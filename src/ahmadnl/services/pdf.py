from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import fitz

from ahmadnl.config import Settings


class PDFProcessingError(ValueError):
    pass


@dataclass(frozen=True)
class ExtractedPDF:
    sha256: str
    byte_size: int
    page_count: int
    title: str | None
    chunks: list[tuple[int, str]]
    storage_path: Path


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def storage_path_for_hash(settings: Settings, digest: str) -> Path:
    return settings.storage_dir / digest[:2] / f"{digest}.pdf"


def validate_pdf_name(filename: str, mime_type: str | None) -> None:
    if not filename.lower().endswith(".pdf"):
        raise PDFProcessingError("Please upload a PDF file.")
    if mime_type and mime_type not in {"application/pdf", "application/x-pdf"}:
        raise PDFProcessingError("The uploaded file does not look like a PDF.")


def process_pdf(data: bytes, filename: str, mime_type: str | None, settings: Settings) -> ExtractedPDF:
    validate_pdf_name(filename, mime_type)
    if len(data) > settings.pdf_max_bytes:
        raise PDFProcessingError(f"PDF is too large. Limit: {settings.pdf_max_bytes // 1024 // 1024} MB.")
    if not data.startswith(b"%PDF"):
        raise PDFProcessingError("The uploaded file is not a valid PDF.")
    digest = sha256_bytes(data)
    storage_path = storage_path_for_hash(settings, digest)
    storage_path.parent.mkdir(parents=True, exist_ok=True)
    storage_path.write_bytes(data)
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # PyMuPDF raises several document-specific exceptions.
        raise PDFProcessingError("The PDF could not be opened.") from exc
    if doc.page_count > settings.pdf_max_pages:
        raise PDFProcessingError(f"PDF has too many pages. Limit: {settings.pdf_max_pages} pages.")
    chunks: list[tuple[int, str]] = []
    for index in range(doc.page_count):
        text = normalize_text(doc.load_page(index).get_text("text"))
        if text:
            chunks.append((index + 1, text))
    if not chunks:
        raise PDFProcessingError("No readable text was found in this PDF.")
    metadata = doc.metadata or {}
    title = normalize_text(metadata.get("title") or "") or None
    return ExtractedPDF(digest, len(data), doc.page_count, title, chunks, storage_path)
