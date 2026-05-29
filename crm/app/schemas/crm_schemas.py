"""CRM schemas."""
import uuid
from pydantic import BaseModel


class CrmConnectRequest(BaseModel):
    crm_type: str
    domain: str
    access_token: str
    refresh_token: str
    connector_id: str
    line_id: str
    member_id: str | None = None


class CrmConnectionResponse(BaseModel):
    id: uuid.UUID
    crm_type: str
    domain: str
    connector_id: str
    line_id: str
    is_active: bool

    class Config:
        from_attributes = True

class BitrixAuthRequest(BaseModel):
    email: str
    password: str
    placement_params: str = ""

class BitrixConnectRequest(BaseModel):
    line_id: uuid.UUID
    access_token: str
    refresh_token: str
    member_id: str
    domain: str