from pypdf import PdfReader
from io import BytesIO


def parse_pdf(file_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(file_bytes))
    pages_text = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages_text.append(text.strip())
    return "\n\n".join(pages_text)


def count_pages(file_bytes: bytes) -> int:
    reader = PdfReader(BytesIO(file_bytes))
    return len(reader.pages)
