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

    def extract_msg_id(self, result) -> str | None:
        if not result:
            return None
        return result.get("messages", [{}])[0].get("id")

    def set_listener(self, listener):
        self.listener = listener

    def set_creds(self, creds: dict):
        self.creds = creds

    async def send(self, data: MessageCreate) -> dict:
        conn = WabaConnection(api_key=self.creds["api_key"])

        clean_phone = data.phone.lstrip('+')

        if data.media:
            results = []
            for m in data.media:
                file_url = f"{settings.s3_external_url}/{settings.s3_bt_bucket}/{m['id']}"
                result = await conn.send_file(clean_phone, file_url, m.get("mime_type"), data.text)
                results.append(result)
            return results[-1] if results else None
        else:
            return await conn.send_message(clean_phone, data.text)