import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"
os.environ["SECRET_KEY"] = "test-secret"
os.environ["EMBEDDING_PROVIDER"] = "local"
os.environ["EMBEDDING_DIMENSIONS"] = "384"
os.environ["RERANK_PROVIDER"] = "none"
os.environ["LLM_PROVIDER"] = "none"

from app.services import knowledge_jobs


def test_enqueue_job_id_is_rq_compatible(monkeypatch):
    captured = {}

    class FakeQueue:
        def enqueue(self, func, document_id, job_id=None):
            captured.update({"func": func, "document_id": document_id, "job_id": job_id})

            class Job:
                id = job_id

            return Job()

    monkeypatch.setattr(knowledge_jobs, "_redis_connection", lambda: object())
    monkeypatch.setattr(knowledge_jobs.Job, "fetch", lambda *args, **kwargs: (_ for _ in ()).throw(knowledge_jobs.NoSuchJobError))
    monkeypatch.setattr(knowledge_jobs, "_queue", lambda connection=None: FakeQueue())

    job_id = knowledge_jobs.enqueue_knowledge_index(12, "abc123")

    assert job_id == "knowledge-index-12-abc123"
    assert ":" not in job_id
    assert captured["func"] == "app.services.knowledge_jobs.index_knowledge_document"
    assert captured["document_id"] == 12


def test_document_id_from_job_id():
    assert knowledge_jobs._document_id_from_job_id("knowledge-index-42-abcdef") == 42
    assert knowledge_jobs._document_id_from_job_id("other-42-abcdef") is None


def test_runtime_statuses_use_live_worker_current_job(monkeypatch):
    class FakeConnection:
        def smembers(self, key):
            assert key == "rq:workers:knowledge-index"
            return {b"rq:worker:worker-1"}

        def hget(self, key, field):
            assert key == "rq:worker:worker-1"
            if field == "state":
                return b"busy"
            assert field == "current_job"
            return b"knowledge-index-8-running"

    class FakeQueue:
        job_ids = ["knowledge-index-7-queued"]

    monkeypatch.setattr(knowledge_jobs, "_redis_connection", lambda: FakeConnection())
    monkeypatch.setattr(knowledge_jobs, "_queue", lambda connection=None: FakeQueue())

    assert knowledge_jobs.knowledge_index_job_statuses() == {7: "queued", 8: "indexing"}
