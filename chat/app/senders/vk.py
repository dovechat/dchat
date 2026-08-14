import httpx
import logging
import random
from sqlalchemy.ext.asyncio import AsyncSession
from core.config import settings
from services.storage_service import StorageService
from app.senders.base import BaseSender
from app.schemas.chat_schemas import MessageCreate
from app.consumers.vk import VkConnection


log = logging.getLogger(__name__)

class VKSender(BaseSender):
    def __init__(self):
        self.listener = None
        self.creds = None
        self.line_id = None

    def extract_msg_id(self, result) -> str | None:
        log.info(f"VK extract_msg_id result={result} type={type(result)}")
        if not result:
            return None
        return str(result) if isinstance(result, int) else result.get("message_id")

    def set_listener(self, listener):
        self.listener = listener

    def set_creds(self, creds: dict):
        self.creds = creds

    def set_line_id(self, line_id):
        self.line_id = line_id

    async def send(self, data: MessageCreate, db: AsyncSession = None) -> dict:
        log.info(f"\n\n ========== send data.message_id  {data.message_id} {type(data.message_id)} \n\n")

        conn = VkConnection(access_token=self.creds["access_token"], line_id=self.line_id, db=db)

        clean_phone = data.phone.lstrip('+')

        log.info(f"peer_id={int(clean_phone)}")

        if data.media:
            attachments = []
            for m in data.media:
                file_url = StorageService().presigned_url(m['id'])
                async with httpx.AsyncClient() as client:
                    resp = await client.get(file_url)
                    resp.raise_for_status()
                    file_bytes = resp.content
                mime_type = m.get("mime_type", "")
                if mime_type.startswith("image/"):
                    attachment = await conn.upload_and_send_photo(
                        int(clean_phone), file_bytes,
                        m.get("file_name", "photo.jpg")
                    )
                else:
                    attachment = await conn.upload_and_send_doc(
                        int(clean_phone), file_bytes,
                        m.get("file_name", "file")
                    )
                attachments.append(attachment)
        else:
            return await conn.send_message(int(clean_phone), data.text, random_id=data.message_id)

    async def edit(self, channel_msg_id: str, phone: str, text: str) -> dict:
        log.info(f"\n\n  -+-+-+   senders vk channel_msg_id {channel_msg_id} phone {phone} text {text} \n\n")
        conn = VkConnection(access_token=self.creds["access_token"], line_id=self.line_id)
        clean_phone = phone.lstrip('+')
        return await conn.edit_message(int(clean_phone), int(channel_msg_id), text)

    async def delete(self, channel_msg_id: str, phone: str) -> dict:
        conn = VkConnection(access_token=self.creds["access_token"], line_id=self.line_id)
        clean_phone = phone.lstrip('+')
        return await conn.delete_message(int(clean_phone), int(channel_msg_id))