from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ahmadnl.config import Settings
from ahmadnl.models import Document, DocumentChunk, DocumentState
from ahmadnl.services.pdf import PDFProcessingError, sha256_bytes, storage_path_for_hash, validate_pdf_name, process_pdf


async def ingest_pdf(
    session: AsyncSession,
    *,
    user_id: str,
    telegram_file_id: str,
    filename: str,
    mime_type: str | None,
    data: bytes,
    settings: Settings,
) -> tuple[Document, bool]:
    """Persist a Telegram PDF upload and extracted page chunks.

    Returns `(document, is_duplicate)`. Duplicate detection is same-user and hash-based.
    """
    validate_pdf_name(filename, mime_type)
    if len(data) > settings.pdf_max_bytes:
        raise PDFProcessingError(f"PDF is too large. Limit: {settings.pdf_max_bytes // 1024 // 1024} MB.")
    digest = sha256_bytes(data)
    existing = await session.scalar(select(Document).where(Document.user_id == user_id, Document.sha256 == digest))
    if existing and existing.state == DocumentState.READY:
        return existing, True

    if existing:
        document = existing
        document.telegram_file_id = telegram_file_id
        document.original_filename = filename
        document.storage_path = str(storage_path_for_hash(settings, digest))
        document.byte_size = len(data)
        document.page_count = 0
        document.title = None
        document.failure_reason = None
        document.state = DocumentState.PROCESSING
        await session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document.id))
    else:
        document = Document(
            user_id=user_id,
            telegram_file_id=telegram_file_id,
            original_filename=filename,
            storage_path=str(storage_path_for_hash(settings, digest)),
            sha256=digest,
            byte_size=len(data),
            state=DocumentState.PROCESSING,
        )
        session.add(document)
    await session.flush()

    try:
        extracted = process_pdf(data, filename, mime_type, settings)
        document.storage_path = str(extracted.storage_path)
        document.page_count = extracted.page_count
        document.title = extracted.title
        document.state = DocumentState.READY
        for page_number, text in extracted.chunks:
            session.add(DocumentChunk(document_id=document.id, page_number=page_number, text=text))
        await session.flush()
    except Exception as exc:
        document.state = DocumentState.FAILED
        document.failure_reason = str(exc)[:1000]
        await session.flush()
        raise

    return document, False
