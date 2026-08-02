import os
import uuid
from datetime import datetime
from minio import Minio
from core.config import settings
from services.storage_service import StorageService


async def serialize_message(
    event,
    line_id: uuid.UUID,
    conversation_id: uuid.UUID,
    peer_phone: str,
):
    message = event.message
    sender = await event.get_sender()

    return {
        "line_id": line_id,
        "event_type": "message_created",
        "conversation_id": str(conversation_id) if conversation_id else None,
        "peer_phone": peer_phone,
        "message": {
            "id": message.id,
            "text": message.text or "",
            "date": (
                message.date.isoformat()
                if isinstance(message.date, datetime)
                else None
            ),
            "sender": {
                "id": getattr(sender, "id", None),
                "first_name": getattr(sender, "first_name", None),
                "last_name": getattr(sender, "last_name", None),
                "username": getattr(sender, "username", None),
            },
            "chat_id": event.chat_id,
            "grouped_id": (
                str(message.grouped_id)
                if message.grouped_id
                else None
            ),
            "media": await process_media(event),
        },
    }


async def process_media(event):
    if not event.media:
        return []

    media_id = uuid.uuid4()

    file_bytes = await event.download_media(file=bytes)

    filename = (
        event.message.file.name
        if event.message.file and event.message.file.name
        else "unnamed"
    )

    mime_type = (
        event.message.file.mime_type
        if event.message.file and event.message.file.mime_type
        else "application/octet-stream"
    )

    storage = StorageService()

    await storage.save_file(
        file_bytes,
        media_id,
        filename,
        mime_type,
    )

    return [
        {
            "id": str(media_id),
            "file_name": filename,
            "mime_type": mime_type,
        }
    ]

def serialize_edited_message(event, line_id: str, conversation_id: uuid.UUID):
    return {
        "line_id": line_id,
        "event_type": "message_edit",
        "conversation_id": str(conversation_id),
        "message": {
            "id": event.message.id,
            "text": event.message.text or "",
        },
    }


def serialize_deleted_message(message_ids, line_id: str, conversation_id):
    return {
        "line_id": line_id,
        "conversation_id": str(conversation_id),
        "event_type": "message_delete",
        "message_ids": message_ids,
    }