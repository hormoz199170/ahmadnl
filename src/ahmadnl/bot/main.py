import asyncio
from io import BytesIO

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import LabeledPrice, Message, PreCheckoutQuery
from sqlalchemy import select

from ahmadnl.config import get_settings
from ahmadnl.db import create_schema, make_session_factory
from ahmadnl.models import OrderStatus, Product, ProductPrice, User
from ahmadnl.services.credits import balance, grant_daily_free
from ahmadnl.services.documents import ingest_pdf
from ahmadnl.services.payments import complete_successful_payment, create_order, verify_order_for_checkout
from ahmadnl.services.pdf import PDFProcessingError

router = Router()

WELCOME = """Welcome to AhmadNL.

Turn any PDF into a guided reading experience:
• Summary
• Key points
• Study questions
• Answer guidance

Upload a PDF to start. Your daily free credits make the first steps clear before you buy more.
Use /credits to check your balance or /buy to buy credits with Telegram Stars when checkout is configured."""


def session_factory():
    return make_session_factory(get_settings())


@router.message(CommandStart())
async def start(message: Message) -> None:
    settings = get_settings()
    async with session_factory()() as session, session.begin():
        user = await upsert_user(session, message)
        await grant_daily_free(session, user.id, settings.daily_free_credits)
        credits = await balance(session, user.id)
    await message.answer(f"{WELCOME}\n\nAvailable credits: {credits}")


@router.message(Command("credits"))
async def credits(message: Message) -> None:
    settings = get_settings()
    async with session_factory()() as session, session.begin():
        user = await upsert_user(session, message)
        await grant_daily_free(session, user.id, settings.daily_free_credits)
        credits_value = await balance(session, user.id)
    await message.answer(
        f"Available credits: {credits_value}\n\n"
        f"Daily free credits: {settings.daily_free_credits}. "
        "Credits are spent only when a reading action succeeds."
    )


@router.message(Command("buy"))
async def buy(message: Message, bot: Bot) -> None:
    async with session_factory()() as session, session.begin():
        user = await upsert_user(session, message)
        product, price = await first_stars_product(session)
        if not product or not price:
            await message.answer("Credit packs are not configured yet. Please try again later.")
            return
        order = await create_order(session, user.id, product.id, price.id)
    await bot.send_invoice(
        chat_id=message.chat.id,
        title=product.name,
        description=f"{product.credits} AhmadNL reading credits.",
        payload=order.id,
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=product.name, amount=price.amount)],
    )


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    async with session_factory()() as session, session.begin():
        ok = await verify_order_for_checkout(session, query.invoice_payload, query.currency, query.total_amount)
    if ok:
        await query.answer(ok=True)
    else:
        await query.answer(ok=False, error_message="This credit pack is no longer available. Please start a new purchase.")


@router.message(F.successful_payment)
async def successful_payment(message: Message) -> None:
    payment = message.successful_payment
    async with session_factory()() as session, session.begin():
        user = await upsert_user(session, message)
        order = await complete_successful_payment(
            session,
            order_id=payment.invoice_payload,
            provider_payment_id=payment.telegram_payment_charge_id,
            currency=payment.currency,
            amount=payment.total_amount,
            expected_user_id=user.id,
        )
        credits_value = await balance(session, user.id)
    if order.status == OrderStatus.PAID:
        await message.answer(f"Payment confirmed. Credits were added exactly once. Available credits: {credits_value}")
    else:
        await message.answer("Payment was not completed. No credits were added.")


@router.message(F.document)
async def pdf_upload(message: Message, bot: Bot) -> None:
    document = message.document
    if not document.file_name or not document.file_name.lower().endswith(".pdf"):
        await message.answer("Please upload a PDF file. I will extract readable text and build a study guide from it.")
        return
    settings = get_settings()
    if document.file_size and document.file_size > settings.pdf_max_bytes:
        await message.answer(f"PDF is too large. Limit: {settings.pdf_max_bytes // 1024 // 1024} MB.")
        return

    await message.answer("PDF received. I am validating and extracting readable text now.")
    buffer = BytesIO()
    try:
        await bot.download(document.file_id, destination=buffer)
        data = buffer.getvalue()
        async with session_factory()() as session, session.begin():
            user = await upsert_user(session, message)
            stored, duplicate = await ingest_pdf(
                session,
                user_id=user.id,
                telegram_file_id=document.file_id,
                filename=document.file_name,
                mime_type=document.mime_type,
                data=data,
                settings=settings,
            )
    except PDFProcessingError as exc:
        await message.answer(f"I could not read this PDF: {exc}")
        return
    except Exception:
        await message.answer("I could not save and extract this PDF. Please try again later.")
        return

    if duplicate:
        await message.answer(
            f"You already uploaded this PDF. I will reuse the extracted document with {stored.page_count} pages for reading actions."
        )
    else:
        await message.answer(
            f"PDF is ready: {stored.page_count} pages extracted. You can now use it for summary, key points, study questions, and answer guidance."
        )


@router.message()
async def menu(message: Message) -> None:
    await message.answer("Upload a PDF to begin, or use /start to see what AhmadNL can do.")


async def upsert_user(session, message: Message) -> User:
    telegram_user = message.from_user
    user = await session.scalar(select(User).where(User.telegram_id == telegram_user.id))
    if user:
        user.username = telegram_user.username
        return user
    user = User(telegram_id=telegram_user.id, username=telegram_user.username)
    session.add(user)
    await session.flush()
    return user


async def first_stars_product(session) -> tuple[Product | None, ProductPrice | None]:
    row = await session.execute(
        select(Product, ProductPrice)
        .join(ProductPrice, ProductPrice.product_id == Product.id)
        .where(Product.active == 1, ProductPrice.provider == "telegram_stars", ProductPrice.currency == "XTR")
        .order_by(ProductPrice.amount)
        .limit(1)
    )
    return row.first() or (None, None)


async def run_bot() -> None:
    settings = get_settings()
    settings.validate_runtime()
    if not settings.is_production:
        await create_schema(settings)
    bot = Bot(settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    await dispatcher.start_polling(bot)


def main() -> None:
    asyncio.run(run_bot())


if __name__ == "__main__":
    main()
