"""Extract plain text from uploaded PDF, DOCX, or TXT files."""

from __future__ import annotations

import io


def extract_text_from_file(file_bytes: bytes, filename: str) -> str:
    """Detect format from extension and return extracted plain text.

    Supported formats: .pdf (PyPDF2), .docx (python-docx), .txt (UTF-8 decode).
    Raises ValueError for unsupported formats.
    """
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext == "pdf":
        return _extract_pdf(file_bytes)
    elif ext == "docx":
        return _extract_docx(file_bytes)
    elif ext == "txt":
        return file_bytes.decode("utf-8", errors="replace")
    else:
        raise ValueError(
            f"Unsupported file format '.{ext}'. Use .pdf, .docx, or .txt"
        )


def _extract_pdf(file_bytes: bytes) -> str:
    from PyPDF2 import PdfReader

    reader = PdfReader(io.BytesIO(file_bytes))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(p.strip() for p in pages if p.strip())


def _extract_docx(file_bytes: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)
