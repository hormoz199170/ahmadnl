# Architecture

AhmadNL is a small Telegram PDF reading assistant: upload a PDF, extract reusable text chunks once, then use a simple Telegram menu to generate summary, key points, study questions, and answer guidance from the same document.

## Layers

- `bot`: aiogram 3.x entrypoint and thin handlers with English-only onboarding, document navigation, reading actions, credits, and payments.
- `config`: typed environment-driven settings; secrets are read from environment only.
- `models`: SQLAlchemy models for users, documents, chunks, AI cache/usage, credits, coupons, orders, products, and payment records.
- `services/pdf.py` and `services/documents.py`: Telegram PDF ingestion, duplicate detection, validation, hashing, safe local storage, PyMuPDF extraction, normalization, page chunks, and lifecycle-friendly errors.
- `services/ai.py` and `services/reading.py`: `AIProvider` abstraction, Gemini provider, request IDs, concurrency, retry/timeout, cached results, usage counters, failure persistence, and credit-aware reading operations.
- `services/credits.py` and `services/payments.py`: immutable credit ledger, daily free credits, idempotency, coupons/order/payment foundation, Telegram Stars checkout boundary, and development-safe purchase boundary.

## Migrations

Alembic is used for production schema migrations. Production deployments run `alembic upgrade head` against PostgreSQL; local development may use automatic SQLite schema creation.

## Data storage

Production must use PostgreSQL through SQLAlchemy. SQLite is acceptable for local development and tests. Uploaded PDF files are stored under `STORAGE_DIR` by SHA-256 prefix. Extracted text is stored as page chunks, not as unnecessary duplicate full-document text.

## Phase boundary

This MVP intentionally stops at Phase 7. It does not include OCR, vector databases, chat-with-PDF, subscriptions, referrals, dashboards, or Phase 8 features.
