from __future__ import annotations

from io import BytesIO

try:
    from pypdf import PdfReader
except Exception:  # pragma: no cover - optional dependency in some environments
    PdfReader = None


def chunk_text(text: str, max_chars: int = 500) -> list[str]:
    normalized = '\n'.join(line.strip() for line in text.splitlines()).strip()
    if not normalized:
        return []

    paragraphs = [p.strip() for p in normalized.split('\n\n') if p.strip()]
    chunks: list[str] = []
    current = ''

    for para in paragraphs:
        addition = para if not current else f'{current}\n\n{para}'
        if len(addition) <= max_chars:
            current = addition
            continue

        if current:
            chunks.append(current)
            current = ''

        if len(para) <= max_chars:
            current = para
            continue

        start = 0
        while start < len(para):
            chunks.append(para[start:start + max_chars])
            start += max_chars

    if current:
        chunks.append(current)

    return chunks


def extract_text_from_upload(content_type: str, filename: str, data: bytes) -> str:
    guessed_name = (filename or '').lower()
    ctype = (content_type or '').lower()

    if 'pdf' in ctype or guessed_name.endswith('.pdf'):
        if PdfReader is None:
            raise ValueError('PDF parsing is not available. Install pypdf to enable PDF ingestion.')
        reader = PdfReader(BytesIO(data))
        return '\n'.join(page.extract_text() or '' for page in reader.pages)

    try:
        return data.decode('utf-8')
    except UnicodeDecodeError:
        return data.decode('latin-1', errors='ignore')
