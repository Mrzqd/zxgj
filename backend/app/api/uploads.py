from fastapi import APIRouter, File, UploadFile, status

from app.api.deps import CurrentUser, DbSession, require_project_member
from app.models import Attachment
from app.schemas import AttachmentRead
from app.services.storage import upload_to_s3

router = APIRouter(prefix="/projects/{project_id}/uploads", tags=["uploads"])


@router.post("", response_model=AttachmentRead, status_code=status.HTTP_201_CREATED)
def upload_file(project_id: int, db: DbSession, user: CurrentUser, file: UploadFile = File(...)):
    require_project_member(db, project_id, user)
    object_key, url, size_bytes = upload_to_s3(project_id, file)
    attachment = Attachment(
        project_id=project_id,
        uploader_id=user.id,
        object_key=object_key,
        url=url,
        file_name=file.filename or "upload",
        content_type=file.content_type,
        size_bytes=size_bytes,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return attachment

