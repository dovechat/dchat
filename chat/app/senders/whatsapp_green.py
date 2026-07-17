import logging
from sqlalchemy.ext.asyncio import AsyncSession
from core.config import settings
from services.storage_service import StorageService
from app.senders.base import BaseSender
from app.schemas.chat_schemas import MessageCreate
from app.consumers.green_whatsapp import GreenWhatsAppConnection

log = logging.getLogger(__name__)

class WhatsAppGreenSender(BaseSender):
    def __init__(self):
        self.creds = None
        self.line_id = None

    def set_creds(self, creds: dict):
        self.creds = creds

    def set_line_id(self, line_id):
        self.line_id = line_id

    def extract_msg_id(self, result) -> str | None:
        return result.get("idMessage") if result else None

    async def send(self, data: MessageCreate, db: AsyncSession = None) -> dict:
        conn = GreenWhatsAppConnection(
            id_instance=self.creds["id_instance"],
            api_token=self.creds["api_token"],
            line_id=self.line_id,
            db=db,
        )

        clean_phone = data.phone.lstrip('+')
        chat_id = f"{clean_phone}@c.us"

        if data.media:
            results = []
            for m in data.media:
                file_url = StorageService().presigned_url(m['id'])
                result = await conn.send_file(chat_id, file_url, data.text, file_name=m.get('file_name', 'file'))
                results.append(result)
            return results[-1] if results else None
        else:
            return await conn.send_message(chat_id, data.text)

    async def edit(self, channel_msg_id: str, phone: str, text: str) -> dict:
        conn = GreenWhatsAppConnection(
            id_instance=self.creds["id_instance"],
            api_token=self.creds["api_token"],
            line_id=self.line_id,
        )
        clean_phone = phone.lstrip('+')
        chat_id = f"{clean_phone}@c.us"
        return await conn.edit_message(chat_id, channel_msg_id, text)
    
    async def delete(self, channel_msg_id: str, phone: str) -> dict:
        conn = GreenWhatsAppConnection(
            id_instance=self.creds["id_instance"],
            api_token=self.creds["api_token"],
            line_id=self.line_id,
        )
        clean_phone = phone.lstrip('+')
        chat_id = f"{clean_phone}@c.us"
        return await conn.delete_message(chat_id, channel_msg_id)