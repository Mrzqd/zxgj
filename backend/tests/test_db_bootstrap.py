import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["EMBEDDING_PROVIDER"] = "local"
os.environ["EMBEDDING_DIMENSIONS"] = "384"
os.environ["RERANK_PROVIDER"] = "none"
os.environ["LLM_PROVIDER"] = "none"

from app.db import bootstrap


def test_ivfflat_index_dimension_limit():
    assert not bootstrap.should_create_ivfflat_index(4096)
    assert bootstrap.should_create_ivfflat_index(1536)
    assert bootstrap.should_create_ivfflat_index(2000)


def test_validated_dimensions_rejects_invalid_values():
    assert bootstrap._validated_dimensions(1536, "TEST") == 1536
    try:
        bootstrap._validated_dimensions(0, "TEST")
    except ValueError as exc:
        assert "positive integer" in str(exc)
    else:
        raise AssertionError("invalid dimensions should fail")
