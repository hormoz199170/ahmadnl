"""initial Phase 1-6 schema

Revision ID: 20260824_0001
Revises:
Create Date: 2026-08-24
"""
from alembic import op
import sqlalchemy as sa

revision = "20260824_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("telegram_id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_users_telegram_id"), "users", ["telegram_id"], unique=True)

    op.create_table(
        "products",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("active", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "coupons",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("credits", sa.Integer(), nullable=False),
        sa.Column("max_redemptions", sa.Integer(), nullable=False),
        sa.Column("redeemed_count", sa.Integer(), nullable=False),
        sa.Column("active", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("code"),
    )

    op.create_table(
        "documents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("telegram_file_id", sa.String(length=256), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("storage_path", sa.String(length=512), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "sha256", name="uq_user_document_hash"),
    )
    op.create_index(op.f("ix_documents_sha256"), "documents", ["sha256"], unique=False)
    op.create_index(op.f("ix_documents_user_id"), "documents", ["user_id"], unique=False)

    op.create_table(
        "product_prices",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_document_chunks_document_id"), "document_chunks", ["document_id"], unique=False)

    op.create_table(
        "ai_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=False),
        sa.Column("prompt_version", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("input_chars", sa.Integer(), nullable=False),
        sa.Column("output_chars", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "kind", "prompt_version", name="uq_ai_cache"),
    )
    op.create_index(op.f("ix_ai_results_document_id"), "ai_results", ["document_id"], unique=False)
    op.create_index(op.f("ix_ai_results_request_id"), "ai_results", ["request_id"], unique=True)

    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("note", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(op.f("ix_credit_ledger_user_id"), "credit_ledger", ["user_id"], unique=False)

    op.create_table(
        "daily_free_usage",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column("credits_granted", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "usage_date", name="uq_daily_free_user_date"),
    )
    op.create_index(op.f("ix_daily_free_usage_user_id"), "daily_free_usage", ["user_id"], unique=False)

    op.create_table(
        "orders",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("product_id", sa.String(length=64), nullable=False),
        sa.Column("price_id", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["price_id"], ["product_prices.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_orders_user_id"), "orders", ["user_id"], unique=False)

    op.create_table(
        "payment_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("order_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_payment_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_payment_records_order_id"), "payment_records", ["order_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_payment_records_order_id"), table_name="payment_records")
    op.drop_table("payment_records")
    op.drop_index(op.f("ix_orders_user_id"), table_name="orders")
    op.drop_table("orders")
    op.drop_index(op.f("ix_daily_free_usage_user_id"), table_name="daily_free_usage")
    op.drop_table("daily_free_usage")
    op.drop_index(op.f("ix_credit_ledger_user_id"), table_name="credit_ledger")
    op.drop_table("credit_ledger")
    op.drop_index(op.f("ix_ai_results_request_id"), table_name="ai_results")
    op.drop_index(op.f("ix_ai_results_document_id"), table_name="ai_results")
    op.drop_table("ai_results")
    op.drop_index(op.f("ix_document_chunks_document_id"), table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_table("product_prices")
    op.drop_index(op.f("ix_documents_user_id"), table_name="documents")
    op.drop_index(op.f("ix_documents_sha256"), table_name="documents")
    op.drop_table("documents")
    op.drop_table("coupons")
    op.drop_table("products")
    op.drop_index(op.f("ix_users_telegram_id"), table_name="users")
    op.drop_table("users")
