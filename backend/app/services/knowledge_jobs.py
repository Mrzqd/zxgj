from redis import Redis
from rq import Queue
from rq.exceptions import NoSuchJobError
from rq.job import Job

from app.core.config import settings
from app.db.session import SessionLocal


def _redis_connection() -> Redis:
    return Redis.from_url(settings.redis_url)


def _queue(connection: Redis | None = None) -> Queue:
    return Queue(settings.rq_queue_name, connection=connection or _redis_connection())


def _job_status_value(job: Job) -> str:
    status = job.get_status(refresh=True)
    return getattr(status, "value", str(status))


def enqueue_knowledge_index(document_id: int, signature: str | None = None) -> str | None:
    connection = _redis_connection()
    job_id = f"knowledge-index-{document_id}-{signature}" if signature else None
    if job_id:
        try:
            existing = Job.fetch(job_id, connection=connection)
        except NoSuchJobError:
            existing = None
        if existing is not None:
            if _job_status_value(existing) in {"queued", "started", "deferred", "scheduled"}:
                return existing.id
            existing.delete()
    job = _queue(connection).enqueue(
        "app.services.knowledge_jobs.index_knowledge_document",
        document_id,
        job_id=job_id,
    )
    return job.id


def _document_id_from_job_id(job_id: str) -> int | None:
    if not job_id.startswith("knowledge-index-"):
        return None
    rest = job_id.removeprefix("knowledge-index-")
    raw_id = rest.split("-", 1)[0]
    try:
        return int(raw_id)
    except ValueError:
        return None


def knowledge_index_job_statuses() -> dict[int, str]:
    connection = _redis_connection()
    queue = _queue(connection)
    statuses: dict[int, str] = {}
    for job_id in queue.job_ids:
        document_id = _document_id_from_job_id(job_id)
        if document_id is not None:
            statuses[document_id] = "queued"
    for worker_key in connection.smembers(f"rq:workers:{settings.rq_queue_name}"):
        worker_name = worker_key.decode("utf-8")
        redis_key = worker_name if worker_name.startswith("rq:worker:") else f"rq:worker:{worker_name}"
        state = connection.hget(redis_key, "state")
        if state != b"busy":
            continue
        current_job = connection.hget(redis_key, "current_job")
        if not current_job:
            continue
        document_id = _document_id_from_job_id(current_job.decode("utf-8"))
        if document_id is not None:
            statuses[document_id] = "indexing"
    return statuses


def index_knowledge_document(document_id: int) -> None:
    from app.services.knowledge import index_document_by_id, mark_document_index_failed

    db = SessionLocal()
    try:
        index_document_by_id(db, document_id)
        db.commit()
    except Exception as exc:
        db.rollback()
        try:
            mark_document_index_failed(db, document_id, str(exc))
            db.commit()
        except Exception:
            db.rollback()
        raise
    finally:
        db.close()
