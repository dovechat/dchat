from pydantic import BaseModel
from typing import Optional


class CrmSettingsRead(BaseModel):
    no_deal_action: str
    auto_create_contact: bool
    responsible_user_id: Optional[str] = None

    model_config = {"from_attributes": True}


class CrmSettingsUpdate(BaseModel):
    no_deal_action: Optional[str] = None
    auto_create_contact: Optional[bool] = None
    responsible_user_id: Optional[str] = None
    bitrix_client_id: Optional[str] = None
    bitrix_client_secret: Optional[str] = None