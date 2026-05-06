from pydantic import BaseModel, ConfigDict
from uuid import UUID
from typing import Optional

class MemberCreate(BaseModel):
    email: str
    role: str  # 'owner' или 'member'

class MemberResponse(BaseModel):
    id: UUID
    user_id: UUID
    tenant_id: UUID
    role: str
    is_active: bool
    email: str | None = None
    model_config = ConfigDict(from_attributes=True)

class LinePermissionCreate(BaseModel):
    user_id: UUID
    line_id: UUID
    action: str = "send"  # можно сразу задать

class LinePermissionResponse(BaseModel):
    user_id: UUID
    line_id: UUID
    action: str
    model_config = ConfigDict(from_attributes=True)