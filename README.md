# AhmadNL

AhmadNL is a Telegram PDF reading assistant for English-only guided study.

**Positioning:** turn any PDF into a guided reading experience.

## What users get

1. Upload a PDF.
2. AhmadNL validates, stores, and extracts readable text once.
3. The same document can be reused for:
   - Summary
   - Key points
   - Study questions
   - Answer guidance
4. Completed AI results are cached so repeated actions do not waste credits or Gemini calls.

## Development setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e '.[test]'
cp .env.example .env
ahmadnl-bot
```

Production requires PostgreSQL via `DATABASE_URL`. SQLite is suitable only for local development and tests.

## Database migrations

Alembic is the production migration workflow. The initial migration represents the Phase 1–6 SQLAlchemy schema.

Local development can create SQLite tables automatically on bot startup. Production should run migrations explicitly instead:

```bash
export APP_ENV=production
export DATABASE_URL=postgresql+asyncpg://user:password@host:5432/ahmadnl
alembic upgrade head
ahmadnl-bot
```

Do not commit production credentials. Configure `DATABASE_URL` in the hosting environment.

## Configuration

All secrets and limits are environment-driven. Start from `.env.example` and set real values in your hosting environment only.

Key variables:

- `TELEGRAM_BOT_TOKEN`
- `DATABASE_URL`
- `GEMINI_API_KEY`
- `GEMINI_MODEL`
- `STORAGE_DIR`
- PDF limits, AI limits, credit costs, daily free credits, and development purchase flag.

## Payments

Telegram Stars checkout uses server-side products and prices stored in the database. The bot creates a Stars invoice from trusted `ProductPrice` rows, verifies pre-checkout totals, and grants credits exactly once only after Telegram confirms successful payment.

Remaining deployment configuration:

- Seed at least one active `Product` and matching `ProductPrice` with `provider='telegram_stars'` and `currency='XTR'`.
- Configure `TELEGRAM_BOT_TOKEN` for the production bot.
- Confirm Telegram Stars eligibility/settings for the bot in Telegram before advertising paid checkout as live.
