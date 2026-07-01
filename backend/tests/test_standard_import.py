import os
import io
import zipfile

import httpx

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["EMBEDDING_PROVIDER"] = "local"
os.environ["EMBEDDING_DIMENSIONS"] = "384"
os.environ["RERANK_PROVIDER"] = "none"
os.environ["LLM_PROVIDER"] = "none"

from app.scripts import import_standard_documents as importer
from app.services.mineru import MinerUClient


def test_raw_relative_path_resolves_under_knowledge_dir(monkeypatch, tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    monkeypatch.setattr(importer, "KNOWLEDGE_DIR", knowledge_dir)

    document = importer.StandardDocument(
        id="GB-TEST",
        title="GB TEST 测试标准",
        output="70-GB-TEST.md",
        local_path="raw/GB-TEST.pdf",
    )

    assert document.raw_path == knowledge_dir / "raw" / "GB-TEST.pdf"


def test_load_manifest_supports_metadata_fields(tmp_path):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        """
        [
          {
            "id": "GB-TEST",
            "title": "GB TEST 测试标准",
            "output": "70-GB-TEST.md",
            "source_url": "https://std.samr.gov.cn/search/std?q=GB-TEST",
            "download_url": "https://example.com/GB-TEST.pdf",
            "local_path": "raw/GB-TEST.pdf",
            "category": "core_acceptance",
            "priority": 1,
            "tags": ["验收", "测试"]
          }
        ]
        """,
        encoding="utf-8",
    )

    documents = importer.load_manifest(manifest)

    assert documents[0].category == "core_acceptance"
    assert documents[0].priority == 1
    assert documents[0].tags == ["验收", "测试"]
    assert documents[0].source_url == "https://std.samr.gov.cn/search/std?q=GB-TEST"
    assert documents[0].download_url == "https://example.com/GB-TEST.pdf"


def test_source_url_is_not_used_as_download_url(monkeypatch, tmp_path):
    calls = []
    document = importer.StandardDocument(
        id="GB-TEST",
        title="GB TEST 测试标准",
        output="70-GB-TEST.md",
        source_url="https://std.samr.gov.cn/search/std?q=GB-TEST",
        local_path=str(tmp_path / "missing.pdf"),
    )
    monkeypatch.setattr(importer, "download_file", lambda *args, **kwargs: calls.append(args))

    try:
        importer.ensure_raw_file(document)
    except FileNotFoundError as exc:
        assert "download_url" in str(exc)
        assert calls == []
    else:
        raise AssertionError("ensure_raw_file should require download_url for automatic downloads")


def test_filter_documents_by_category_and_priority():
    documents = [
        importer.StandardDocument(
            id="A",
            title="A",
            output="A.md",
            category="core_acceptance",
            priority=1,
        ),
        importer.StandardDocument(
            id="B",
            title="B",
            output="B.md",
            category="material",
            priority=2,
        ),
        importer.StandardDocument(
            id="C",
            title="C",
            output="C.md",
            category="material",
            priority=3,
        ),
    ]

    filtered = importer.filter_documents(documents, categories=["material"], max_priority=2)

    assert [document.id for document in filtered] == ["B"]


def test_download_file_retries_transient_ssl_error(monkeypatch, tmp_path):
    calls = []

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def request(self, method, url, **kwargs):
            calls.append((method, url))
            request = httpx.Request(method, url)
            if len(calls) == 1:
                raise httpx.ConnectError(
                    "[SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol",
                    request=request,
                )
            return httpx.Response(200, content=b"%PDF test", request=request)

    monkeypatch.setattr(importer.httpx, "Client", FakeClient)
    monkeypatch.setattr(importer.settings, "mineru_retry_attempts", 2)
    monkeypatch.setattr(importer.settings, "mineru_retry_backoff_seconds", 0)

    output_path = tmp_path / "raw" / "GB-TEST.pdf"
    importer.download_file("https://example.com/GB-TEST.pdf", output_path)

    assert output_path.read_bytes() == b"%PDF test"
    assert len(calls) == 2


def test_download_markdown_falls_back_after_httpx_transport_error(monkeypatch, tmp_path):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w") as archive:
        archive.writestr("result/full.md", "# 标准正文\n\n内容")

    calls = []
    client = MinerUClient(token="test-token")
    client.download_retry_attempts = 1
    client.download_retry_backoff_seconds = 0

    def fail_httpx(full_zip_url, tmp_path):
        calls.append("httpx")
        raise httpx.ConnectError("ssl eof", request=httpx.Request("GET", full_zip_url))

    def succeed_urllib(full_zip_url, tmp_path):
        calls.append("urllib")
        tmp_path.write_bytes(zip_buffer.getvalue())

    monkeypatch.setattr(client, "_download_result_zip_httpx", fail_httpx)
    monkeypatch.setattr(client, "_download_result_zip_urllib", succeed_urllib)

    output_path = client.download_markdown("https://example.com/result.zip", tmp_path, "GB-TEST.md")

    assert calls == ["httpx", "urllib"]
    assert output_path.read_text(encoding="utf-8") == "# 标准正文\n\n内容"


def test_parse_documents_writes_manifest_output(monkeypatch, tmp_path):
    raw_dir = tmp_path / "raw"
    documents_dir = tmp_path / "documents"
    mineru_output = tmp_path / ".mineru-output"
    raw_dir.mkdir()
    documents_dir.mkdir()
    raw_file = raw_dir / "GB-TEST.pdf"
    raw_file.write_bytes(b"%PDF test")

    monkeypatch.setattr(importer, "KNOWLEDGE_DIR", tmp_path)
    monkeypatch.setattr(importer, "DOCUMENTS_DIR", documents_dir)

    class FakeMinerUClient:
        def parse_local_files(self, files, output_dir):
            assert files == [raw_file]
            output_dir.mkdir(parents=True, exist_ok=True)
            parsed = mineru_output / "GB-TEST.md"
            parsed.parent.mkdir(parents=True, exist_ok=True)
            parsed.write_text("# 原文标题\n\n标准正文", encoding="utf-8")
            return [parsed]

    monkeypatch.setattr(importer, "MinerUClient", FakeMinerUClient)

    document = importer.StandardDocument(
        id="GB-TEST",
        title="GB TEST 测试标准",
        output="70-GB-TEST.md",
        local_path=str(raw_file),
    )
    output_paths = importer.parse_documents([document])

    assert output_paths == [documents_dir / "70-GB-TEST.md"]
    content = output_paths[0].read_text(encoding="utf-8")
    assert content.startswith("# GB TEST 测试标准")
    assert "标准正文" in content


def test_index_builtin_documents_does_not_raise_by_default(monkeypatch, tmp_path, capsys):
    output_path = tmp_path / "70-GB-TEST.md"
    output_path.write_text("# 测试", encoding="utf-8")
    calls = []

    def fake_index(session_factory, filenames=None):
        calls.append(filenames)
        return [
            importer.KnowledgeIndexResult("70-GB-TEST.md", "测试", True),
            importer.KnowledgeIndexResult("71-GB-FAIL.md", "失败", False, "mock failure"),
        ]

    monkeypatch.setattr(importer, "index_builtin_knowledge_independently", fake_index)

    ok = importer.index_builtin_documents([output_path])

    captured = capsys.readouterr()
    assert ok is False
    assert calls == [{"70-GB-TEST.md"}]
    assert "indexed summary: success=1 failed=1" in captured.out
    assert "索引部分失败" in captured.err


def test_index_builtin_documents_strict_raises(monkeypatch, tmp_path):
    output_path = tmp_path / "70-GB-TEST.md"
    output_path.write_text("# 测试", encoding="utf-8")

    def fake_index(session_factory, filenames=None):
        return [importer.KnowledgeIndexResult("70-GB-TEST.md", "测试", False, "mock failure")]

    monkeypatch.setattr(importer, "index_builtin_knowledge_independently", fake_index)

    try:
        importer.index_builtin_documents([output_path], strict=True)
    except RuntimeError as exc:
        assert "1 个知识库文件索引失败" in str(exc)
    else:
        raise AssertionError("strict index should raise")
