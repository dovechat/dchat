import uuid
import enum
from sqlalchemy import Column, Index, Integer, BigInteger, String, JSON, Enum as SQLEnum, ForeignKey, DateTime, Numeric, \
    Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from core.database import Base


class RobotJobStatus(enum.Enum):
    pending = "pending"
    processing = "processing"
    completed = "completed"
    failed = "failed"


class Tariff(Base):
    __tablename__ = "tariffs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False)
    # Pricing per channel and period (month/year) from TZ 9.1
    channel_type = Column(String, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)
    period_days = Column(Integer, default=30)
    is_active = Column(Boolean, default=True)


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    amount = Column(Numeric(10, 2), nullable=False)
    # acquiring or bank_transfer (TZ 9.1)
    payment_method = Column(String, nullable=False)
    external_id = Column(String, unique=True)  # Transaction ID from gateway
    status = Column(String)
    created_at = Column(DateTime, server_default=func.now())

class Balance(Base):
    __tablename__ = "balances"

    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True)
    main_balance = Column(Numeric(10, 2), default=0, nullable=False)
    bonus_balance = Column(Numeric(10, 2), default=0, nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class BalanceLedger(Base):
    __tablename__ = "balance_ledger"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)  # Positive for deposit, negative for withdrawal
    # main or bonus (TZ 9.1)
    balance_type = Column(String, default="main", nullable=False)
    description = Column(String)
    # Link to payment or line_id that triggered withdrawal
    reference_id = Column(UUID(as_uuid=True), index=True)
    created_at = Column(DateTime, server_default=func.now(), index=True)

__table_args__ = (
        Index("ix_ledger_tenant_created", "tenant_id", "created_at"),
    )

class RobotJob(Base):
    __tablename__ = "robot_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    # send_text, send_file, check_account (TZ 8.2-8.4)
    job_type = Column(String, nullable=False)
    status = Column(SQLEnum(RobotJobStatus, native_enum=False), default=RobotJobStatus.pending, index=True)
    params = Column(JSON)  # Inputs from CRM
    result = Column(JSON)  # Success/Error details

    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    created_at = Column(DateTime, server_default=func.now())