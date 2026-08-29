from datetime import UTC, date, datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ahmadnl.db import Base


def now_utc() -> datetime:
    return datetime.now(UTC)


class DocumentState(str, Enum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class AIResultKind(str, Enum):
    SUMMARY = "summary"
    KEY_POINTS = "key_points"
    STUDY_QUESTIONS = "study_questions"
    ANSWER_GUIDANCE = "answer_guidance"


class LedgerKind(str, Enum):
    GRANT = "grant"
    CONSUME = "consume"
    REFUND = "refund"
    ADMIN_ADJUSTMENT = "admin_adjustment"
    DAILY_FREE = "daily_free"


class OrderStatus(str, Enum):
    CREATED = "created"
    PAID = "paid"
    FAILED = "failed"
    CANCELED = "canceled"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    telegram_id: Mapped[int] = mapped_column(unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    documents: Mapped[list["Document"]] = relationship(back_populates="user")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    telegram_file_id: Mapped[str] = mapped_column(String(256))
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_path: Mapped[str] = mapped_column(String(512))
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    byte_size: Mapped[int] = mapped_column(Integer)
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str | None] = mapped_column(String(255))
    state: Mapped[DocumentState] = mapped_column(String(32), default=DocumentState.UPLOADED)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    user: Mapped[User] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(cascade="all, delete-orphan")
    __table_args__ = (UniqueConstraint("user_id", "sha256", name="uq_user_document_hash"),)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text)


class AIResult(Base):
    __tablename__ = "ai_results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    kind: Mapped[AIResultKind] = mapped_column(String(64))
    request_id: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    prompt_version: Mapped[str] = mapped_column(String(32), default="v1")
    content: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), default="completed")
    error_message: Mapped[str | None] = mapped_column(Text)
    input_chars: Mapped[int] = mapped_column(Integer, default=0)
    output_chars: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
    __table_args__ = (UniqueConstraint("document_id", "kind", "prompt_version", name="uq_ai_cache"),)


class CreditLedger(Base):
    __tablename__ = "credit_ledger"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[LedgerKind] = mapped_column(String(32))
    amount: Mapped[int] = mapped_column(Integer)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    note: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class DailyFreeUsage(Base):
    __tablename__ = "daily_free_usage"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    usage_date: Mapped[date] = mapped_column(Date)
    credits_granted: Mapped[int] = mapped_column(Integer, default=0)
    __table_args__ = (UniqueConstraint("user_id", "usage_date", name="uq_daily_free_user_date"),)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    credits: Mapped[int] = mapped_column(Integer)
    active: Mapped[int] = mapped_column(Integer, default=1)


class ProductPrice(Base):
    __tablename__ = "product_prices"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    currency: Mapped[str] = mapped_column(String(16))
    amount: Mapped[int] = mapped_column(Integer)
    provider: Mapped[str] = mapped_column(String(32), default="telegram_stars")


class Coupon(Base):
    __tablename__ = "coupons"
    code: Mapped[str] = mapped_column(String(64), primary_key=True)
    credits: Mapped[int] = mapped_column(Integer)
    max_redemptions: Mapped[int] = mapped_column(Integer, default=1)
    redeemed_count: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[int] = mapped_column(Integer, default=1)


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    product_id: Mapped[str] = mapped_column(ForeignKey("products.id"))
    price_id: Mapped[str] = mapped_column(ForeignKey("product_prices.id"))
    status: Mapped[OrderStatus] = mapped_column(String(32), default=OrderStatus.CREATED)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)


class PaymentRecord(Base):
    __tablename__ = "payment_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    order_id: Mapped[str] = mapped_column(ForeignKey("orders.id"), index=True)
    provider: Mapped[str] = mapped_column(String(32))
    provider_payment_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[PaymentStatus] = mapped_column(String(32), default=PaymentStatus.PENDING)
    amount: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now_utc)
