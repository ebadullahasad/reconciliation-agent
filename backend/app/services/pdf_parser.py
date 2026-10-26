import re
from datetime import date
from pathlib import Path

import pdfplumber

# Below this many characters, we assume the PDF has no real text layer
# (i.e. it's a scanned image) and fall back to OCR instead of regex.
MIN_TEXT_LAYER_CHARS = 20

# Label variants kept close to how real invoices phrase these fields, so a
# different template doesn't need a code change - only a new alias here.
INVOICE_NUMBER_PATTERNS = [
    r"invoice\s*(?:#|no\.?|number)?\s*[:\-]?\s*([A-Za-z]{2,}-?\d+)",
]
CUSTOMER_PATTERNS = [
    r"(?:customer|bill\s*to|client)\s*[:\-]\s*(.+)",
]
DATE_PATTERNS = [
    r"(?:invoice\s*)?date\s*[:\-]\s*(.+)",
]
# "Total" is intentionally matched last-onpm install lodashccurrence, since templates often
# also print "Subtotal" earlier in the same document.
TOTAL_PATTERNS = [
    r"(?:grand\s*total|total\s*due|amount\s*due|total)\s*[:\-]?\s*(?:PKR|USD|Rs\.?|\$)?\s*([\d,]+\.\d{2}|[\d,]+)",
]


class PDFParseError(RuntimeError):
    pass


def _extract_text_layer(path: str) -> str:
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


def _extract_text_via_ocr(path: str) -> str:
    try:
        import pytesseract
        from pdf2image import convert_from_path
    except ImportError as exc:
        raise PDFParseError(
            "This PDF has no text layer (looks scanned) and OCR dependencies "
            "aren't installed. Run: pip install pytesseract pdf2image, and "
            "install the tesseract-ocr system package."
        ) from exc

    pages = convert_from_path(path)
    return "\n".join(pytesseract.image_to_string(page) for page in pages)


def extract_text(path: str) -> tuple[str, str]:
    """Returns (text, method) where method is 'text_layer' or 'ocr'."""
    text = _extract_text_layer(path)
    if len(text.strip()) >= MIN_TEXT_LAYER_CHARS:
        return text, "text_layer"
    return _extract_text_via_ocr(path), "ocr"


def _first_match(patterns: list[str], text: str) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _last_match(patterns: list[str], text: str) -> str | None:
    result = None
    for pattern in patterns:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            result = match.group(1).strip()
    return result


def _parse_amount(raw: str) -> float:
    return float(raw.replace(",", ""))


def _parse_date(raw: str) -> date:
    from dateutil import parser as date_parser

    return date_parser.parse(raw, fuzzy=True).date()


def parse_invoice_pdf(path: str) -> dict:
    """Extract {invoice_number, invoice_date, amount, customer_name} from a
    single invoice PDF. Raises PDFParseError with a clear reason if a
    required field can't be found, instead of guessing."""

    text, method = extract_text(path)

    invoice_number = _first_match(INVOICE_NUMBER_PATTERNS, text)
    customer_name = _first_match(CUSTOMER_PATTERNS, text)
    date_raw = _first_match(DATE_PATTERNS, text)
    amount_raw = _last_match(TOTAL_PATTERNS, text)

    missing = [
        name
        for name, value in [
            ("invoice_number", invoice_number),
            ("invoice_date", date_raw),
            ("amount", amount_raw),
        ]
        if value is None
    ]
    if missing:
        raise PDFParseError(
            f"{Path(path).name} (extracted via {method}): could not find required "
            f"field(s) {missing} in the extracted text"
        )

    try:
        invoice_date = _parse_date(date_raw)
        amount = _parse_amount(amount_raw)
    except ValueError as exc:
        raise PDFParseError(f"{Path(path).name}: failed to parse field value: {exc}")

    return {
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "amount": amount,
        "customer_name": customer_name,
    }
