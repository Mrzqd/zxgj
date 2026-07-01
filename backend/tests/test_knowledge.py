import os
from hashlib import sha256
from io import BytesIO
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["EMBEDDING_PROVIDER"] = "local"
os.environ["EMBEDDING_DIMENSIONS"] = "384"
os.environ["RERANK_PROVIDER"] = "none"
os.environ["LLM_PROVIDER"] = "none"

from starlette.datastructures import UploadFile
from sqlalchemy.orm import joinedload

from app.api.auth import register
from app.api.knowledge import (
    _knowledge_event_stream,
    _document_to_read,
    ask_knowledge,
    delete_knowledge_document,
    download_knowledge_document,
    get_knowledge_document,
    list_knowledge_documents,
    trigger_knowledge_index,
    update_knowledge_document,
    upload_knowledge_document,
)
from app.api.projects import create_project
from app.db.session import Base, SessionLocal, engine
from app.models import KnowledgeChunk, KnowledgeDocument
from app.schemas import KnowledgeAskRequest, KnowledgeDocumentUpdate, ProjectCreate, UserCreate
from app.services import knowledge
from app.services.knowledge_jobs import index_knowledge_document


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    knowledge._BUILTIN_SYNC_KEYS.clear()
    knowledge._INDEXED_SCOPE_KEYS.clear()
    knowledge._BUILTIN_RECORDS_SYNC_KEY = None


def _upload_file(name: str, content: str) -> UploadFile:
    return UploadFile(filename=name, file=BytesIO(content.encode("utf-8")))


def _add_knowledge_chunk(
    db,
    *,
    title: str,
    heading: str,
    content: str,
    project_id: int | None = None,
) -> KnowledgeChunk:
    document = KnowledgeDocument(
        project_id=project_id,
        source_type="upload" if project_id else "builtin",
        title=title,
        filename=f"{title}.md",
        content_type="text/markdown",
        content_hash=sha256(content.encode("utf-8")).hexdigest(),
        summary=content[:120],
        content=content,
        index_status="ready",
    )
    db.add(document)
    db.flush()
    searchable_text = f"{title} {heading} {content}"
    chunk = KnowledgeChunk(
        document_id=document.id,
        chunk_index=0,
        heading=heading,
        content=content,
        terms=" ".join(sorted(set(knowledge.tokenize(searchable_text)))),
        embedding=knowledge.term_signature(searchable_text),
        embedding_provider=knowledge.settings.embedding_provider,
        embedding_model=knowledge._embedding_model_storage_key(),
        embedding_dimensions=knowledge.settings.embedding_dimensions,
        embedding_vector=[0.0] * knowledge.settings.embedding_dimensions,
        embedding_index_dimensions=knowledge.settings.embedding_index_dimensions,
        embedding_index_vector=[0.0] * knowledge.settings.embedding_index_dimensions,
    )
    document.index_signature = knowledge._document_index_signature(document.content_hash)
    db.add(chunk)
    db.flush()
    return chunk


def test_rag_knowledge_documents_upload_search_download_and_delete():
    db = SessionLocal()
    try:
        token = register(
            UserCreate(email="owner@example.com", name="屋主", password="password123"),
            db,
        )
        project = create_project(ProjectCreate(name="新家装修", address="杭州"), db, token.user)
        knowledge.index_builtin_knowledge_independently(SessionLocal)

        builtin_documents = list_knowledge_documents(project.id, db, token.user)
        answer = ask_knowledge(project.id, KnowledgeAskRequest(question="卫生间闭水试验怎么验收"), db, token.user)
        uploaded = upload_knowledge_document(
            project.id,
            db,
            token.user,
            _upload_file("custom.md", "# 自定义烟机资料\n\n油烟机止逆阀建议在吊顶和烟道处理前确认型号。"),
        )
        updated = update_knowledge_document(
            project.id,
            uploaded.id,
            KnowledgeDocumentUpdate(
                title="自定义烟机资料更新",
                filename="custom-updated.md",
                content="# 自定义烟机资料更新\n\n止逆阀需要提前确认口径和安装位置。",
                content_type="text/markdown",
            ),
            db,
            token.user,
        )
        knowledge.index_document_by_id(db, uploaded.id)
        db.commit()
        custom_answer = ask_knowledge(project.id, KnowledgeAskRequest(question="止逆阀什么时候确认"), db, token.user)
        detail = get_knowledge_document(project.id, uploaded.id, db, token.user)
        file_response = download_knowledge_document(project.id, uploaded.id, db, token.user)

        assert len(builtin_documents) >= 5
        assert "闭水" in answer.answer
        assert answer.sources
        assert updated.source_type == "upload"
        assert updated.filename == "custom-updated.md"
        assert detail.content.startswith("# 自定义烟机资料更新")
        assert "止逆阀" in custom_answer.answer
        assert file_response.body.decode("utf-8").startswith("# 自定义烟机资料更新")

        delete_knowledge_document(project.id, uploaded.id, db, token.user)
        db.commit()
        remaining = list_knowledge_documents(project.id, db, token.user)
        assert all(document.id != uploaded.id for document in remaining)
    finally:
        db.close()


def test_multi_route_retrieval_keeps_exact_keyword_hit_outside_vector_top(monkeypatch):
    db = SessionLocal()
    try:
        irrelevant = _add_knowledge_chunk(
            db,
            title="乳胶漆资料",
            heading="墙面验收",
            content="乳胶漆墙面应检查色差、开裂和污染。",
        )
        relevant = _add_knowledge_chunk(
            db,
            title="厨房油烟机资料",
            heading="止逆阀采购",
            content="油烟机止逆阀建议在吊顶前购买，并提前确认口径和安装位置。",
        )
        db.commit()

        monkeypatch.setattr(knowledge, "ensure_scoped_embeddings", lambda *args, **kwargs: None)
        monkeypatch.setattr(knowledge, "_vector_candidate_ids", lambda *args, **kwargs: [irrelevant.id])
        monkeypatch.setattr(knowledge, "embed_text", lambda text: [0.0] * knowledge.settings.embedding_dimensions)

        results = knowledge.retrieve(db, "止逆阀什么时候买", None, limit=1)

        assert results
        assert results[0].chunk.id == relevant.id
        assert "止逆阀" in results[0].chunk.content
    finally:
        db.close()


def test_retrieval_query_rewrites_with_history(monkeypatch):
    calls = {}

    def fake_rewrite(question, history=None):
        calls["question"] = question
        calls["history"] = history
        return "卫生间闭水试验怎么验收"

    monkeypatch.setattr(knowledge, "rewrite_search_query", fake_rewrite)

    rewritten = knowledge.build_retrieval_query(
        "这个怎么验收",
        history=[{"role": "user", "content": "卫生间闭水试验"}],
    )

    assert rewritten == "卫生间闭水试验怎么验收"
    assert calls["question"] == "这个怎么验收"


def test_retrieval_query_falls_back_when_rewrite_fails(monkeypatch):
    monkeypatch.setattr(knowledge, "rewrite_search_query", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("fail")))

    rewritten = knowledge.build_retrieval_query(
        "这个怎么验收",
        history=[{"role": "user", "content": "卫生间闭水试验"}],
    )

    assert "卫生间闭水试验" in rewritten
    assert "这个怎么验收" in rewritten


def test_projection_embedding_is_deterministic_and_uses_index_dimensions(monkeypatch):
    monkeypatch.setattr(knowledge.settings, "embedding_index_dimensions", 8)
    vector = [0.1, -0.2, 0.3, 0.4]

    projected = knowledge._project_embedding(vector)

    assert projected == knowledge._project_embedding(vector)
    assert len(projected) == 8
    assert abs(sum(value * value for value in projected) - 1) < 0.000001


def test_rerank_input_includes_document_title(monkeypatch):
    db = SessionLocal()
    captured = {}
    try:
        chunk = _add_knowledge_chunk(
            db,
            title="厨房油烟机资料",
            heading="止逆阀采购",
            content="油烟机止逆阀建议在吊顶前购买。",
        )
        db.commit()

        def fake_rerank(query, documents):
            captured["documents"] = documents
            return [1.0]

        monkeypatch.setattr(knowledge, "rerank", fake_rerank)

        knowledge._apply_rerank("止逆阀", [knowledge.RetrievedChunk(chunk=chunk, score=1)])

        assert "厨房油烟机资料" in captured["documents"][0]
        assert "止逆阀采购" in captured["documents"][0]
    finally:
        db.close()


def test_build_contexts_respects_budget_and_neighbor_window(monkeypatch):
    db = SessionLocal()
    try:
        document = KnowledgeDocument(
            source_type="builtin",
            title="防水验收资料",
            filename="防水验收资料.md",
            content_type="text/markdown",
            content_hash="hash",
            summary="summary",
            content="content",
            index_status="ready",
            index_signature="sig",
        )
        db.add(document)
        db.flush()
        chunks = []
        for index, content in enumerate(["前置说明", "闭水试验需要检查渗漏。" * 20, "后续整改"]):
            chunk = KnowledgeChunk(
                document_id=document.id,
                chunk_index=index,
                heading=f"条文 {index}",
                content=content,
                terms="闭水 防水 验收",
                embedding="闭水:1",
                embedding_provider=knowledge.settings.embedding_provider,
                embedding_model=knowledge._embedding_model_storage_key(),
                embedding_dimensions=knowledge.settings.embedding_dimensions,
                embedding_vector=[0.1] * knowledge.settings.embedding_dimensions,
                embedding_index_dimensions=knowledge.settings.embedding_index_dimensions,
                embedding_index_vector=[0.1] * knowledge.settings.embedding_index_dimensions,
            )
            db.add(chunk)
            chunks.append(chunk)
        db.commit()

        monkeypatch.setattr(knowledge.settings, "rag_neighbor_window", 1)
        monkeypatch.setattr(knowledge.settings, "rag_context_max_chars", 500)
        monkeypatch.setattr(knowledge.settings, "rag_context_per_source_max_chars", 260)

        built = knowledge.build_contexts(db, [knowledge.RetrievedChunk(chunk=chunks[1], score=1)])

        assert len(built.contexts) == 1
        assert "前置说明" in built.contexts[0]
        assert "后续整改" in built.contexts[0]
        assert len(built.contexts[0]) <= 500
    finally:
        db.close()


def test_builtin_knowledge_document_cannot_be_updated():
    db = SessionLocal()
    try:
        token = register(
            UserCreate(email="readonly@example.com", name="屋主", password="password123"),
            db,
        )
        project = create_project(ProjectCreate(name="新家装修", address="杭州"), db, token.user)
        builtin = next(document for document in list_knowledge_documents(project.id, db, token.user) if document.source_type == "builtin")

        try:
            update_knowledge_document(
                project.id,
                builtin.id,
                KnowledgeDocumentUpdate(
                    title="不应更新",
                    filename="readonly.md",
                    content="# 不应更新\n\n内置知识不可编辑。",
                    content_type="text/markdown",
                ),
                db,
                token.user,
            )
        except Exception as exc:
            assert getattr(exc, "status_code", None) == 404
        else:
            raise AssertionError("builtin document should not be editable")
    finally:
        db.close()


def test_repeated_question_does_not_reembed_documents(monkeypatch):
    db = SessionLocal()
    calls = []

    def fake_embed(text: str) -> list[float]:
        calls.append(text)
        return [0.1] * 384

    monkeypatch.setattr(knowledge, "embed_text", fake_embed)
    try:
        token = register(
            UserCreate(email="owner@example.com", name="屋主", password="password123"),
            db,
        )
        project = create_project(ProjectCreate(name="新家装修", address="杭州"), db, token.user)
        _add_knowledge_chunk(
            db,
            title="验收资料",
            heading="防水和阴阳角",
            content="卫生间闭水试验需要检查渗漏，厨房阴阳角需要归方。",
        )
        db.commit()

        ask_knowledge(project.id, KnowledgeAskRequest(question="卫生间闭水试验怎么验收"), db, token.user)
        first_call_count = len(calls)
        ask_knowledge(project.id, KnowledgeAskRequest(question="厨房阴阳角怎么验收"), db, token.user)

        assert first_call_count == 1
        assert len(calls) == first_call_count + 1
        assert calls[-1] == "厨房阴阳角怎么验收"
    finally:
        db.close()


def test_listing_documents_does_not_embed(monkeypatch):
    db = SessionLocal()

    def fail_embed(text: str) -> list[float]:
        raise AssertionError(f"listing should not embed: {text}")

    monkeypatch.setattr(knowledge, "embed_text", fail_embed)
    try:
        token = register(
            UserCreate(email="owner2@example.com", name="屋主", password="password123"),
            db,
        )
        project = create_project(ProjectCreate(name="新家装修", address="杭州"), db, token.user)

        documents = list_knowledge_documents(project.id, db, token.user)

        assert documents
    finally:
        db.close()


def test_list_documents_records_enqueue_failure(monkeypatch, tmp_path):
    docs_dir = tmp_path / "documents"
    docs_dir.mkdir()
    (docs_dir / "01-built-in.md").write_text("# 内置资料\n\n卫生间闭水试验应检查渗漏。", encoding="utf-8")

    def fail_enqueue(document):
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(knowledge, "KNOWLEDGE_DIR", docs_dir)
    monkeypatch.setattr(knowledge, "enqueue_document_index", fail_enqueue)

    db = SessionLocal()
    try:
        documents = knowledge.list_documents(db, project_id=None)
        db.commit()

        assert documents[0].index_status == "failed"
        assert "redis unavailable" in documents[0].index_error
    finally:
        db.close()


def test_trigger_knowledge_index_enqueues_unready_documents(monkeypatch):
    db = SessionLocal()
    enqueued = []

    def fake_enqueue(document):
        enqueued.append(document.filename)

    monkeypatch.setattr(knowledge, "enqueue_document_index", fake_enqueue)

    try:
        token = register(
            UserCreate(email="trigger@example.com", name="屋主", password="password123"),
            db,
        )
        project = create_project(ProjectCreate(name="新家装修", address="杭州"), db, token.user)
        pending = KnowledgeDocument(
            source_type="upload",
            project_id=project.id,
            title="待索引",
            filename="pending.md",
            content_type="text/markdown",
            content_hash="pending-hash",
            summary="summary",
            content="# 待索引\n\n闭水验收。",
            index_status="pending",
        )
        failed = KnowledgeDocument(
            source_type="upload",
            project_id=project.id,
            title="失败",
            filename="failed.md",
            content_type="text/markdown",
            content_hash="failed-hash",
            summary="summary",
            content="# 失败\n\n止逆阀。",
            index_status="failed",
            index_error="old error",
        )
        indexing = KnowledgeDocument(
            source_type="upload",
            project_id=project.id,
            title="索引中",
            filename="indexing.md",
            content_type="text/markdown",
            content_hash="indexing-hash",
            summary="summary",
            content="# 索引中\n\n水电验收。",
            index_status="indexing",
        )
        db.add_all([pending, failed, indexing])
        db.commit()

        result = trigger_knowledge_index(project.id, db, token.user)

        assert result.queued >= 2
        assert result.skipped == 1
        assert result.failed == 0
        assert result.total_unready >= 3
        assert "pending.md" in enqueued
        assert "failed.md" in enqueued
        assert db.query(KnowledgeDocument).filter(KnowledgeDocument.filename == "pending.md").one().index_status == "queued"
        assert db.query(KnowledgeDocument).filter(KnowledgeDocument.filename == "failed.md").one().index_status == "queued"
    finally:
        db.close()


def test_list_documents_syncs_queue_statuses(monkeypatch):
    db = SessionLocal()
    try:
        queued = KnowledgeDocument(
            source_type="builtin",
            title="排队资料",
            filename="queued.md",
            content_type="text/markdown",
            content_hash="queued-hash",
            summary="summary",
            content="# 排队资料\n\n闭水验收。",
            index_status="indexing",
        )
        running = KnowledgeDocument(
            source_type="builtin",
            title="运行资料",
            filename="running.md",
            content_type="text/markdown",
            content_hash="running-hash",
            summary="summary",
            content="# 运行资料\n\n水电验收。",
            index_status="queued",
        )
        db.add_all([queued, running])
        db.commit()
        queued_id = queued.id
        running_id = running.id

        monkeypatch.setattr(knowledge, "ensure_builtin_records", lambda *args, **kwargs: None)
        monkeypatch.setattr(knowledge, "enqueue_document_index", lambda document: None)
        monkeypatch.setattr(
            knowledge,
            "knowledge_index_job_statuses",
            lambda: {queued_id: "queued", running_id: "indexing"},
        )

        documents = knowledge.list_documents(db, project_id=None)
        status_by_filename = {document.filename: document.index_status for document in documents}

        assert status_by_filename["queued.md"] == "queued"
        assert status_by_filename["running.md"] == "indexing"
    finally:
        db.close()


def test_list_documents_uses_lightweight_rows(monkeypatch, tmp_path):
    docs_dir = tmp_path / "documents"
    docs_dir.mkdir()
    (docs_dir / "01-built-in.md").write_text("# 内置资料\n\n卫生间闭水试验应检查渗漏。", encoding="utf-8")

    monkeypatch.setattr(knowledge, "KNOWLEDGE_DIR", docs_dir)
    monkeypatch.setattr(knowledge, "enqueue_document_index", lambda document: None)

    db = SessionLocal()
    try:
        documents = knowledge.list_documents(db, project_id=None)

        assert documents
        assert _document_to_read(documents[0], project_id=1).content is None
    finally:
        db.close()


def test_builtin_records_are_cached_between_list_requests(monkeypatch, tmp_path):
    docs_dir = tmp_path / "documents"
    docs_dir.mkdir()
    document_path = docs_dir / "01-built-in.md"
    document_path.write_text("# 内置资料\n\n卫生间闭水试验应检查渗漏。", encoding="utf-8")
    read_calls = []
    original_read_text = Path.read_text

    def tracking_read_text(path, *args, **kwargs):
        if path == document_path:
            read_calls.append(path.name)
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(knowledge, "KNOWLEDGE_DIR", docs_dir)
    monkeypatch.setattr(knowledge, "enqueue_document_index", lambda document: None)
    monkeypatch.setattr(Path, "read_text", tracking_read_text)

    db = SessionLocal()
    try:
        knowledge.list_documents(db, project_id=None)
        knowledge.list_documents(db, project_id=None)

        assert read_calls == ["01-built-in.md"]
    finally:
        db.close()


def test_upload_marks_pending_and_worker_indexes(monkeypatch):
    db = SessionLocal()
    embed_calls = []

    def fake_embed(text: str) -> list[float]:
        embed_calls.append(text)
        return [0.1] * knowledge.settings.embedding_dimensions

    monkeypatch.setattr(knowledge, "embed_text", fake_embed)
    monkeypatch.setattr(knowledge, "enqueue_document_index", lambda document: None)
    try:
        token = register(
            UserCreate(email="pending@example.com", name="屋主", password="password123"),
            db,
        )
        project = create_project(ProjectCreate(name="新家装修", address="杭州"), db, token.user)

        uploaded = upload_knowledge_document(
            project.id,
            db,
            token.user,
            _upload_file("custom.md", "# 自定义资料\n\n止逆阀需要提前确认。"),
        )

        assert uploaded.index_status == "pending"
        assert embed_calls == []

        knowledge.index_document_by_id(db, uploaded.id)
        db.commit()

        document = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == uploaded.id).one()
        assert document.index_status == "ready"
        assert document.index_signature
        assert embed_calls
    finally:
        db.close()


def test_worker_persists_failed_index_status(monkeypatch):
    db = SessionLocal()
    try:
        document = KnowledgeDocument(
            source_type="builtin",
            title="失败资料",
            filename="fail.md",
            content_type="text/markdown",
            content_hash="hash",
            summary="summary",
            content="# 失败资料\n\n触发失败。",
            index_status="pending",
        )
        db.add(document)
        db.commit()
        document_id = document.id
    finally:
        db.close()

    monkeypatch.setattr(knowledge, "embed_text", lambda text: (_ for _ in ()).throw(RuntimeError("mock failure")))

    try:
        index_knowledge_document(document_id)
    except Exception:
        pass
    else:
        raise AssertionError("worker should raise indexing failure")

    db = SessionLocal()
    try:
        failed = db.query(KnowledgeDocument).filter(KnowledgeDocument.id == document_id).one()
        assert failed.index_status == "failed"
        assert "mock failure" in failed.index_error
    finally:
        db.close()


def test_split_content_limits_long_sections(monkeypatch):
    monkeypatch.setattr(knowledge.settings, "knowledge_chunk_target_chars", 1000)
    monkeypatch.setattr(knowledge.settings, "knowledge_chunk_max_chars", 1500)
    content = "# 长标准\n\n" + "\n".join(f"{index}. " + ("装修验收要求。" * 80) for index in range(20))

    chunks = knowledge._split_content(content)

    assert len(chunks) > 1
    assert max(len(chunk_content) for _, chunk_content in chunks) <= 1500


def test_split_content_splits_oversized_paragraph(monkeypatch):
    monkeypatch.setattr(knowledge.settings, "knowledge_chunk_target_chars", 1000)
    monkeypatch.setattr(knowledge.settings, "knowledge_chunk_max_chars", 1500)
    content = "# 长段落\n\n" + ("防水验收" * 900)

    chunks = knowledge._split_content(content)

    assert len(chunks) > 1
    assert max(len(chunk_content) for _, chunk_content in chunks) <= 1500


def test_split_content_uses_numbered_clauses_as_semantic_units(monkeypatch):
    monkeypatch.setattr(knowledge.settings, "knowledge_chunk_target_chars", 400)
    monkeypatch.setattr(knowledge.settings, "knowledge_chunk_max_chars", 800)
    first_clause = "1.0.1 卫生间防水层完成后应进行闭水试验。" + ("检查是否渗漏。" * 55)
    second_clause = "1.0.2 厨房墙地面铺贴前应核验基层找平和阴阳角。" + ("确认尺寸偏差。" * 55)
    content = f"# 住宅装饰装修\n\n## 一般规定\n\n{first_clause}\n{second_clause}"

    chunks = knowledge._split_content(content)

    assert len(chunks) == 2
    assert chunks[0] == ("一般规定", first_clause)
    assert chunks[1] == ("一般规定", second_clause)


def test_split_content_uses_chinese_headings():
    content = "\n".join(
        [
            "第1章 总则",
            "1.0.1 装修施工前应确认设计和交底。",
            "第2章 瓦工验收",
            "2.0.1 卫生间地面应核验排水坡度。",
        ]
    )

    chunks = knowledge._split_content(content)

    assert chunks == [
        ("第1章 总则", "1.0.1 装修施工前应确认设计和交底。"),
        ("第2章 瓦工验收", "2.0.1 卫生间地面应核验排水坡度。"),
    ]


def test_split_content_preserves_markdown_table_lines():
    content = "\n".join(
        [
            "# 瓦工验收",
            "| 项目 | 要求 |",
            "| --- | --- |",
            "| 闭水 | 24 小时后无渗漏 |",
            "普通说明：闭水完成后再进行下一步。",
        ]
    )

    chunks = knowledge._split_content(content)

    assert "| 项目 | 要求 |\n| --- | --- |\n| 闭水 | 24 小时后无渗漏 |" in chunks[0][1]
    assert "普通说明：闭水完成后再进行下一步。" in chunks[0][1]


def test_split_content_splits_oversized_semantic_unit(monkeypatch):
    monkeypatch.setattr(knowledge.settings, "knowledge_chunk_target_chars", 1000)
    monkeypatch.setattr(knowledge.settings, "knowledge_chunk_max_chars", 1500)
    content = "# 超长条文\n\n1.0.1 " + ("防水验收。" * 700)

    chunks = knowledge._split_content(content)

    assert len(chunks) > 1
    assert max(len(chunk_content) for _, chunk_content in chunks) <= 1500


def test_chunking_config_changes_embedding_storage_key(monkeypatch):
    monkeypatch.setattr(knowledge.settings, "embedding_model", "Qwen/Qwen3-Embedding-8B")
    monkeypatch.setattr(knowledge.settings, "knowledge_chunk_target_chars", 1800)
    monkeypatch.setattr(knowledge.settings, "knowledge_chunk_max_chars", 3200)
    first_key = knowledge._embedding_model_storage_key()

    monkeypatch.setattr(knowledge.settings, "knowledge_chunk_target_chars", 1200)
    second_key = knowledge._embedding_model_storage_key()

    assert first_key != second_key
    assert first_key.startswith("Qwen/Qwen3-Embedding-8B|ck:")
    assert len(first_key) <= 120


def test_independent_builtin_index_keeps_successful_documents(monkeypatch, tmp_path):
    docs_dir = tmp_path / "documents"
    docs_dir.mkdir()
    (docs_dir / "01-ok.md").write_text("# 可索引\n\n卫生间闭水验收。", encoding="utf-8")
    (docs_dir / "02-fail.md").write_text("# 失败文档\n\n触发失败。", encoding="utf-8")

    def fake_embed(text: str) -> list[float]:
        if "失败文档" in text:
            raise RuntimeError("mock embedding failure")
        return [0.1] * 384

    monkeypatch.setattr(knowledge, "KNOWLEDGE_DIR", docs_dir)
    monkeypatch.setattr(knowledge, "embed_text", fake_embed)

    results = knowledge.index_builtin_knowledge_independently(SessionLocal)

    assert [result.ok for result in results] == [True, False]

    db = SessionLocal()
    try:
        ok_document = db.query(KnowledgeDocument).filter(KnowledgeDocument.filename == "01-ok.md").one()
        failed_document = db.query(KnowledgeDocument).filter(KnowledgeDocument.filename == "02-fail.md").one()
        assert db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == ok_document.id).count() > 0
        assert db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == failed_document.id).count() == 0
    finally:
        db.close()


def test_independent_builtin_index_can_limit_filenames(monkeypatch, tmp_path):
    docs_dir = tmp_path / "documents"
    docs_dir.mkdir()
    (docs_dir / "01-selected.md").write_text("# 已选择\n\n卫生间闭水验收。", encoding="utf-8")
    (docs_dir / "02-skipped.md").write_text("# 未选择\n\n不应索引。", encoding="utf-8")
    embed_calls = []

    def fake_embed(text: str) -> list[float]:
        embed_calls.append(text)
        return [0.1] * knowledge.settings.embedding_dimensions

    monkeypatch.setattr(knowledge, "KNOWLEDGE_DIR", docs_dir)
    monkeypatch.setattr(knowledge, "embed_text", fake_embed)

    results = knowledge.index_builtin_knowledge_independently(SessionLocal, filenames={"01-selected.md"})

    assert [result.filename for result in results] == ["01-selected.md"]
    assert all("未选择" not in call for call in embed_calls)

    db = SessionLocal()
    try:
        assert db.query(KnowledgeDocument).filter(KnowledgeDocument.filename == "01-selected.md").count() == 1
        assert db.query(KnowledgeDocument).filter(KnowledgeDocument.filename == "02-skipped.md").count() == 0
    finally:
        db.close()


def test_embedding_budget_splits_before_embedding(monkeypatch):
    db = SessionLocal()
    embedded_texts = []
    content = "# 超长资料\n\n" + ("防水验收" * 350)

    def fake_embed(text: str) -> list[float]:
        embedded_texts.append(text)
        return [0.1] * knowledge.settings.embedding_dimensions

    monkeypatch.setattr(knowledge.settings, "knowledge_chunk_target_chars", 2000)
    monkeypatch.setattr(knowledge.settings, "knowledge_chunk_max_chars", 4000)
    monkeypatch.setattr(knowledge.settings, "knowledge_embedding_max_chars", 1000)
    monkeypatch.setattr(knowledge, "embed_text", fake_embed)

    try:
        document = KnowledgeDocument(
            source_type="builtin",
            title="超长资料",
            filename="long.md",
            content_type="text/markdown",
            content_hash=sha256(content.encode("utf-8")).hexdigest(),
            summary="summary",
            content=content,
            index_status="pending",
        )
        db.add(document)
        db.flush()

        knowledge.index_document_by_id(db, document.id)
        db.commit()

        assert len(embedded_texts) > 1
        assert max(len(text) for text in embedded_texts) <= 1000
        assert db.query(KnowledgeChunk).filter(KnowledgeChunk.document_id == document.id).count() == len(embedded_texts)
    finally:
        db.close()


def test_index_document_commits_before_embedding(monkeypatch):
    db = SessionLocal()
    content = "# 索引事务\n\n卫生间闭水验收。"
    observed_statuses = []

    def fake_embed(text: str) -> list[float]:
        other_db = SessionLocal()
        try:
            status = other_db.query(KnowledgeDocument.index_status).filter(KnowledgeDocument.filename == "tx.md").scalar()
            observed_statuses.append(status)
        finally:
            other_db.close()
        return [0.1] * knowledge.settings.embedding_dimensions

    monkeypatch.setattr(knowledge, "embed_text", fake_embed)

    try:
        document = KnowledgeDocument(
            source_type="builtin",
            title="索引事务",
            filename="tx.md",
            content_type="text/markdown",
            content_hash=sha256(content.encode("utf-8")).hexdigest(),
            summary="summary",
            content=content,
            index_status="pending",
        )
        db.add(document)
        db.commit()

        knowledge.index_document_by_id(db, document.id)
        db.commit()

        assert observed_statuses == ["indexing"]
        assert db.query(KnowledgeDocument).filter(KnowledgeDocument.id == document.id).one().index_status == "ready"
    finally:
        db.close()


def test_document_index_signature_ignores_other_builtin_files(monkeypatch, tmp_path):
    docs_dir = tmp_path / "documents"
    docs_dir.mkdir()
    first = docs_dir / "01-a.md"
    second = docs_dir / "02-b.md"
    first.write_text("# A\n\n闭水验收。", encoding="utf-8")
    second.write_text("# B\n\n找平验收。", encoding="utf-8")
    monkeypatch.setattr(knowledge, "KNOWLEDGE_DIR", docs_dir)
    content_hash = sha256(first.read_text(encoding="utf-8").encode("utf-8")).hexdigest()

    before = knowledge._document_index_signature(content_hash)
    second.write_text("# B\n\n找平验收。新增内容。", encoding="utf-8")
    after = knowledge._document_index_signature(content_hash)

    assert before == after


def test_embedding_signature_normalizes_same_qwen_model(monkeypatch):
    content_hash = sha256(b"same document").hexdigest()
    monkeypatch.setattr(knowledge.settings, "embedding_model", "./models/Qwen3-Embedding-8B")
    monkeypatch.setattr(knowledge.settings, "embedding_api_base", "https://local.example/v1")
    local_signature = knowledge._document_index_signature(content_hash)
    local_storage_key = knowledge._embedding_model_storage_key()

    monkeypatch.setattr(knowledge.settings, "embedding_model", "Qwen/Qwen3-Embedding-8B")
    monkeypatch.setattr(knowledge.settings, "embedding_api_base", "https://api-inference.modelscope.cn/v1")
    remote_signature = knowledge._document_index_signature(content_hash)
    remote_storage_key = knowledge._embedding_model_storage_key()

    assert local_signature == remote_signature
    assert local_storage_key == remote_storage_key


def test_reusable_chunks_refresh_document_metadata(monkeypatch):
    db = SessionLocal()
    content = "# 可复用\n\n闭水验收。"
    monkeypatch.setattr(knowledge.settings, "embedding_model", "./models/Qwen3-Embedding-8B")
    old_storage_key = knowledge._embedding_model_storage_key()
    try:
        document = KnowledgeDocument(
            source_type="builtin",
            title="可复用",
            filename="reuse.md",
            content_type="text/markdown",
            content_hash=sha256(content.encode("utf-8")).hexdigest(),
            summary="summary",
            content=content,
            index_status="pending",
            index_signature=None,
        )
        db.add(document)
        db.flush()
        db.add(
            KnowledgeChunk(
                document_id=document.id,
                chunk_index=0,
                heading="可复用",
                content="闭水验收。",
                terms="闭水 验收",
                embedding=knowledge.term_signature("可复用 闭水验收。"),
                embedding_provider=knowledge.settings.embedding_provider,
                embedding_model=old_storage_key,
                embedding_dimensions=knowledge.settings.embedding_dimensions,
                embedding_vector=[0.1] * knowledge.settings.embedding_dimensions,
                embedding_index_dimensions=knowledge.settings.embedding_index_dimensions,
                embedding_index_vector=[0.1] * knowledge.settings.embedding_index_dimensions,
            )
        )
        db.flush()
        monkeypatch.setattr(knowledge.settings, "embedding_model", "Qwen/Qwen3-Embedding-8B")
        document = (
            db.query(KnowledgeDocument)
            .options(joinedload(KnowledgeDocument.chunks))
            .filter(KnowledgeDocument.id == document.id)
            .one()
        )

        assert knowledge._mark_pending_if_stale(document) is False
        assert document.index_status == "ready"
        assert document.index_signature == knowledge._document_index_signature(document.content_hash)
        assert document.chunks[0].embedding_model == knowledge._embedding_model_storage_key()
    finally:
        db.close()


def test_stream_knowledge_answer_emits_status_sources_and_answer():
    db = SessionLocal()
    try:
        token = register(
            UserCreate(email="stream@example.com", name="屋主", password="password123"),
            db,
        )
        project = create_project(ProjectCreate(name="新家装修", address="杭州"), db, token.user)
        knowledge.index_builtin_knowledge_independently(SessionLocal)

        body = "".join(_knowledge_event_stream(
            project.id,
            KnowledgeAskRequest(question="卫生间闭水试验怎么验收"),
            db,
        ))

        assert "event: status" in body
        assert "正在理解问题" in body
        assert "event: sources" in body
        assert "event: delta" in body
        assert "event: done" in body
        assert "闭水" in body
    finally:
        db.close()
