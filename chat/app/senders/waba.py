import logging
from core.config import settings
from app.senders.base import BaseSender
from app.schemas.chat_schemas import MessageCreate
from app.consumers.waba import WabaConnection

log = logging.getLogger(__name__)

class WabaSender(BaseSender):
    def __init__(self):
        self.listener = None
        self.creds = None

    def set_listener(self, listener):
        self.listener = listener

    def set_creds(self, creds: dict):
        self.creds = creds

    async def send(self, data: MessageCreate) -> dict:
        conn = WabaConnection(api_key=self.creds["api_key"])

        clean_phone = data.phone.lstrip('+')

        if data.media_id:
            file_url = f"{settings.s3_external_url}{data.media_id}"
            return await conn.send_file(clean_phone, file_url,  data.raw_content.get("mime_type") , data.text)
        else:
            return await conn.send_message(clean_phone, data.text)