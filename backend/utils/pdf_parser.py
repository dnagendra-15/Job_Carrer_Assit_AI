from pypdf import PdfReader
from io import BytesIO

from backend.utils.text_cleaner import clean_resume_text


def parse_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(file_bytes))
    pages_text = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages_text.append(text.strip())
    raw_text = "\n\n".join(pages_text)
    # Normalize once here -- this cleaned version is what gets passed to
    # every downstream LLM node, so noise removed here is removed everywhere.
    return clean_resume_text(raw_text)


def count_pages(file_bytes: bytes) -> int:
    reader = PdfReader(BytesIO(file_bytes))
    return len(reader.pages)
