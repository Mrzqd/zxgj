import json

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import Response, StreamingResponse

from app.api.deps import CurrentUser, DbSession, require_project_member
from app.schemas import (
    KnowledgeAnswerRead,
    KnowledgeAskRequest,
    KnowledgeDocumentRead,
    KnowledgeDocumentUpdate,
    KnowledgeIndexTriggerRead,
    KnowledgeSourceRead,
)
from app.services.knowledge import (
    RetrievedChunk,
    build_fallback_answer,
    build_indexing_answer,
    build_no_results_answer,
    build_rag_answer,
    build_rag_context,
    delete_document,
    get_document,
    ingest_upload,
    list_documents,
    stream_rag_answer,
    trigger_unready_index_jobs,
    update_upload_document,
)

router = APIRouter(prefix="/projects/{project_id}/knowledge", tags=["knowledge"])


def _document_to_read(document, project_id: int, include_content: bool = False) -> KnowledgeDocumentRead:
    return KnowledgeDocumentRead(
        id=document.id,
        project_id=document.project_id,
        source_type=document.source_type,
        title=document.title,
        filename=document.filename,
        download_url=f"/api/projects/{project_id}/knowledge/documents/{document.id}/download",
        summary=document.summary,
        content=document.content if include_content else None,
        index_status=document.index_status,
        indexed_at=document.indexed_at,
        index_error=document.index_error,
        created_at=document.created_at,
    )


def _source_to_read(result: RetrievedChunk, project_id: int) -> KnowledgeSourceRead:
    return KnowledgeSourceRead(
        id=result.chunk.id,
        document_id=result.chunk.document_id,
        document_title=result.chunk.document.title,
        heading=result.chunk.heading,
        text=result.chunk.content,
        download_url=f"/api/projects/{project_id}/knowledge/documents/{result.chunk.document_id}/download",
        score=round(result.score, 4),
    )


def _stream_event(event: str, data: dict | str) -> str:
    payload = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


@router.get("/documents", response_model=list[KnowledgeDocumentRead])
def list_knowledge_documents(project_id: int, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    documents = list_documents(db, project_id)
    db.commit()
    return [_document_to_read(document, project_id) for document in documents]


@router.post("/index", response_model=KnowledgeIndexTriggerRead)
def trigger_knowledge_index(project_id: int, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    result = trigger_unready_index_jobs(db, project_id)
    db.commit()
    return KnowledgeIndexTriggerRead(
        queued=result.queued,
        skipped=result.skipped,
        failed=result.failed,
        total_unready=result.total_unready,
    )


@router.post("/documents", response_model=KnowledgeDocumentRead, status_code=status.HTTP_201_CREATED)
def upload_knowledge_document(
    project_id: int,
    db: DbSession,
    user: CurrentUser,
    file: UploadFile = File(...),
):
    require_project_member(db, project_id, user)
    document = ingest_upload(db, project_id, user, file)
    db.commit()
    db.refresh(document)
    return _document_to_read(document, project_id)


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentRead)
def get_knowledge_document(project_id: int, document_id: int, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    document = get_document(db, document_id, project_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库文件不存在")
    return _document_to_read(document, project_id, include_content=True)


@router.patch("/documents/{document_id}", response_model=KnowledgeDocumentRead)
def update_knowledge_document(
    project_id: int,
    document_id: int,
    payload: KnowledgeDocumentUpdate,
    db: DbSession,
    user: CurrentUser,
):
    require_project_member(db, project_id, user)
    document = update_upload_document(
        db,
        document_id=document_id,
        project_id=project_id,
        title=payload.title,
        filename=payload.filename,
        content=payload.content,
        content_type=payload.content_type,
    )
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库文件不存在或不可编辑")
    db.commit()
    db.refresh(document)
    return _document_to_read(document, project_id, include_content=True)


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_knowledge_document(project_id: int, document_id: int, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    if not delete_document(db, document_id, project_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库文件不存在或不可删除")
    db.commit()
    return None


@router.get("/documents/{document_id}/download")
def download_knowledge_document(project_id: int, document_id: int, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    document = get_document(db, document_id, project_id)
    if document is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="知识库文件不存在")
    return Response(
        document.content,
        media_type=(document.content_type or "text/markdown") + "; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{document.filename}"'},
    )


@router.post("/ask", response_model=KnowledgeAnswerRead)
def ask_knowledge(project_id: int, payload: KnowledgeAskRequest, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    answer, results = build_rag_answer(
        db,
        payload.question,
        project_id,
        history=[message.model_dump() for message in payload.history],
    )
    db.commit()
    documents_by_id = {result.chunk.document.id: result.chunk.document for result in results}
    return KnowledgeAnswerRead(
        answer=answer,
        sources=[_source_to_read(result, project_id) for result in results],
        documents=[_document_to_read(document, project_id) for document in documents_by_id.values()],
    )


@router.post("/ask/stream")
def stream_knowledge_answer(project_id: int, payload: KnowledgeAskRequest, db: DbSession, user: CurrentUser):
    require_project_member(db, project_id, user)
    return StreamingResponse(
        _knowledge_event_stream(project_id, payload, db),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _knowledge_event_stream(project_id: int, payload: KnowledgeAskRequest, db: DbSession):
    history = [message.model_dump() for message in payload.history]
    try:
        yield _stream_event("status", {"message": "正在理解问题..."})
        if payload.history:
            yield _stream_event("status", {"message": "正在理解上下文..."})
        yield _stream_event("status", {"message": "正在查找知识库文档..."})
        rag_context = build_rag_context(db, payload.question, project_id, history=history)
        sources = [_source_to_read(result, project_id).model_dump(mode="json") for result in rag_context.results]
        yield _stream_event("sources", {"sources": sources})

        if not rag_context.results:
            answer = build_indexing_answer() if rag_context.has_pending_documents else build_no_results_answer()
            yield _stream_event("status", {"message": "知识库正在索引" if rag_context.has_pending_documents else "没有找到足够相关的资料"})
            yield _stream_event("delta", {"text": answer})
            yield _stream_event("done", {"answer": answer})
            db.commit()
            return

        yield _stream_event("status", {"message": "正在生成回答..."})
        answer_parts: list[str] = []
        for delta in stream_rag_answer(payload.question, rag_context.contexts, history=history):
            answer_parts.append(delta)
            yield _stream_event("delta", {"text": delta})

        if not answer_parts:
            fallback = build_fallback_answer(rag_context.results)
            answer_parts.append(fallback)
            yield _stream_event("delta", {"text": fallback})

        answer = "".join(answer_parts).strip()
        yield _stream_event("done", {"answer": answer})
        db.commit()
    except HTTPException as exc:
        db.rollback()
        yield _stream_event("error", {"message": str(exc.detail)})
    except Exception as exc:
        db.rollback()
        yield _stream_event("error", {"message": f"助手请求失败：{exc}"})
