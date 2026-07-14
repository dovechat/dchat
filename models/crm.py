import uuid
from datetime import datetime
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from core.database import Base
from models.tenants import Tenant, User  # noqa: F401
from models.lines import Line, ChannelAccount  # noqa: F401


class CrmConnection(Base):
    __tablename__ = "crm_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    line_id = Column(UUID(as_uuid=True), ForeignKey("lines.id", ondelete="SET NULL"), nullable=True, index=True)
    crm_type = Column(String, nullable=False, default="bitrix24")
    channel_type = Column(String, nullable=True)
    connector_id = Column(String, nullable=True)
    crm_line_id = Column(String, nullable=True)
    domain = Column(String, nullable=False)
    access_token_enc = Column(String, nullable=False)
    refresh_token_enc = Column(String, nullable=False)
    member_id = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    token_updated_at = Column(DateTime, server_default=func.now())
    created_at = Column(DateTime, server_default=func.now())
    # AMO-specific fields
    account_id = Column(String, nullable=True)
    amojo_id = Column(String, nullable=True)

    __table_args__ = (
        UniqueConstraint("line_id", "connector_id", name="uq_line_connector"),
    )


class CrmDialogLink(Base):
    __tablename__ = "crm_dialog_links"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True)
    crm_account_id = Column(UUID(as_uuid=True), ForeignKey("crm_accounts.id", ondelete="CASCADE"), nullable=False, index=True)
    crm_chat_id = Column(String, nullable=False)
    crm_user_id = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    amo_lead_id = Column(String, nullable=True, index=True)

    __table_args__ = (
        UniqueConstraint("conversation_id", "crm_account_id", name="uq_conv_crm"),
    )


class CrmSettings(Base):
    __tablename__ = "crm_settings"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    no_deal_action = Column(String, nullable=False, default="nothing")
    auto_create_contact = Column(Boolean, nullable=False, default=True)
    responsible_user_id = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())


class CrmAccount(Base):
    __tablename__ = "crm_accounts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    crm_type = Column(String, nullable=False)
    domain = Column(String, nullable=False)
    access_token_enc = Column(String)
    refresh_token_enc = Column(String)
    is_active = Column(Boolean, default=True)
    token_updated_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())
    member_id = Column(String)
    amojo_id = Column(String)
    account_id = Column(String)
    no_deal_action = Column(String, default="nothing")
    auto_create_contact = Column(Boolean, default=True)
    responsible_user_id = Column(String)


class CrmLineConnection(Base):
    __tablename__ = "crm_line_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    crm_account_id = Column(UUID(as_uuid=True), ForeignKey("crm_accounts.id", ondelete="CASCADE"), nullable=False)
    line_id = Column(UUID(as_uuid=True), ForeignKey("lines.id", ondelete="CASCADE"), nullable=False)
    channel_type = Column(String, nullable=False)
    crm_line_id = Column(String)
    connector_id = Column(String)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())