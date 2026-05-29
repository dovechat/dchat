import uuid
from io import BytesIO
from minio import Minio
from fastapi import UploadFile
from core.config import settings
import logging

log = logging.getLogger("uvicorn.error")


class StorageService:
    def __init__(self):
        self.client = Minio(
            settings.s3_endpoint,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            secure=settings.s3_secure,
        )

    async def save_file(
        self,
        file_bytes: bytes,
        media_id: uuid.UUID,
        filename: str,
        mime_type: str,
    ) -> dict:
        size = len(file_bytes)
        self.client.put_object(
            settings.s3_bucket,
            str(media_id),
            BytesIO(file_bytes),
            size,
            content_type=mime_type,
            metadata={"filename": filename, "content_type": mime_type, "size": size},
        )
        log.info(f"StorageService.save_file media_id={media_id} filename={filename} size={size}")
        return {
            "media_id": media_id,
            "filename": filename,
            "mime_type": mime_type,
            "size": size,
        }

    async def upload_file(
        self,
        file: UploadFile,
        media_id: uuid.UUID,
    ) -> dict:
        file_bytes = await file.read()
        return self.save_file(file_bytes, media_id, file.filename, file.content_type)

    def public_url(self, media_id: uuid.UUID) -> str:
        return f"{settings.s3_external_url}/{settings.s3_bucket}/{media_id}"