import re
from dataclasses import dataclass
from pathlib import Path

import fitz


class PdfError(Exception):
    pass


@dataclass
class TextChunk:
    text: str
    page: int
    chunk_index: int


@dataclass
class ExtractedPdf:
    pages: list[str]
    chunks: list[TextChunk]
    character_count: int


def clean_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"(?<=\w)-\n(?=\w)", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_page(text: str, page: int, size: int, overlap: int) -> list[TextChunk]:
    if not text:
        return []
    chunks: list[TextChunk] = []
    start = 0
    index = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            boundary = max(text.rfind("\n", start, end), text.rfind(". ", start, end))
            if boundary > start + size // 2:
                end = boundary + 1
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(TextChunk(text=chunk, page=page, chunk_index=index))
            index += 1
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def extract_pdf(path: Path, chunk_size: int, chunk_overlap: int) -> ExtractedPdf:
    try:
        document = fitz.open(path)
    except Exception as exc:
        raise PdfError("The uploaded file is not a readable PDF.") from exc

    try:
        if document.needs_pass:
            raise PdfError("Password-protected PDFs are not supported.")
        pages: list[str] = []
        chunks: list[TextChunk] = []
        for page_number, page in enumerate(document, start=1):
            text = clean_text(page.get_text("text"))
            pages.append(text)
            chunks.extend(chunk_page(text, page_number, chunk_size, chunk_overlap))
        return ExtractedPdf(
            pages=pages,
            chunks=chunks,
            character_count=sum(len(page) for page in pages),
        )
    finally:
        document.close()

