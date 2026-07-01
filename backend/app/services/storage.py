from pathlib import PurePosixPath
from uuid import uuid4

import boto3
from fastapi import HTTPException, UploadFile, status

from app.core.config import settings


def _public_url(object_key: str) -> str:
    if settings.s3_public_base_url:
        return f"{settings.s3_public_base_url.rstrip('/')}/{object_key}"
    if settings.s3_endpoint_url:
        return f"{settings.s3_endpoint_url.rstrip('/')}/{settings.s3_bucket}/{object_key}"
    return f"https://{settings.s3_bucket}.s3.{settings.aws_region}.amazonaws.com/{object_key}"


def upload_to_s3(project_id: int, file: UploadFile) -> tuple[str, str, int]:
    max_bytes = settings.max_upload_mb * 1024 * 1024
    content = file.file.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"文件不能超过 {settings.max_upload_mb}MB",
        )

    suffix = PurePosixPath(file.filename or "upload").suffix
    object_key = f"projects/{project_id}/{uuid4().hex}{suffix}"
    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
    )
    client.put_object(
        Bucket=settings.s3_bucket,
        Key=object_key,
        Body=content,
        ContentType=file.content_type or "application/octet-stream",
    )
    return object_key, _public_url(object_key), len(content)

