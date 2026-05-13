import httpx
import logging
import random
from core.config import settings
from app.senders.base import BaseSender
from app.schemas.chat_schemas import MessageCreate
from app.consumers.vk import VkConnection

log = logging.getLogger(__name__)

class VKSender(BaseSender):
    def __init__(self):
        self.listener = None
        self.creds = None

    def set_listener(self, listener):
        self.listener = listener

    def set_creds(self, creds: dict):
        self.creds = creds

    async def send(self, data: MessageCreate) -> dict:
        log.info(f"\n\n ========== send data.message_id  {data.message_id} {type(data.message_id)} \n\n")

        conn = VkConnection(access_token=self.creds["access_token"])

        clean_phone = data.phone.lstrip('+')
        
        if data.media:
            attachments = []
            for m in data.media:
                file_url = f"{settings.s3_internal_url}dovechat-media/{m['id']}"
                async with httpx.AsyncClient() as client:
                    resp = await client.get(file_url)
                    resp.raise_for_status()
                    file_bytes = resp.content
                attachment = await conn.upload_and_send_photo(
                    int(clean_phone), file_bytes,
                    m.get("file_name", "photo.jpg")
                )
                attachments.append(attachment)
            
            return await conn.call("messages.send", {
                "peer_id": int(clean_phone),
                "message": data.text or "",
                "attachment": ",".join(attachments),
                "random_id": data.message_id
            })
        else:
            return await conn.send_message(clean_phone, data.text, random_id=data.message_id)