"""Schemas for authentication and authorization"""

import re
import uuid

from enum import Enum
from typing import Annotated, Optional
from pydantic import AfterValidator, BaseModel, EmailStr, Field


class UserRole(str, Enum):
    """User roles in organization"""

    OWNER = "owner"
    ADMIN = "admin"
    MANAGER = "manager"
    MEMBER = "member"


class TokenType(str, Enum):
    """Token types"""

    ACCESS = "access"
    REFRESH = "refresh"


class TokenPayload(BaseModel):
    """JWT token payload"""

    sub: str
    exp: int
    type: str
    organization_id: int | None = None
    role: str | None = None


class TokenPair(BaseModel):
    """Access/refresh token pair"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class LoginRequest(BaseModel):
    """Login request"""

    email: EmailStr
    password: str


class RefreshTokenRequest(BaseModel):
    """Refresh token request"""

    refresh_token: str


class UserContext(BaseModel):
    """Current user context"""

    id: uuid.UUID
    email: str
    role: UserRole | None = None

    def is_owner(self) -> bool:
        """Check if user is admin or owner"""
        return self.role == UserRole.OWNER

    def is_admin(self) -> bool:
        """Check if user is manager, admin or owner"""
        return self.role in [UserRole.OWNER, UserRole.ADMIN]

    def is_manager(self) -> bool:
        """Check if user is manager, admin or owner"""
        return self.role in [UserRole.OWNER, UserRole.ADMIN, UserRole.MANAGER]

    def can_modify_resource(self, resource_owner_id: int) -> bool:
        """Check resource modification permissions"""
        if self.is_manager():
            return True
        return self.user_id == resource_owner_id


def validate_phone(v: str) -> str:
    # Remove everything except digits and plus
    clean = re.sub(r"(?!\+)[^\d]", "", v)
    if not re.match(r"^\+\d{7,15}$", clean):
        raise ValueError("Phone must start with + followed by 7-15 digits")
    return clean

PhoneStr = Annotated[str, AfterValidator(validate_phone)]

class RegisterBase(BaseModel):
    """Base registration"""

    email: EmailStr
    phone: PhoneStr
    

class RegisterRequest(RegisterBase):
    """Registration request"""

    password: str
    ifsms: bool 

class RegisterDB(RegisterBase):
    """Registration data for insert into database"""

    password_hash: str
