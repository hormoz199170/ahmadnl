import asyncio
from io import BytesIO

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, LabeledPrice, Message, PreCheckoutQuery
from sqlalchemy import select

from ahmadnl.config import get_settings
from ahmadnl.db import create_schema, make_session_factory
from ahmadnl.models import Document, DocumentState, OrderStatus, Product, ProductPrice, User
from ahmadnl.services.credits import balance, grant_daily_free
from ahmadnl.services.documents import ingest_pdf
from ahmadnl.services.payments import complete_successful_payment, create_order, verify_order_for_checkout
from ahmadnl.services.ai import AIError, GeminiProvider, ReadingAssistant, ReadingTask
from ahmadnl.services.credits import CreditError
from ahmadnl.services.reading import run_reading_operation
from ahmadnl.services.pdf import PDFProcessingError

router = Router()

WELCOME = """Welcome to AhmadNL.

Turn any PDF into a guided reading experience:
• Summary
• Key points
• Study questions
• Answer guidance

Upload a PDF to start. Your daily free credits make the first steps clear before you buy more.
Use /documents to continue with a processed PDF. Use /credits to check your balance or /buy to buy credits with Telegram Stars when checkout is configured."""


def session_factory():
    return make_session_factory(get_settings())


@router.message(CommandStart())
async def start(message: Message) -> None:
    settings = get_settings()
    async with session_factory()() as session, session.begin():
        user = await upsert_user(session, message)
        await grant_daily_free(session, user.id, settings.daily_free_credits)
        credits = await balance(session, user.id)
    await message.answer(f"{WELCOME}\n\nAvailable credits: {credits}", reply_markup=main_menu_keyboard())


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


@router.message(Command("documents"))
async def documents(message: Message) -> None:
    async with session_factory()() as session, session.begin():
        user = await upsert_user(session, message)
        rows = (
            await session.execute(
                select(Document)
                .where(Document.user_id == user.id, Document.state == DocumentState.READY)
                .order_by(Document.created_at.desc())
                .limit(5)
            )
        ).scalars().all()
    if not rows:
        await message.answer("No processed PDFs yet. Upload a PDF to create your first guided reading document.")
        return
    await message.answer("Choose a processed PDF:", reply_markup=documents_keyboard(rows))


@router.callback_query(F.data == "menu")
async def menu_callback(query: CallbackQuery) -> None:
    await query.message.answer(WELCOME, reply_markup=main_menu_keyboard())
    await query.answer()


@router.callback_query(F.data == "documents")
async def documents_callback(query: CallbackQuery) -> None:
    async with session_factory()() as session, session.begin():
        user = await upsert_user_from_callback(session, query)
        rows = (
            await session.execute(
                select(Document)
                .where(Document.user_id == user.id, Document.state == DocumentState.READY)
                .order_by(Document.created_at.desc())
                .limit(5)
            )
        ).scalars().all()
    if not rows:
        await query.message.answer("No processed PDFs yet. Upload a PDF to create your first guided reading document.")
    else:
        await query.message.answer("Choose a processed PDF:", reply_markup=documents_keyboard(rows))
    await query.answer()


@router.callback_query(F.data.startswith("doc:"))
async def document_actions(query: CallbackQuery) -> None:
    document_id = query.data.split(":", 1)[1]
    async with session_factory()() as session, session.begin():
        user = await upsert_user_from_callback(session, query)
        document = await session.get(Document, document_id)
        if not document or document.user_id != user.id or document.state != DocumentState.READY:
            await query.message.answer("I could not find that processed PDF. Use /documents to choose another one.")
            await query.answer()
            return
    await query.message.answer(f"Reading actions for {document_label(document)}:", reply_markup=reading_keyboard(document.id))
    await query.answer()


@router.callback_query(F.data.startswith("ai:"))
async def ai_action(query: CallbackQuery) -> None:
    _, task_value, document_id = query.data.split(":", 2)
    task = ReadingTask(task_value)
    settings = get_settings()
    assistant = ReadingAssistant(
        GeminiProvider(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout_seconds=settings.ai_timeout_seconds,
            max_retries=settings.ai_max_retries,
            max_output_tokens=settings.ai_max_output_tokens,
        ),
        settings,
    )
    await query.message.answer(f"Working on {task_title(task)}. I will reuse the extracted PDF text and cached results when available.")
    try:
        async with session_factory()() as session, session.begin():
            user = await upsert_user_from_callback(session, query)
            result = await run_reading_operation(
                session,
                assistant=assistant,
                settings=settings,
                user_id=user.id,
                document_id=document_id,
                task=task,
            )
            content = result.ai_result.content or "No result was returned."
            title = document_label(result.document)
            cached = result.cached
            credits_left = result.credits_left
    except CreditError:
        await query.message.answer(await purchase_options_text("You do not have enough credits for this reading action."))
        await query.answer()
        return
    except AIError as exc:
        await query.message.answer(str(exc))
        await query.answer()
        return
    except Exception:
        await query.message.answer("I could not complete that reading action. Please try again later.")
        await query.answer()
        return

    prefix = "Cached result" if cached else "New result"
    await send_long_message(query.message, f"{prefix}: {task_title(task)} for {title}\nCredits left: {credits_left}\n\n{content}")
    await query.message.answer("Continue with this PDF:", reply_markup=reading_keyboard(document_id))
    await query.answer()


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
            f"You already uploaded this PDF. I will reuse the extracted document with {stored.page_count} pages for reading actions.",
            reply_markup=reading_keyboard(stored.id),
        )
    else:
        await message.answer(
            f"PDF is ready: {stored.page_count} pages extracted. Choose what you want next:",
            reply_markup=reading_keyboard(stored.id),
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


async def upsert_user_from_callback(session, query: CallbackQuery) -> User:
    telegram_user = query.from_user
    user = await session.scalar(select(User).where(User.telegram_id == telegram_user.id))
    if user:
        user.username = telegram_user.username
        return user
    user = User(telegram_id=telegram_user.id, username=telegram_user.username)
    session.add(user)
    await session.flush()
    return user


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="My Documents", callback_data="documents")],
            [InlineKeyboardButton(text="Buy Credits", callback_data="buy_hint")],
        ]
    )


def documents_keyboard(documents: list[Document]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text=document_label(document), callback_data=f"doc:{document.id}")] for document in documents]
    )


def reading_keyboard(document_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Summary", callback_data=f"ai:{ReadingTask.SUMMARY.value}:{document_id}")],
            [InlineKeyboardButton(text="Key Points", callback_data=f"ai:{ReadingTask.KEY_POINTS.value}:{document_id}")],
            [InlineKeyboardButton(text="Study Questions", callback_data=f"ai:{ReadingTask.STUDY_QUESTIONS.value}:{document_id}")],
            [InlineKeyboardButton(text="Answer Guidance", callback_data=f"ai:{ReadingTask.ANSWER_GUIDANCE.value}:{document_id}")],
            [InlineKeyboardButton(text="My Documents", callback_data="documents")],
        ]
    )


@router.callback_query(F.data == "buy_hint")
async def buy_hint(query: CallbackQuery) -> None:
    await query.message.answer("Use /buy to see configured Telegram Stars credit packs. No payment is recorded until Telegram confirms it.")
    await query.answer()


def document_label(document: Document) -> str:
    title = document.title or document.original_filename
    if len(title) > 40:
        title = title[:37] + "..."
    return f"{title} ({document.page_count} pages)"


def task_title(task: ReadingTask) -> str:
    return {
        ReadingTask.SUMMARY: "Summary",
        ReadingTask.KEY_POINTS: "Key Points",
        ReadingTask.STUDY_QUESTIONS: "Study Questions",
        ReadingTask.ANSWER_GUIDANCE: "Answer Guidance",
    }[task]


async def send_long_message(message: Message, text: str) -> None:
    for start in range(0, len(text), 3900):
        await message.answer(text[start : start + 3900])


async def purchase_options_text(prefix: str) -> str:
    async with session_factory()() as session, session.begin():
        product, price = await first_stars_product(session)
    if not product or not price:
        return f"{prefix} Credit packs are not configured yet. No payment was started."
    return (
        f"{prefix}\n\n"
        f"Available pack: {product.name} — {product.credits} credits for {price.amount} Telegram Stars.\n"
        "Use /buy to start Telegram Stars checkout. No payment is recorded until Telegram confirms it."
    )


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
