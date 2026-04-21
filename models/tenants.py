import uuid
import enum
from datetime import datetime, timezone
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    String,
    JSON,
    Enum,
    ForeignKey,
    DateTime,
    Boolean,
    UniqueConstraint,
)
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from core.database import Base


class TenantStatus(enum.Enum):
    active = "active"
    blocked = "blocked"

class UserRole(enum.Enum):
    admin = "admin"
    user = "user"
    support = "support"
    owner = "owner"

class UserStatus(enum.Enum):
    trial = "trial"
    active = "active"
    inactive = "inactive"
    suspended = "suspended"

class PermissionAction(enum.Enum):
    owner = "owner"
    member = "member"

class TenantPayment(enum.Enum):
    acquiring = "acquiring"
    wire = "wire"


class BankDetails(Base):
    __tablename__ = "banking_details"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    # Universal fields
    bank_name = Column(String(255), nullable=False)
    account_number = Column(String(34), nullable=False)  # Supports both RU account and IBAN
    bic = Column(String(11), nullable=False)  # Supports both RU BIK and SWIFT

    # Specific fields
    corr_account = Column(String(20), nullable=True)  # Required for RU, optional for others
    kpp = Column(String(9), nullable=True)  # Required for RU, optional for others

    currency = Column(String(3), default="RUB", nullable=False)
    is_primary = Column(Boolean, default=False, nullable=False)


class Tenant(Base):
    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, index=True, nullable=False)
    banking_details = relationship(
        "BankDetails",
        backref="tenant",
        cascade="all, delete-orphan",
        uselist=False,
        lazy="joined"
    )
    locale = Column(String, default="en_US")
    payment = Column(Enum(TenantPayment, name="tenantpayment"), default=TenantPayment.acquiring, nullable=False)
    status = Column(Enum(TenantStatus, name="tenantstatus"), default=TenantStatus.active, nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, nullable=True, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(Enum(UserRole, name="userrole"), default=UserRole.user, nullable=False, index=True)
    status = Column(Enum(UserStatus, name="userstatus"), default=UserStatus.inactive, nullable=False, index=True)
    full_name = Column(String, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.now, nullable=True, index=True)
    invite_token = Column(String, nullable=True, index=True)


class Membership(Base):
    __tablename__ = "memberships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    # Roles: owner, admin, staff
    role = Column(String, nullable=False, default="staff")
    is_active = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="uq_user_tenant"),
    )



class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    device_info = Column(String)
    ip_address = Column(String)
    is_blocked = Column(Boolean, default=False)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), index=True)
    user_id = Column(UUID(as_uuid=True), index=True)
    action = Column(String, nullable=False)
    entity_type = Column(String, index=True)
    entity_id = Column(String, index=True)
    old_state = Column(JSON)
    new_state = Column(JSON)
    ip_address = Column(String)
    created_at = Column(DateTime, server_default=func.now())


class JuridicalEntity(Base):
    __tablename__ = "juridical_entities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), unique=True, nullable=False)
    company_name = Column(String, nullable=False)
    inn = Column(String(12), index=True, nullable=False)
    bik = Column(String(9), nullable=False)
    account_number = Column(String(20), nullable=False)
    created_at = Column(DateTime, server_default=func.now())


class ResourcePermission(Base):
    __tablename__ = "resource_permissions"

    id = Column(Integer, primary_key=True, index=True)
    # Using UUID to match User.id and Tenant.id
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)

    resource_type = Column(String, nullable=False)  # e.g., 'whatsapp_line'
    resource_id = Column(UUID(as_uuid=True), nullable=False)
    action = Column(Enum(PermissionAction), default=PermissionAction.member, nullable=False)

    __table_args__ = (
        UniqueConstraint('user_id', 'resource_type', 'resource_id', 'action', name='_user_resource_action_uc'),
    )


