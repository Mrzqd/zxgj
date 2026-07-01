from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import math
from pathlib import Path
import re

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import case, func, or_, text
from sqlalchemy.orm import Session, joinedload, load_only

from app.core.config import settings
from app.db.vector import format_vector
from app.models import KnowledgeChunk, KnowledgeDocument, User
from app.services.embeddings import (
    cosine_similarity,
    embed_text,
    parse_term_signature,
    rerank,
    sparse_cosine_similarity,
    term_signature,
    tokenize,
)
from app.services.llm import generate_answer, rewrite_search_query, stream_answer
from app.services.knowledge_jobs import enqueue_knowledge_index, knowledge_index_job_statuses


KNOWLEDGE_DIR = Path(__file__).resolve().parents[1] / "knowledge" / "documents"
MAX_KNOWLEDGE_UPLOAD_BYTES = 2 * 1024 * 1024
SUPPORTED_EXTENSIONS = {".md", ".txt"}
MIN_CHUNK_CHARS = 400
CHUNKING_VERSION = "semantic-v1"
MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}\s+(.+)$")
CHINESE_HEADING_RE = re.compile(r"^(第[一二三四五六七八九十百千0-9]+[章节].{0,120}|附录\s*[A-ZＡ-Ｚ一二三四五六七八九十0-9]+.{0,120})$")
CHINESE_ARTICLE_RE = re.compile(r"^第[一二三四五六七八九十百千0-9]+条\s*.+")
NUMBERED_CLAUSE_RE = re.compile(r"^\d+(?:\.\d+){2,6}\s*.+")
NUMBERED_HEADING_RE = re.compile(r"^\d+(?:\.\d+)?\s+[\u4e00-\u9fffA-Za-z].{0,80}$")
LIST_ITEM_RE = re.compile(r"^(?:[-*+]\s+|[（(]?[一二三四五六七八九十]+[）)、.]|[（(]?\d{1,3}[）)、.]|[a-zA-Z][.)、])\s*.+")
_BUILTIN_SYNC_KEYS: set[str] = set()
_INDEXED_SCOPE_KEYS: set[tuple[int | None, str]] = set()
_BUILTIN_SIGNATURE_CACHE: str | None = None
_BUILTIN_RECORDS_SYNC_KEY: str | None = None


@dataclass
class RetrievedChunk:
    chunk: KnowledgeChunk
    score: float


@dataclass
class RagContext:
    results: list[RetrievedChunk]
    contexts: list[str]
    retrieval_query: str
    has_pending_documents: bool = False


@dataclass
class KnowledgeIndexResult:
    filename: str
    title: str
    ok: bool
    error: str | None = None


@dataclass
class KnowledgeIndexTriggerResult:
    queued: int
    skipped: int
    failed: int
    total_unready: int


@dataclass
class DocumentIndexSnapshot:
    id: int
    title: str
    filename: str
    content: str
    content_hash: str


@dataclass
class KnowledgeChunkDraft:
    chunk_index: int
    heading: str
    content: str
    terms: str
    embedding: str
    embedding_vector: list[float]
    embedding_index_vector: list[float]


@dataclass
class CandidateChunk:
    chunk: KnowledgeChunk
    routes: dict[str, int]


@dataclass
class BuiltContext:
    results: list[RetrievedChunk]
    contexts: list[str]


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _fallback_retrieval_query(question: str, history: list[dict[str, str]] | None = None) -> str:
    history = history or []
    recent_user_messages = [
        message.get("content", "").strip()
        for message in history[-6:]
        if message.get("role") == "user" and message.get("content", "").strip()
    ]
    if not recent_user_messages:
        return question
    return _clean_text(" ".join(recent_user_messages[-2:] + [question]))[:500]


def build_retrieval_query(question: str, history: list[dict[str, str]] | None = None) -> str:
    if not history:
        return question
    try:
        rewritten = rewrite_search_query(question, history=history)
    except Exception:
        rewritten = None
    return _clean_text(rewritten or _fallback_retrieval_query(question, history))[:500] or question


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _chunk_limits() -> tuple[int, int]:
    target = max(MIN_CHUNK_CHARS, settings.knowledge_chunk_target_chars)
    maximum = max(target, settings.knowledge_chunk_max_chars)
    return target, maximum


def _extract_title(content: str, fallback: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("# ").strip()[:180] or fallback
    return fallback


def _extract_summary(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped[:300]
    return ""


def _split_long_text(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            split_at = max(
                text.rfind("。", start, end),
                text.rfind("；", start, end),
                text.rfind("，", start, end),
                text.rfind("\n", start, end),
                text.rfind(" ", start, end),
            )
            if split_at > start + max_chars // 2:
                end = split_at + 1
        part = text[start:end].strip()
        if part:
            parts.append(part)
        start = end
    return parts


def _normalize_content_line(line: str) -> str:
    return re.sub(r"[ \t]+", " ", line.strip())


def _clean_chunk_text(text: str) -> str:
    lines = [_normalize_content_line(line) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def _is_table_line(line: str) -> bool:
    return line.startswith("|") and line.endswith("|")


def _is_semantic_heading(line: str) -> bool:
    return bool(
        CHINESE_HEADING_RE.match(line)
        or (NUMBERED_HEADING_RE.match(line) and not NUMBERED_CLAUSE_RE.match(line))
    )


def _starts_semantic_unit(line: str) -> bool:
    return bool(
        NUMBERED_CLAUSE_RE.match(line)
        or CHINESE_ARTICLE_RE.match(line)
        or LIST_ITEM_RE.match(line)
        or line.startswith(("注：", "注1", "注 1", "说明："))
    )


def _semantic_units(lines: list[str]) -> list[str]:
    units: list[str] = []
    current: list[str] = []
    in_table = False

    def flush() -> None:
        if not current:
            return
        text = _clean_chunk_text("\n".join(current))
        if text:
            units.append(text)
        current.clear()

    for line in lines:
        text = _normalize_content_line(line)
        if not text:
            continue

        is_table = _is_table_line(text)
        if is_table:
            if current and not in_table:
                flush()
            current.append(text)
            in_table = True
            continue

        if in_table:
            flush()
            in_table = False

        if _starts_semantic_unit(text) and current:
            flush()
        current.append(text)

    flush()
    return units


def _pack_semantic_units(units: list[str]) -> list[str]:
    target_chars, max_chars = _chunk_limits()
    chunks: list[str] = []
    buffer: list[str] = []
    buffer_length = 0

    def flush() -> None:
        nonlocal buffer_length
        if not buffer:
            return
        text = _clean_chunk_text("\n\n".join(buffer))
        if text:
            chunks.append(text)
        buffer.clear()
        buffer_length = 0

    for unit in units:
        text = _clean_chunk_text(unit)
        if not text:
            continue
        if len(text) > max_chars:
            flush()
            chunks.extend(_split_long_text(text, max_chars))
            continue
        if buffer and buffer_length + len(text) + 2 > target_chars:
            flush()
        buffer.append(text)
        buffer_length += len(text) + 2

    flush()
    return chunks


def _split_content(content: str) -> list[tuple[str, str]]:
    chunks: list[tuple[str, str]] = []
    current_heading = _extract_title(content, "装修资料")
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        for text in _pack_semantic_units(_semantic_units(buffer)):
            chunks.append((current_heading, text))
        buffer.clear()

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        markdown_heading = MARKDOWN_HEADING_RE.match(line)
        if markdown_heading:
            flush()
            current_heading = markdown_heading.group(1).strip()[:180] or current_heading
            continue
        if _is_semantic_heading(line):
            flush()
            current_heading = line[:180] or current_heading
            continue
        buffer.append(line)
    flush()
    return chunks


def _embedding_input_limit() -> int:
    return max(1000, settings.knowledge_embedding_max_chars)


def _split_for_embedding_budget(title: str, heading: str, chunk_content: str) -> list[str]:
    search_title = title[:180]
    search_heading = heading[:180]
    prefix_length = len(f"{search_title} {search_heading} ")
    max_chars = _embedding_input_limit()
    content_budget = max(200, max_chars - prefix_length)
    parts: list[str] = []

    for part in _split_long_text(chunk_content, content_budget):
        if len(f"{search_title} {search_heading} {part}") <= max_chars:
            parts.append(part)
            continue

        # Last-resort hard split for pathological MinerU output or very long headings.
        hard_budget = max(1, max_chars - prefix_length)
        parts.extend(_split_long_text(part, hard_budget))

    return [part for part in parts if part.strip()]


def _document_scope_filter(project_id: int | None):
    if project_id is None:
        return KnowledgeDocument.project_id.is_(None)
    return or_(KnowledgeDocument.project_id.is_(None), KnowledgeDocument.project_id == project_id)


def _builtin_signature() -> str:
    digest = sha256()
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _chunking_config_key() -> str:
    target_chars, max_chars = _chunk_limits()
    return f"{CHUNKING_VERSION}:{target_chars}:{max_chars}"


def _projection_config_key() -> str:
    return f"projection-hash-v1:{settings.embedding_index_dimensions}"


def _normalized_embedding_model() -> str:
    model = (settings.embedding_model or "local").strip().replace("\\", "/").rstrip("/")
    lowered = model.lower()
    if lowered in {"./models/qwen3-embedding-8b", "models/qwen3-embedding-8b", "qwen3-embedding-8b"}:
        return "Qwen/Qwen3-Embedding-8B"
    return model


def _embedding_model_storage_key() -> str:
    model = _normalized_embedding_model()
    digest = sha256(f"{model}|{_chunking_config_key()}".encode("utf-8")).hexdigest()[:12]
    suffix = f"|ck:{digest}"
    return f"{model[: 120 - len(suffix)]}{suffix}"


def _embedding_runtime_config_key() -> str:
    return "|".join(
        [
            settings.embedding_provider,
            _normalized_embedding_model(),
            str(settings.embedding_dimensions),
            str(settings.embedding_index_dimensions),
            _projection_config_key(),
            _chunking_config_key(),
            str(settings.knowledge_embedding_max_chars),
        ]
    )


def _embedding_config_key() -> str:
    return _embedding_runtime_config_key()


def _document_index_signature(content_hash: str) -> str:
    return sha256(f"{content_hash}|{_embedding_runtime_config_key()}".encode("utf-8")).hexdigest()


def _document_seed_current(document: KnowledgeDocument, content_hash: str) -> bool:
    return document.content_hash == content_hash and document.title and document.content


def _invalidate_scope_cache(project_id: int | None) -> None:
    for key in list(_INDEXED_SCOPE_KEYS):
        if key[0] == project_id:
            _INDEXED_SCOPE_KEYS.discard(key)


def _embedding_config_current(chunk: KnowledgeChunk) -> bool:
    return (
        chunk.embedding_provider == settings.embedding_provider
        and chunk.embedding_model == _embedding_model_storage_key()
        and chunk.embedding_dimensions == settings.embedding_dimensions
        and bool(chunk.embedding_vector)
        and chunk.embedding_index_dimensions == settings.embedding_index_dimensions
        and bool(chunk.embedding_index_vector)
    )


def _chunk_vectors_reusable(chunk: KnowledgeChunk) -> bool:
    return (
        chunk.embedding_provider == settings.embedding_provider
        and chunk.embedding_dimensions == settings.embedding_dimensions
        and bool(chunk.embedding_vector)
        and chunk.embedding_index_dimensions == settings.embedding_index_dimensions
        and bool(chunk.embedding_index_vector)
    )


def _document_embeddings_current(document: KnowledgeDocument) -> bool:
    chunks = list(document.chunks)
    current_signature = _document_index_signature(document.content_hash)
    return (
        document.index_status == "ready"
        and document.index_signature == current_signature
        and bool(chunks)
        and all(_embedding_config_current(chunk) for chunk in chunks)
    )


def _refresh_reusable_embedding_metadata(document: KnowledgeDocument) -> bool:
    if "chunks" not in document.__dict__:
        return False
    chunks = list(document.chunks)
    if not chunks or not all(_chunk_vectors_reusable(chunk) for chunk in chunks):
        return False
    storage_key = _embedding_model_storage_key()
    for chunk in chunks:
        chunk.embedding_model = storage_key
    document.index_status = "ready"
    document.index_signature = _document_index_signature(document.content_hash)
    document.index_error = None
    if document.indexed_at is None:
        document.indexed_at = _utcnow()
    return True


def _document_index_metadata_current(document: KnowledgeDocument) -> bool:
    return (
        document.index_status == "ready"
        and document.index_signature == _document_index_signature(document.content_hash)
    )


def _document_needs_index(document: KnowledgeDocument) -> bool:
    if "chunks" in document.__dict__:
        return not _document_embeddings_current(document)
    return not _document_index_metadata_current(document)


def _chunk_config_document_ids(
    db: Session,
    document_ids: list[int],
    *,
    require_current_model: bool,
) -> set[int]:
    if not document_ids:
        return set()

    condition = (
        (KnowledgeChunk.embedding_provider == settings.embedding_provider)
        & (KnowledgeChunk.embedding_dimensions == settings.embedding_dimensions)
        & KnowledgeChunk.embedding_vector.isnot(None)
        & (KnowledgeChunk.embedding_index_dimensions == settings.embedding_index_dimensions)
        & KnowledgeChunk.embedding_index_vector.isnot(None)
    )
    if require_current_model:
        condition = condition & (KnowledgeChunk.embedding_model == _embedding_model_storage_key())

    matching_count = func.sum(case((condition, 1), else_=0))
    rows = (
        db.query(KnowledgeChunk.document_id)
        .filter(KnowledgeChunk.document_id.in_(document_ids))
        .group_by(KnowledgeChunk.document_id)
        .having(func.count(KnowledgeChunk.id) > 0)
        .having(func.count(KnowledgeChunk.id) == matching_count)
        .all()
    )
    return {int(row[0]) for row in rows}


def _refresh_reusable_embedding_metadata_for_documents(
    db: Session,
    documents: list[KnowledgeDocument],
    *,
    current_document_ids: set[int] | None = None,
) -> set[int]:
    current_document_ids = current_document_ids or set()
    candidates = [document for document in documents if document.id not in current_document_ids]
    reusable_ids = _chunk_config_document_ids(
        db,
        [document.id for document in candidates],
        require_current_model=False,
    )
    if not reusable_ids:
        return set()

    db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id.in_(reusable_ids)).update(
        {KnowledgeChunk.embedding_model: _embedding_model_storage_key()},
        synchronize_session=False,
    )
    now = _utcnow()
    for document in candidates:
        if document.id not in reusable_ids:
            continue
        document.index_status = "ready"
        document.index_signature = _document_index_signature(document.content_hash)
        document.index_error = None
        if document.indexed_at is None:
            document.indexed_at = now
    return reusable_ids


def _builtin_records_sync_key() -> str:
    digest = sha256()
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        stat = path.stat()
        digest.update(path.name.encode("utf-8"))
        digest.update(str(stat.st_size).encode("ascii"))
        digest.update(str(stat.st_mtime_ns).encode("ascii"))
    return digest.hexdigest()


def _mark_pending_if_stale(document: KnowledgeDocument) -> bool:
    if not _document_needs_index(document):
        return False
    if _refresh_reusable_embedding_metadata(document):
        return False
    if document.index_status not in {"indexing", "queued"}:
        document.index_status = "pending"
    document.index_signature = None
    document.indexed_at = None
    return True


def _mark_queued_index(document: KnowledgeDocument) -> None:
    document.index_status = "queued"
    document.index_signature = None
    document.indexed_at = None


def enqueue_document_index(document: KnowledgeDocument) -> None:
    enqueue_knowledge_index(document.id, _document_index_signature(document.content_hash))


def _try_enqueue_document_index(document: KnowledgeDocument) -> bool:
    try:
        enqueue_document_index(document)
        return True
    except Exception as exc:
        document.index_status = "failed"
        document.index_error = f"索引任务入队失败：{exc}"[:2000]
        document.index_signature = None
        document.indexed_at = None
        return False


def _sync_runtime_index_statuses(db: Session, documents: list[KnowledgeDocument]) -> None:
    active_documents = [document for document in documents if document.index_status in {"queued", "indexing"}]
    if not active_documents:
        return
    try:
        runtime_statuses = knowledge_index_job_statuses()
    except Exception:
        return
    for document in active_documents:
        runtime_status = runtime_statuses.get(document.id)
        if runtime_status:
            document.index_status = runtime_status
        elif document.index_status in {"queued", "indexing"}:
            document.index_status = "pending"


def _document_index_metadata_options():
    return load_only(
        KnowledgeDocument.id,
        KnowledgeDocument.project_id,
        KnowledgeDocument.source_type,
        KnowledgeDocument.title,
        KnowledgeDocument.filename,
        KnowledgeDocument.content_hash,
        KnowledgeDocument.summary,
        KnowledgeDocument.index_status,
        KnowledgeDocument.index_signature,
        KnowledgeDocument.indexed_at,
        KnowledgeDocument.index_error,
        KnowledgeDocument.created_at,
    )


def _scoped_document_metadata_query(db: Session, project_id: int | None):
    return (
        db.query(KnowledgeDocument)
        .options(_document_index_metadata_options())
        .filter(_document_scope_filter(project_id))
    )


def _embed_for_storage(text_value: str, *, source: str | None = None) -> tuple[str, list[float]]:
    try:
        vector = embed_text(text_value)
    except Exception as exc:
        source_text = f"（{source}，字符数 {len(text_value)}）" if source else f"（字符数 {len(text_value)}）"
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"嵌入模型调用失败{source_text}：{exc}",
        ) from exc
    if len(vector) != settings.embedding_dimensions:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"嵌入向量维度为 {len(vector)}，与 EMBEDDING_DIMENSIONS={settings.embedding_dimensions} 不一致",
        )
    return term_signature(text_value), vector


def _project_embedding(vector: list[float]) -> list[float]:
    dimensions = max(1, settings.embedding_index_dimensions)
    projected = [0.0] * dimensions
    for index, value in enumerate(vector):
        if not value:
            continue
        digest = sha256(f"{index}".encode("utf-8")).digest()
        target = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        projected[target] += float(value) * sign
    norm = math.sqrt(sum(value * value for value in projected))
    if not norm:
        return projected
    return [value / norm for value in projected]


def _build_chunk_drafts(title: str, filename: str, content: str) -> list[KnowledgeChunkDraft]:
    drafts: list[KnowledgeChunkDraft] = []
    search_title = title[:180]
    for heading, chunk_content in _split_content(content):
        search_heading = heading[:180]
        for part in _split_for_embedding_budget(search_title, search_heading, chunk_content):
            searchable_text = f"{search_title} {search_heading} {part}"
            chunk_index = len(drafts)
            signature, vector = _embed_for_storage(searchable_text, source=f"{filename}#{chunk_index + 1}")
            terms = " ".join(sorted(set(tokenize(searchable_text))))
            drafts.append(
                KnowledgeChunkDraft(
                    chunk_index=chunk_index,
                    heading=search_heading,
                    content=part,
                    terms=terms,
                    embedding=signature,
                    embedding_vector=vector,
                    embedding_index_vector=_project_embedding(vector),
                )
            )
    return drafts


def _replace_document_chunks(
    db: Session,
    document: KnowledgeDocument,
    drafts: list[KnowledgeChunkDraft],
) -> None:
    document.chunks.clear()
    db.flush()
    for draft in drafts:
        db.add(
            KnowledgeChunk(
                document_id=document.id,
                chunk_index=draft.chunk_index,
                heading=draft.heading,
                content=draft.content,
                terms=draft.terms,
                embedding=draft.embedding,
                embedding_provider=settings.embedding_provider,
                embedding_model=_embedding_model_storage_key(),
                embedding_dimensions=settings.embedding_dimensions,
                embedding_vector=draft.embedding_vector,
                embedding_index_dimensions=settings.embedding_index_dimensions,
                embedding_index_vector=draft.embedding_index_vector,
            )
        )


def _index_document_chunks(db: Session, document: KnowledgeDocument, title: str, content: str) -> None:
    _replace_document_chunks(db, document, _build_chunk_drafts(title, document.filename, content))


def _upsert_document(
    db: Session,
    *,
    title: str,
    filename: str,
    content: str,
    source_type: str,
    project_id: int | None = None,
    uploader_id: int | None = None,
    content_type: str | None = "text/markdown",
) -> KnowledgeDocument:
    content_hash = sha256(content.encode("utf-8")).hexdigest()
    project_filter = (
        KnowledgeDocument.project_id.is_(None)
        if project_id is None
        else KnowledgeDocument.project_id == project_id
    )
    document = (
        db.query(KnowledgeDocument)
        .options(joinedload(KnowledgeDocument.chunks))
        .filter(
            project_filter,
            KnowledgeDocument.filename == filename,
            KnowledgeDocument.source_type == source_type,
        )
        .first()
    )
    if document and document.content_hash == content_hash and _document_embeddings_current(document):
        return document

    if not document:
        document = KnowledgeDocument(
            project_id=project_id,
            uploader_id=uploader_id,
            source_type=source_type,
            title=title,
            filename=filename,
            content_type=content_type,
            content_hash=content_hash,
            summary=_extract_summary(content),
            content=content,
            index_status="indexing",
            index_signature=None,
            index_error=None,
        )
        db.add(document)
        db.flush()
    else:
        document.title = title
        document.uploader_id = uploader_id
        document.content_type = content_type
        document.content_hash = content_hash
        document.summary = _extract_summary(content)
        document.content = content
        document.index_status = "indexing"
        document.index_signature = None
        document.index_error = None
        document.indexed_at = None
        document.chunks.clear()
        db.flush()

    _index_document_chunks(db, document, title, content)
    document.index_status = "ready"
    document.index_signature = _document_index_signature(document.content_hash)
    document.indexed_at = _utcnow()
    document.index_error = None
    db.flush()
    return document


def _upsert_document_record(
    db: Session,
    *,
    title: str,
    filename: str,
    content: str,
    source_type: str,
    project_id: int | None = None,
    uploader_id: int | None = None,
    content_type: str | None = "text/markdown",
) -> KnowledgeDocument:
    content_hash = sha256(content.encode("utf-8")).hexdigest()
    project_filter = (
        KnowledgeDocument.project_id.is_(None)
        if project_id is None
        else KnowledgeDocument.project_id == project_id
    )
    document = (
        db.query(KnowledgeDocument)
        .filter(
            project_filter,
            KnowledgeDocument.filename == filename,
            KnowledgeDocument.source_type == source_type,
        )
        .first()
    )
    if document and _document_seed_current(document, content_hash):
        return document
    if not document:
        document = KnowledgeDocument(
            project_id=project_id,
            uploader_id=uploader_id,
            source_type=source_type,
            title=title,
            filename=filename,
            content_type=content_type,
            content_hash=content_hash,
            summary=_extract_summary(content),
            content=content,
            index_status="pending",
            index_signature=None,
            index_error=None,
        )
        db.add(document)
        db.flush()
        return document

    document.title = title
    document.uploader_id = uploader_id
    document.content_type = content_type
    document.content_hash = content_hash
    document.summary = _extract_summary(content)
    document.content = content
    document.chunks.clear()
    document.index_status = "pending"
    document.index_signature = None
    document.index_error = None
    document.indexed_at = None
    db.flush()
    return document


def ensure_builtin_records(db: Session, filenames: set[str] | None = None, *, force: bool = False) -> None:
    global _BUILTIN_RECORDS_SYNC_KEY
    sync_key = None if filenames is not None else _builtin_records_sync_key()
    if not force and sync_key is not None and _BUILTIN_RECORDS_SYNC_KEY == sync_key:
        return

    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        if filenames is not None and path.name not in filenames:
            continue
        content = path.read_text(encoding="utf-8")
        _upsert_document_record(
            db,
            title=_extract_title(content, path.stem),
            filename=path.name,
            content=content,
            source_type="builtin",
        )
    if sync_key is not None:
        _BUILTIN_RECORDS_SYNC_KEY = sync_key


def ensure_builtin_knowledge(db: Session) -> None:
    ensure_builtin_records(db)
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        document = (
            db.query(KnowledgeDocument)
            .filter(
                KnowledgeDocument.project_id.is_(None),
                KnowledgeDocument.filename == path.name,
                KnowledgeDocument.source_type == "builtin",
            )
            .first()
        )
        if document and _mark_pending_if_stale(document):
            _try_enqueue_document_index(document)


def ensure_index_jobs(db: Session, project_id: int | None) -> None:
    ensure_builtin_records(db)
    documents = _scoped_document_metadata_query(db, project_id).all()
    _sync_runtime_index_statuses(db, documents)
    stale_documents = [
        document
        for document in documents
        if not _document_index_metadata_current(document)
    ]
    stale_ids = {document.id for document in stale_documents}
    reusable_ids = _refresh_reusable_embedding_metadata_for_documents(db, stale_documents)
    for document in documents:
        if document.id not in stale_ids or document.id in reusable_ids:
            continue
        if document.index_status in {"indexing", "queued"}:
            continue
        document.index_status = "pending"
        document.index_signature = None
        document.indexed_at = None
        _try_enqueue_document_index(document)


def trigger_unready_index_jobs(db: Session, project_id: int | None) -> KnowledgeIndexTriggerResult:
    ensure_builtin_records(db)
    documents = (
        _scoped_document_metadata_query(db, project_id)
        .filter(_document_scope_filter(project_id), KnowledgeDocument.index_status != "ready")
        .all()
    )
    _sync_runtime_index_statuses(db, documents)
    reusable_ids = _refresh_reusable_embedding_metadata_for_documents(db, documents)
    queued = 0
    skipped = len(reusable_ids)
    failed = 0
    for document in documents:
        if document.id in reusable_ids:
            continue
        if document.index_status in {"queued", "indexing"}:
            skipped += 1
            continue
        _mark_queued_index(document)
        if _try_enqueue_document_index(document):
            queued += 1
        else:
            failed += 1
    return KnowledgeIndexTriggerResult(
        queued=queued,
        skipped=skipped,
        failed=failed,
        total_unready=len(documents),
    )


def index_document_by_id(db: Session, document_id: int) -> KnowledgeDocument | None:
    document = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.id == document_id)
        .first()
    )
    if document is None:
        return None
    if _document_index_metadata_current(document) and db.query(KnowledgeChunk.id).filter(
        KnowledgeChunk.document_id == document.id
    ).first():
        return document

    document.index_status = "indexing"
    document.index_error = None
    db.flush()
    snapshot = DocumentIndexSnapshot(
        id=document.id,
        title=document.title,
        filename=document.filename,
        content=document.content,
        content_hash=document.content_hash,
    )
    db.commit()

    try:
        drafts = _build_chunk_drafts(snapshot.title, snapshot.filename, snapshot.content)
        document = (
            db.query(KnowledgeDocument)
            .options(joinedload(KnowledgeDocument.chunks))
            .filter(KnowledgeDocument.id == snapshot.id)
            .first()
        )
        if document is None:
            return None
        if document.content_hash != snapshot.content_hash:
            document.index_status = "pending"
            document.index_error = "文档内容在索引过程中发生变化，等待重新索引"
            document.index_signature = None
            document.indexed_at = None
            db.flush()
            return document
        _replace_document_chunks(db, document, drafts)
        document.index_status = "ready"
        document.index_signature = _document_index_signature(snapshot.content_hash)
        document.indexed_at = _utcnow()
        document.index_error = None
        db.flush()
    except Exception as exc:
        db.rollback()
        document = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == snapshot.id).first()
        if document is None:
            raise
        document.index_status = "failed"
        document.index_error = str(exc)[:2000]
        document.index_signature = None
        document.indexed_at = None
        db.flush()
        raise
    return document


def mark_document_index_failed(db: Session, document_id: int, error: str) -> None:
    document = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == document_id).first()
    if document is None:
        return
    document.index_status = "failed"
    document.index_error = error[:2000]
    document.index_signature = None
    document.indexed_at = None
    db.flush()


def index_builtin_knowledge_independently(
    session_factory,
    filenames: set[str] | None = None,
) -> list[KnowledgeIndexResult]:
    seed_db = session_factory()
    try:
        ensure_builtin_records(seed_db, filenames=filenames, force=True)
        seed_db.commit()
    except Exception:
        seed_db.rollback()
        raise
    finally:
        seed_db.close()

    results: list[KnowledgeIndexResult] = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        if filenames is not None and path.name not in filenames:
            continue
        content = path.read_text(encoding="utf-8")
        title = _extract_title(content, path.stem)
        db = session_factory()
        try:
            document = _upsert_document_record(
                db,
                title=title,
                filename=path.name,
                content=content,
                source_type="builtin",
            )
            index_document_by_id(db, document.id)
            db.commit()
            results.append(KnowledgeIndexResult(filename=path.name, title=title, ok=True))
        except Exception as exc:
            db.rollback()
            failed_document = (
                db.query(KnowledgeDocument)
                .filter(
                    KnowledgeDocument.project_id.is_(None),
                    KnowledgeDocument.filename == path.name,
                    KnowledgeDocument.source_type == "builtin",
                )
                .first()
            )
            if failed_document:
                mark_document_index_failed(db, failed_document.id, str(exc))
                db.commit()
            results.append(KnowledgeIndexResult(filename=path.name, title=title, ok=False, error=str(exc)))
        finally:
            db.close()

    _BUILTIN_SYNC_KEYS.discard(_embedding_config_key())
    _INDEXED_SCOPE_KEYS.clear()
    return results


def ensure_scoped_embeddings(db: Session, project_id: int | None) -> None:
    scope_key = (project_id, _embedding_config_key())
    if scope_key in _INDEXED_SCOPE_KEYS:
        return

    ensure_index_jobs(db, project_id)
    _INDEXED_SCOPE_KEYS.add(scope_key)


def list_documents(db: Session, project_id: int | None = None) -> list[KnowledgeDocument]:
    ensure_index_jobs(db, project_id)
    documents = (
        db.query(KnowledgeDocument)
        .options(
            load_only(
                KnowledgeDocument.id,
                KnowledgeDocument.project_id,
                KnowledgeDocument.source_type,
                KnowledgeDocument.title,
                KnowledgeDocument.filename,
                KnowledgeDocument.summary,
                KnowledgeDocument.index_status,
                KnowledgeDocument.indexed_at,
                KnowledgeDocument.index_error,
                KnowledgeDocument.created_at,
            )
        )
        .filter(_document_scope_filter(project_id))
        .order_by(KnowledgeDocument.source_type.asc(), KnowledgeDocument.created_at.desc())
        .all()
    )
    _sync_runtime_index_statuses(db, documents)
    return documents


def get_document(db: Session, document_id: int, project_id: int | None = None) -> KnowledgeDocument | None:
    ensure_index_jobs(db, project_id)
    return (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.id == document_id, _document_scope_filter(project_id))
        .first()
    )


def update_upload_document(
    db: Session,
    *,
    document_id: int,
    project_id: int,
    title: str,
    filename: str,
    content: str,
    content_type: str | None = "text/markdown",
) -> KnowledgeDocument | None:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 .md 或 .txt 文件")
    if not _clean_text(content):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件内容不能为空")
    if len(content.encode("utf-8")) > MAX_KNOWLEDGE_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="知识库文件不能超过 2MB")

    document = (
        db.query(KnowledgeDocument)
        .filter(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.project_id == project_id,
            KnowledgeDocument.source_type == "upload",
        )
        .first()
    )
    if not document:
        return None

    document.title = title
    document.filename = filename
    document.content_type = content_type or "text/markdown"
    document.content_hash = sha256(content.encode("utf-8")).hexdigest()
    document.summary = _extract_summary(content)
    document.content = content
    document.chunks.clear()
    document.index_status = "pending"
    document.index_signature = None
    document.index_error = None
    document.indexed_at = None
    _invalidate_scope_cache(project_id)
    db.flush()
    _try_enqueue_document_index(document)
    return document


def ingest_upload(db: Session, project_id: int, user: User, file: UploadFile) -> KnowledgeDocument:
    filename = file.filename or "knowledge.md"
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="仅支持 .md 或 .txt 文件")

    raw = file.file.read(MAX_KNOWLEDGE_UPLOAD_BYTES + 1)
    if len(raw) > MAX_KNOWLEDGE_UPLOAD_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="知识库文件不能超过 2MB")
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件必须是 UTF-8 文本") from None

    if not _clean_text(content):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="文件内容不能为空")

    document = _upsert_document_record(
        db,
        title=_extract_title(content, Path(filename).stem),
        filename=filename,
        content=content,
        source_type="upload",
        project_id=project_id,
        uploader_id=user.id,
        content_type=file.content_type or "text/plain",
    )
    _invalidate_scope_cache(project_id)
    _try_enqueue_document_index(document)
    return document


def delete_document(db: Session, document_id: int, project_id: int) -> bool:
    document = (
        db.query(KnowledgeDocument)
        .filter(
            KnowledgeDocument.id == document_id,
            KnowledgeDocument.project_id == project_id,
            KnowledgeDocument.source_type == "upload",
        )
        .first()
    )
    if not document:
        return False
    db.delete(document)
    _invalidate_scope_cache(project_id)
    return True


def _scoped_chunk_query(db: Session, project_id: int | None):
    return (
        db.query(KnowledgeChunk)
        .join(KnowledgeDocument)
        .options(joinedload(KnowledgeChunk.document))
        .filter(_document_scope_filter(project_id), KnowledgeDocument.index_status == "ready")
    )


def _vector_candidate_ids(
    db: Session,
    *,
    query_vector: list[float],
    project_id: int | None,
    limit: int,
) -> list[int] | None:
    if db.bind is None or db.bind.dialect.name != "postgresql":
        return None
    scope = "kd.project_id IS NULL" if project_id is None else "(kd.project_id IS NULL OR kd.project_id = :project_id)"
    rows = db.execute(
        text(
            "SELECT kc.id "
            "FROM knowledge_chunks kc "
            "JOIN knowledge_documents kd ON kd.id = kc.document_id "
            f"WHERE {scope} AND kd.index_status = 'ready' AND kc.embedding_index_vector IS NOT NULL "
            "ORDER BY kc.embedding_index_vector <=> CAST(:query_vector AS vector) "
            "LIMIT :limit"
        ),
        {
            "project_id": project_id,
            "query_vector": format_vector(_project_embedding(query_vector)),
            "limit": limit,
        },
    ).all()
    return [int(row[0]) for row in rows]


def _load_chunks_by_ids(db: Session, project_id: int | None, ids: list[int]) -> list[KnowledgeChunk]:
    if not ids:
        return []
    order = {chunk_id: index for index, chunk_id in enumerate(ids)}
    chunks = _scoped_chunk_query(db, project_id).filter(KnowledgeChunk.id.in_(ids)).all()
    chunks.sort(key=lambda chunk: order.get(chunk.id, len(order)))
    return chunks


def _like_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _ranked_query_terms(query_terms: set[str]) -> list[str]:
    return sorted((term for term in query_terms if len(term.strip()) >= 2), key=lambda term: (-len(term), term))[:12]


def _keyword_route_score(chunk: KnowledgeChunk, query_terms: set[str]) -> float:
    chunk_terms = set(chunk.terms.split())
    return float(len(query_terms & chunk_terms))


def _exact_route_score(chunk: KnowledgeChunk, phrases: list[str]) -> float:
    haystack = f"{chunk.document.title} {chunk.heading} {chunk.content}"
    return sum(1.0 for phrase in phrases if phrase and phrase in haystack)


def _keyword_candidate_chunks(
    db: Session,
    *,
    project_id: int | None,
    query_terms: set[str],
    limit: int,
) -> list[KnowledgeChunk]:
    terms = _ranked_query_terms(query_terms)
    if not terms:
        return []
    conditions = [KnowledgeChunk.terms.ilike(_like_pattern(term), escape="\\") for term in terms]
    chunks = _scoped_chunk_query(db, project_id).filter(or_(*conditions)).all()
    chunks.sort(key=lambda chunk: _keyword_route_score(chunk, query_terms), reverse=True)
    return chunks[:limit]


def _exact_candidate_chunks(
    db: Session,
    *,
    project_id: int | None,
    query: str,
    query_terms: set[str],
    limit: int,
) -> list[KnowledgeChunk]:
    phrases = [query] if len(query) >= 2 else []
    phrases.extend(term for term in _ranked_query_terms(query_terms) if term not in phrases)
    if not phrases:
        return []
    conditions = []
    for phrase in phrases[:8]:
        pattern = _like_pattern(phrase)
        conditions.extend(
            [
                KnowledgeDocument.title.ilike(pattern, escape="\\"),
                KnowledgeChunk.heading.ilike(pattern, escape="\\"),
                KnowledgeChunk.content.ilike(pattern, escape="\\"),
            ]
        )
    chunks = _scoped_chunk_query(db, project_id).filter(or_(*conditions)).all()
    chunks.sort(key=lambda chunk: _exact_route_score(chunk, phrases), reverse=True)
    return chunks[:limit]


def _merge_candidate_routes(route_chunks: dict[str, list[KnowledgeChunk]]) -> list[CandidateChunk]:
    candidates: dict[int, CandidateChunk] = {}
    for route, chunks in route_chunks.items():
        for rank, chunk in enumerate(chunks, start=1):
            candidate = candidates.get(chunk.id)
            if candidate is None:
                candidate = CandidateChunk(chunk=chunk, routes={})
                candidates[chunk.id] = candidate
            candidate.routes[route] = min(rank, candidate.routes.get(route, rank))
    return list(candidates.values())


def _load_candidate_chunks(
    db: Session,
    *,
    project_id: int | None,
    query: str,
    query_terms: set[str],
    query_vector: list[float],
    limit: int,
) -> list[CandidateChunk]:
    vector_ids = _vector_candidate_ids(db, query_vector=query_vector, project_id=project_id, limit=limit)
    vector_chunks = (
        _load_chunks_by_ids(db, project_id, vector_ids)
        if vector_ids is not None
        else _scoped_chunk_query(db, project_id).all()
    )
    keyword_chunks = _keyword_candidate_chunks(db, project_id=project_id, query_terms=query_terms, limit=limit)
    exact_chunks = _exact_candidate_chunks(
        db,
        project_id=project_id,
        query=query,
        query_terms=query_terms,
        limit=limit,
    )
    return _merge_candidate_routes(
        {
            "vector": vector_chunks,
            "keyword": keyword_chunks,
            "exact": exact_chunks,
        }
    )


def _rrf_route_score(routes: dict[str, int]) -> float:
    weights = {"vector": 1.0, "keyword": 0.9, "exact": 1.1}
    return sum(weights.get(route, 0.5) / (60 + rank) for route, rank in routes.items())


def _apply_rerank(query: str, scored: list[RetrievedChunk]) -> list[RetrievedChunk]:
    if not scored:
        return scored
    try:
        rerank_scores = rerank(
            query,
            [f"{item.chunk.document.title}\n{item.chunk.heading}\n{item.chunk.content}" for item in scored],
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"重排模型调用失败：{exc}",
        ) from exc
    if rerank_scores is None:
        return scored
    rescored = [
        RetrievedChunk(chunk=item.chunk, score=(item.score * 0.35) + (rerank_scores[index] * 1.2))
        for index, item in enumerate(scored)
    ]
    rescored.sort(key=lambda item: item.score, reverse=True)
    return rescored


def retrieve(db: Session, question: str, project_id: int | None, limit: int = 5) -> list[RetrievedChunk]:
    query = _clean_text(question)
    if not query:
        return []
    ensure_scoped_embeddings(db, project_id)
    query_signature = parse_term_signature(term_signature(query))
    query_terms = set(tokenize(query))
    _, query_vector = _embed_for_storage(query)
    candidate_limit = max(limit, settings.rag_candidate_limit)
    candidates = _load_candidate_chunks(
        db,
        project_id=project_id,
        query=query,
        query_terms=query_terms,
        query_vector=query_vector,
        limit=candidate_limit,
    )

    scored: list[RetrievedChunk] = []
    for candidate in candidates:
        chunk = candidate.chunk
        chunk_signature = parse_term_signature(chunk.embedding)
        vector_score = cosine_similarity(query_vector, chunk.embedding_vector or [])
        sparse_score = sparse_cosine_similarity(query_signature, chunk_signature)
        chunk_terms = set(chunk.terms.split())
        keyword_score = len(query_terms & chunk_terms) / max(len(query_terms), 1)
        exact_score = sum(1 for term in query_terms if term and term in chunk.content) * 0.08
        route_score = _rrf_route_score(candidate.routes)
        score = (route_score * 8) + (vector_score * 1.15) + (sparse_score * 0.45) + keyword_score + exact_score
        if score > 0:
            scored.append(RetrievedChunk(chunk=chunk, score=score))

    scored.sort(key=lambda item: item.score, reverse=True)
    return _apply_rerank(query, scored[:candidate_limit])[:limit]


def _clip_context_text(text_value: str) -> str:
    limit = max(400, settings.rag_context_per_source_max_chars)
    if len(text_value) <= limit:
        return text_value
    return text_value[:limit].rstrip() + "\n..."


def _neighbor_chunks(db: Session, chunk: KnowledgeChunk) -> list[KnowledgeChunk]:
    window = max(0, settings.rag_neighbor_window)
    if window <= 0:
        return []
    start = max(0, chunk.chunk_index - window)
    end = chunk.chunk_index + window
    return (
        db.query(KnowledgeChunk)
        .filter(
            KnowledgeChunk.document_id == chunk.document_id,
            KnowledgeChunk.chunk_index >= start,
            KnowledgeChunk.chunk_index <= end,
        )
        .order_by(KnowledgeChunk.chunk_index.asc())
        .all()
    )


def build_contexts(db: Session, results: list[RetrievedChunk]) -> BuiltContext:
    max_chars = max(1000, settings.rag_context_max_chars)
    contexts: list[str] = []
    kept_results: list[RetrievedChunk] = []
    used_chars = 0
    seen_chunks: set[int] = set()
    document_counts: dict[int, int] = {}

    for result in results:
        document_id = result.chunk.document_id
        if document_counts.get(document_id, 0) >= 3:
            continue
        chunks = _neighbor_chunks(db, result.chunk) or [result.chunk]
        chunks = [chunk for chunk in chunks if chunk.id not in seen_chunks]
        if not chunks:
            continue
        body = "\n\n".join(f"{chunk.heading}\n{chunk.content}" for chunk in chunks)
        context = _clip_context_text(f"{result.chunk.document.title}\n{body}")
        if contexts and used_chars + len(context) > max_chars:
            continue
        if len(context) > max_chars:
            context = context[:max_chars].rstrip() + "\n..."
        contexts.append(f"[{len(contexts) + 1}] {context}")
        kept_results.append(result)
        used_chars += len(context)
        document_counts[document_id] = document_counts.get(document_id, 0) + 1
        for chunk in chunks:
            seen_chunks.add(chunk.id)
        if used_chars >= max_chars:
            break

    return BuiltContext(results=kept_results, contexts=contexts)


def has_pending_documents(db: Session, project_id: int | None) -> bool:
    return (
        db.query(KnowledgeDocument)
        .filter(
            _document_scope_filter(project_id),
            KnowledgeDocument.index_status.in_(["pending", "queued", "indexing", "failed"]),
        )
        .first()
        is not None
    )


def build_rag_context(
    db: Session,
    question: str,
    project_id: int | None,
    history: list[dict[str, str]] | None = None,
) -> RagContext:
    retrieval_query = build_retrieval_query(question, history=history)
    results = retrieve(db, retrieval_query, project_id, limit=5)
    built = build_contexts(db, results)
    return RagContext(
        results=built.results,
        contexts=built.contexts,
        retrieval_query=retrieval_query,
        has_pending_documents=has_pending_documents(db, project_id),
    )


def build_no_results_answer() -> str:
    return "知识库里没有命中足够相关的内容。可以上传补充资料，或换成更具体的问题，例如“水电打压怎么验收”“卫生间闭水注意什么”。"


def build_indexing_answer() -> str:
    return "知识库正在索引中，当前还没有命中可用内容。请稍后再试，或先查看已完成索引的资料。"


def build_fallback_answer(results: list[RetrievedChunk]) -> str:
    lines = ["根据知识库检索结果，建议重点看："]
    for index, result in enumerate(results[:3], start=1):
        chunk = result.chunk
        lines.append(f"{index}. {chunk.heading}：{chunk.content}")
    lines.append("回答基于下方引用资料生成；涉及结构、燃气、消防、防水争议时，应以当地法规、物业和专业人员意见为准。")
    return "\n".join(lines)


def build_rag_answer(
    db: Session,
    question: str,
    project_id: int | None,
    history: list[dict[str, str]] | None = None,
) -> tuple[str, list[RetrievedChunk]]:
    rag_context = build_rag_context(db, question, project_id, history=history)
    if not rag_context.results:
        if rag_context.has_pending_documents:
            return build_indexing_answer(), []
        return build_no_results_answer(), []

    try:
        generated = generate_answer(question, rag_context.contexts, history=history)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM 调用失败：{exc}",
        ) from exc
    if generated:
        return generated, rag_context.results

    return build_fallback_answer(rag_context.results), rag_context.results


def stream_rag_answer(question: str, contexts: list[str], history: list[dict[str, str]] | None = None):
    try:
        yield from stream_answer(question, contexts, history=history)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LLM 调用失败：{exc}",
        ) from exc
