from pydantic import BaseModel


class PhoneRequest(BaseModel):
    phone: str
    session_string: str = ""


class SendMessageRequest(BaseModel):
    line_id: str
    phone: str
    text: str
    media: list[dict] | None = None

class EditMessageRequest(BaseModel):
    line_id: str
    phone: str
    channel_msg_id: str
    text: str


class DeleteMessageRequest(BaseModel):
    line_id: str
    phone: str
    channel_msg_id: str
