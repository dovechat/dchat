import logging
from core.config import settings
from app.senders.base import BaseSender
from app.schemas.chat_schemas import MessageCreate
from app.consumers.green_whatsapp import GreenWhatsAppConnection

log = logging.getLogger(__name__)

class WhatsAppGreenSender(BaseSender):
    def __init__(self):
        self.creds = None

    def set_creds(self, creds: dict):
        self.creds = creds

    def extract_msg_id(self, result) -> str | None:
        return result.get("idMessage") if result else None

    async def send(self, data: MessageCreate) -> dict:
        conn = GreenWhatsAppConnection(
            id_instance=self.creds["id_instance"],
            api_token=self.creds["api_token"]
        )

        clean_phone = data.phone.lstrip('+')
        chat_id = f"{clean_phone}@c.us"

        if data.media:
            results = []
            for m in data.media:
                file_url = f"{settings.s3_external_url}{settings.s3_bt_bucket}/{m['id']}"
                # file_url = "https://thumbnail.imgbin.com/0/20/18/imgbin-computer-icons-50x50-voicemail-message-box-WvsiFFj0e6tvNm4vSdsU9U0r4_t.jpg"
                result = await conn.send_file(chat_id, file_url, data.text, file_name=m.get('file_name', 'file'))
                results.append(result)
            return results[-1] if results else None
        else:
            return await conn.send_message(chat_id, data.text)
