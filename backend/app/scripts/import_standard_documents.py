from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
from pathlib import Path
import shutil
import sys

import httpx

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.http_retry import request_with_retry
from app.services.knowledge import KnowledgeIndexResult, index_builtin_knowledge_independently
from app.services.mineru import MinerUClient


BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent
KNOWLEDGE_DIR = BACKEND_DIR / "app" / "knowledge"
RAW_DIR = KNOWLEDGE_DIR / "raw"
DOCUMENTS_DIR = KNOWLEDGE_DIR / "documents"
MANIFEST_PATH = KNOWLEDGE_DIR / "standards-manifest.json"


@dataclass
class StandardDocument:
    id: str
    title: str
    output: str
    source_url: str = ""
    download_url: str = ""
    local_path: str = ""
    notes: str = ""
    category: str = "other"
    priority: int = 2
    tags: list[str] = field(default_factory=list)

    @property
    def raw_path(self) -> Path:
        if self.local_path:
            path = Path(self.local_path)
            if path.is_absolute():
                return path
            if path.parts and path.parts[0] == "raw":
                return KNOWLEDGE_DIR / path
            return REPO_DIR / path
        return RAW_DIR / f"{self.id}.pdf"

    @property
    def output_path(self) -> Path:
        return DOCUMENTS_DIR / self.output


def load_manifest(path: Path = MANIFEST_PATH) -> list[StandardDocument]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return [StandardDocument(**item) for item in data]


def filter_documents(
    documents: list[StandardDocument],
    *,
    ids: list[str] | None = None,
    categories: list[str] | None = None,
    max_priority: int | None = None,
) -> list[StandardDocument]:
    filtered = documents
    if ids:
        wanted = set(ids)
        filtered = [document for document in filtered if document.id in wanted]
    if categories:
        wanted_categories = set(categories)
        filtered = [document for document in filtered if document.category in wanted_categories]
    if max_priority is not None:
        filtered = [document for document in filtered if document.priority <= max_priority]
    return filtered


def print_document_list(documents: list[StandardDocument]) -> None:
    for document in documents:
        tags = ",".join(document.tags)
        print(f"P{document.priority}\t{document.category}\t{document.id}\t{document.title}\t{tags}\t{document.source_url}")


def download_file(url: str, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        response = request_with_retry(
            client,
            "GET",
            url,
            operation=f"下载标准原文 {url}",
            attempts=settings.mineru_retry_attempts,
            backoff_seconds=settings.mineru_retry_backoff_seconds,
        )
        output_path.write_bytes(response.content)


def ensure_raw_file(document: StandardDocument, *, force_download: bool = False) -> Path:
    raw_path = document.raw_path
    if raw_path.exists() and not force_download:
        return raw_path
    if not document.download_url:
        raise FileNotFoundError(
            f"{document.id} 缺少本地文件：{raw_path}。请将标准原文放到该路径，或在 manifest 中补 download_url。"
        )
    download_file(document.download_url, raw_path)
    return raw_path


def add_metadata(document: StandardDocument, markdown_path: Path) -> None:
    content = markdown_path.read_text(encoding="utf-8")
    source = document.source_url or document.download_url or str(document.raw_path)
    header = (
        f"# {document.title}\n\n"
        f"来源：{source}\n\n"
        f"说明：本文由 MinerU 从本地标准文件解析生成，用于装修管家知识库检索。"
        f"标准适用性、现行状态和正式条文以官方发布文本为准。\n\n"
    )
    if content.lstrip().startswith(f"# {document.title}"):
        return
    markdown_path.write_text(f"{header}{content}", encoding="utf-8")


def parse_documents(documents: list[StandardDocument], *, force_parse: bool = False) -> list[Path]:
    pending: list[StandardDocument] = []
    raw_files: list[Path] = []
    for document in documents:
        if document.output_path.exists() and not force_parse:
            continue
        raw_file = ensure_raw_file(document)
        pending.append(document)
        raw_files.append(raw_file)
    if not pending:
        return [document.output_path for document in documents if document.output_path.exists()]

    client = MinerUClient()
    tmp_output_dir = KNOWLEDGE_DIR / ".mineru-output"
    tmp_output_dir.mkdir(parents=True, exist_ok=True)
    parsed_paths = client.parse_local_files(raw_files, tmp_output_dir)

    output_paths: list[Path] = []
    for document, parsed_path in zip(pending, parsed_paths, strict=True):
        document.output_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(parsed_path), document.output_path)
        add_metadata(document, document.output_path)
        output_paths.append(document.output_path)
    return [document.output_path for document in documents if document.output_path.exists()]


def index_builtin_documents(output_paths: list[Path], *, strict: bool = False) -> bool:
    filenames = {path.name for path in output_paths}
    results = index_builtin_knowledge_independently(SessionLocal, filenames=filenames)
    succeeded = [result for result in results if result.ok]
    failed = [result for result in results if not result.ok]
    for result in succeeded:
        print(f"indexed: {result.filename}")
    for result in failed:
        print(f"index failed: {result.filename} -> {result.error}", file=sys.stderr)
    print(f"indexed summary: success={len(succeeded)} failed={len(failed)}")
    if failed:
        message = f"{len(failed)} 个知识库文件索引失败，其他文件已独立提交"
        if strict:
            raise RuntimeError(message)
        print(f"索引部分失败：{message}", file=sys.stderr)
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="下载并用 MinerU 解析国家装修标准到内置知识库")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--ids", nargs="*", help="只处理指定标准 id，例如 GB-50327-2001")
    parser.add_argument("--categories", nargs="*", help="只处理指定分类，例如 core_acceptance material")
    parser.add_argument("--max-priority", type=int, help="只处理优先级小于等于该值的标准，例如 1")
    parser.add_argument("--list", action="store_true", help="列出筛选后的标准清单，不执行导入")
    parser.add_argument("--download-only", action="store_true", help="只下载原始文件，不调用 MinerU")
    parser.add_argument("--index", action="store_true", help="解析后立即向量化内置知识库")
    parser.add_argument("--strict-index", action="store_true", help="索引存在失败时返回失败状态")
    parser.add_argument("--force-download", action="store_true", help="即使 raw 文件已存在也重新下载")
    parser.add_argument("--force-parse", action="store_true", help="即使 Markdown 已存在也重新解析")
    args = parser.parse_args(argv)

    documents = load_manifest(args.manifest)
    documents = filter_documents(
        documents,
        ids=args.ids,
        categories=args.categories,
        max_priority=args.max_priority,
    )
    if not documents:
        print("没有匹配的标准文档", file=sys.stderr)
        return 1
    if args.list:
        print_document_list(documents)
        return 0

    try:
        for document in documents:
            raw_path = ensure_raw_file(document, force_download=args.force_download)
            print(f"raw: {document.id} -> {raw_path}")

        if args.download_only:
            return 0

        output_paths = parse_documents(documents, force_parse=args.force_parse)
        for output_path in output_paths:
            print(f"markdown: {output_path}")

        if args.index:
            index_ok = index_builtin_documents(output_paths, strict=args.strict_index)
            print("indexed: builtin knowledge documents")
            if not index_ok:
                return 0
    except Exception as exc:
        print(f"导入失败：{exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
