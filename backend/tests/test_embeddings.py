import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["EMBEDDING_PROVIDER"] = "local"
os.environ["EMBEDDING_DIMENSIONS"] = "384"
os.environ["RERANK_PROVIDER"] = "none"
os.environ["LLM_PROVIDER"] = "none"

from app.core.config import settings
from app.services import embeddings, llm
from app.services.embeddings import cosine_similarity, embed_text, rerank, tokenize
from app.services.llm import generate_answer
from app.services.openai_client import post_openai_compatible_json


class _EmbeddingItem:
    embedding = [0.1, 0.2, 0.3]


class _EmbeddingResponse:
    data = [_EmbeddingItem()]


class _EmbeddingsResource:
    def __init__(self):
        self.request = None

    def create(self, **kwargs):
        self.request = kwargs
        return _EmbeddingResponse()


class _Message:
    content = "按引用资料回答。"


class _Choice:
    message = _Message()


class _ChatResponse:
    choices = [_Choice()]


class _ChatCompletionsResource:
    def __init__(self):
        self.request = None

    def create(self, **kwargs):
        self.request = kwargs
        return _ChatResponse()


class _ChatResource:
    def __init__(self):
        self.completions = _ChatCompletionsResource()


class _FakeOpenAIClient:
    def __init__(self):
        self.embeddings = _EmbeddingsResource()
        self.chat = _ChatResource()


def _patch_openai_client(monkeypatch):
    client = _FakeOpenAIClient()
    monkeypatch.setattr(embeddings, "build_openai_client", lambda *args, **kwargs: client)
    monkeypatch.setattr(llm, "build_openai_client", lambda *args, **kwargs: client)
    return client


def test_local_embedding_is_deterministic_and_searchable():
    left = embed_text("卫生间闭水试验和防水验收")
    right = embed_text("闭水试验需要检查卫生间是否渗漏")
    unrelated = embed_text("中央空调报价和安装")

    assert len(left) == 384
    assert left == embed_text("卫生间闭水试验和防水验收")
    assert cosine_similarity(left, right) > cosine_similarity(left, unrelated)
    assert {"闭水", "防水", "卫生间"}.issubset(set(tokenize("卫生间闭水试验")))


def test_alias_keyword_keeps_original_term():
    assert {"止逆阀", "油烟机", "厨房", "安装"}.issubset(set(tokenize("止逆阀什么时候购买")))


def test_rerank_disabled_by_default():
    assert rerank("闭水怎么验收", ["卫生间闭水验收"]) is None


def test_llm_disabled_by_default():
    assert generate_answer("闭水怎么验收", ["[1] 卫生间闭水验收"]) is None


def test_embedding_uses_openai_sdk(monkeypatch):
    client = _patch_openai_client(monkeypatch)
    monkeypatch.setattr(settings, "embedding_provider", "openai_compatible")
    monkeypatch.setattr(settings, "embedding_model", "Qwen/Qwen3-Embedding-8B")
    monkeypatch.setattr(settings, "embedding_api_base", "https://api-inference.modelscope.cn/v1")

    assert embeddings.embed_text("闭水验收") == [0.1, 0.2, 0.3]
    assert client.embeddings.request == {
        "model": "Qwen/Qwen3-Embedding-8B",
        "input": "闭水验收",
        "encoding_format": "float",
    }


def test_rerank_uses_openai_sdk_custom_post(monkeypatch):
    _patch_openai_client(monkeypatch)
    request = {}

    def fake_post(api_base, api_key, timeout, path, body):
        request.update({"api_base": api_base, "api_key": api_key, "timeout": timeout, "path": path, "body": body})
        return {"results": [{"index": 0, "relevance_score": 0.91}]}

    monkeypatch.setattr(embeddings, "post_openai_compatible_json", fake_post)
    monkeypatch.setattr(settings, "rerank_provider", "openai_compatible")
    monkeypatch.setattr(settings, "rerank_model", "bge-reranker-v2.5-gemma2-lightweight")
    monkeypatch.setattr(settings, "rerank_api_base", "https://api-inference.modelscope.cn/v1")
    monkeypatch.setattr(settings, "rerank_api_key", None)
    monkeypatch.setattr(settings, "modelscope_api_key", None)

    assert embeddings.rerank("闭水", ["卫生间闭水"]) == [0.91]
    assert request == {
        "api_base": "https://api-inference.modelscope.cn/v1",
        "api_key": None,
        "timeout": 20,
        "path": "/rerank",
        "body": {
            "model": "bge-reranker-v2.5-gemma2-lightweight",
            "query": "闭水",
            "documents": ["卫生间闭水"],
        },
    }


def test_llm_uses_openai_sdk(monkeypatch):
    client = _patch_openai_client(monkeypatch)
    monkeypatch.setattr(settings, "llm_provider", "openai_compatible")
    monkeypatch.setattr(settings, "llm_model", "Qwen/Qwen3")
    monkeypatch.setattr(settings, "llm_api_base", "https://api-inference.modelscope.cn/v1")

    assert llm.generate_answer("闭水怎么验收", ["[1] 卫生间闭水验收"]) == "按引用资料回答。"
    assert client.chat.completions.request["model"] == "Qwen/Qwen3"
    assert client.chat.completions.request["messages"][0]["role"] == "system"


def test_openai_compatible_post_filters_non_string_headers(monkeypatch):
    request = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"scores": [0.8]}

    class FakeHttpClient:
        def post(self, url, *, headers, json):
            request.update({"url": url, "headers": headers, "json": json})
            return FakeResponse()

    class FakeClient:
        base_url = "https://api-inference.modelscope.cn/v1/"
        default_headers = {
            "Authorization": "Bearer token",
            "OpenAI-Organization": object(),
            "Content-Type": "application/json",
        }
        _client = FakeHttpClient()

    monkeypatch.setattr("app.services.openai_client.build_openai_client", lambda *args, **kwargs: FakeClient())

    assert post_openai_compatible_json("https://api-inference.modelscope.cn/v1", "token", 20, "/rerank", {}) == {
        "scores": [0.8]
    }
    assert request["url"] == "https://api-inference.modelscope.cn/v1/rerank"
    assert request["headers"] == {"Authorization": "Bearer token", "Content-Type": "application/json"}
