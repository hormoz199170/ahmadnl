# Tasks

## Phase status

- Phase 1 — COMPLETE: package structure, docs, pyproject, env example, gitignore, separation of bot/services/models/tests.
- Phase 2 — COMPLETE: typed settings, SQLAlchemy models, PostgreSQL production expectation, SQLite local/test support, safe secret handling, Alembic migration workflow.
- Phase 3 — COMPLETE: aiogram 3.x entrypoint, onboarding, user persistence, main menu fallback, PDF upload persistence/extraction status messages.
- Phase 4 — COMPLETE: PDF validation, size/MIME/extension checks, actual PDF check, page limit, PyMuPDF extraction, normalization, SHA-256 storage, duplicate detection, chunks, failure lifecycle errors.
- Phase 5 — COMPLETE: AIProvider abstraction, Gemini provider, limits, retries/timeouts, concurrency, deterministic request IDs, cached results, usage/failure persistence, reusable extracted chunks.
- Phase 6 — COMPLETE: product/pricing/order/payment models, immutable credit ledger, idempotency, daily free credits, refund/grant/consume/admin adjustment kind, Telegram Stars invoice/pre-checkout/success boundary, development-safe payment boundary.
- Phase 7 — COMPLETE: minimal Telegram MVP UX connects processed PDFs to document-centric Summary, Key Points, Study Questions, and Answer Guidance actions with cached AI reuse and credit-aware operation handling.

## Fixed production blockers

- Database migrations: Alembic configuration and initial Phase 1–6 schema migration are present.
- Telegram PDF pipeline: aiogram upload handling now downloads, validates, stores, hashes, de-duplicates, extracts, persists chunks, and reports only after persistence/extraction completes.
- Telegram Stars checkout: invoice, pre-checkout verification, successful-payment handling, trusted pricing, and idempotent credit grant are implemented.

## Phase 7 MVP behavior

- `/start` explains AhmadNL as a guided PDF reading assistant and shows a simple menu.
- `/documents` lists recent processed PDFs and lets the user return to a ready document.
- After upload, a ready PDF shows actions for Summary, Key Points, Study Questions, and Answer Guidance.
- Reading actions reuse extracted chunks and cached completed AI results.
- New AI reading actions check credits, consume credits with idempotency, refund on AI failure, and never create Telegram payment success without Telegram confirmation.

## Remaining production configuration

- Configure PostgreSQL `DATABASE_URL` and run `alembic upgrade head` during deployment.
- Configure `TELEGRAM_BOT_TOKEN` in the hosting environment.
- Configure `GEMINI_API_KEY` and `GEMINI_MODEL` in the hosting environment before enabling AI reading actions.
- Seed active Telegram Stars `Product` and `ProductPrice` rows; verify Telegram bot Stars eligibility before advertising paid checkout as live.
- Configure durable `STORAGE_DIR` for uploaded PDFs.

## Do not start yet

- Phase 8 features are intentionally not started.
