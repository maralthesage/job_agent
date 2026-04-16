import io


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """
    Extract text from PDF bytes.

    Args:
        pdf_bytes: raw PDF file content

    Returns:
        extracted text, stripped and joined with newlines
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError(
            "pypdf is required for PDF parsing. "
            "Install it with: pip install pypdf"
        )

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        text_parts = []
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)
        return "\n".join(text_parts).strip()
    except Exception as e:
        raise ValueError(f"Failed to extract PDF text: {e}")
