"""
Document processor for Gmail attachment text extraction.
Bounded BL-06 implementation: PDF, image OCR, DOCX, XLSX/CSV, ICS.
"""
from __future__ import annotations

import importlib
import io
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class UnsupportedFileType(Exception):
    pass


class FileTooLarge(Exception):
    pass


class PasswordProtected(Exception):
    pass


# ---------------------------------------------------------------------------
# MIME -> type mapping
# ---------------------------------------------------------------------------

SUPPORTED_MIME_TYPES: dict[str, str] = {
    "application/pdf": "pdf",
    "image/jpeg": "image",
    "image/png": "image",
    "image/webp": "image",
    "image/gif": "image",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "spreadsheet",
    "text/csv": "spreadsheet",
    "text/calendar": "calendar",
}

SUPPORTED_EXTENSIONS: dict[str, str] = {
    ".pdf": "pdf",
    ".jpg": "image",
    ".jpeg": "image",
    ".png": "image",
    ".webp": "image",
    ".gif": "image",
    ".docx": "docx",
    ".xlsx": "spreadsheet",
    ".csv": "spreadsheet",
    ".ics": "calendar",
}

MAX_BYTES: dict[str, int] = {
    "pdf": 10 * 1024 * 1024,         # 10 MB
    "image": 5 * 1024 * 1024,        # 5 MB
    "docx": 5 * 1024 * 1024,         # 5 MB
    "spreadsheet": 2 * 1024 * 1024,  # 2 MB
    "calendar": 1 * 1024 * 1024,     # 1 MB
}

MAX_EXTRACTED_CHARS = 8000
MAX_SPREADSHEET_ROWS = 1000
MAX_OCR_PAGES = 5


def _truncate(text: str) -> str:
    return (text or "")[:MAX_EXTRACTED_CHARS]


def resolve_doc_type(mime_type: str, filename: str) -> str:
    """Return canonical doc type string or raise UnsupportedFileType."""
    normalized_mime = (mime_type or "").lower().split(";")[0].strip()
    if normalized_mime in SUPPORTED_MIME_TYPES:
        return SUPPORTED_MIME_TYPES[normalized_mime]

    ext = ""
    if filename and "." in filename:
        ext = "." + filename.rsplit(".", 1)[-1].lower()

    if ext in SUPPORTED_EXTENSIONS:
        return SUPPORTED_EXTENSIONS[ext]

    raise UnsupportedFileType(
        f"Unsupported attachment: mime={mime_type!r}, filename={filename!r}"
    )


def is_supported_attachment(mime_type: str, filename: str) -> bool:
    """Return True if this attachment can be processed."""
    try:
        resolve_doc_type(mime_type, filename)
        return True
    except UnsupportedFileType:
        return False


# ---------------------------------------------------------------------------
# Extractors
# ---------------------------------------------------------------------------

def _extract_pdf(data: bytes) -> str:
    """
    Native extraction first, OCR fallback if text is too thin.
    Password-protected/encrypted PDFs raise PasswordProtected.
    """
    text = ""

    # First: encryption pre-check via PyMuPDF if available
    try:
        fitz = importlib.import_module("fitz")  # PyMuPDF
        doc = fitz.open(stream=data, filetype="pdf")
        try:
            if getattr(doc, "needs_pass", False) or getattr(doc, "is_encrypted", False):
                raise PasswordProtected("PDF is encrypted or password-protected")
        finally:
            doc.close()
    except PasswordProtected:
        raise
    except Exception as e:
        logger.warning("PDF encryption pre-check failed: %s", e)

    # Native extraction via pdfplumber first
    try:
        pdfplumber = importlib.import_module("pdfplumber")
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            parts: list[str] = []
            for page in pdf.pages:
                parts.append(page.extract_text() or "")
            text = "\n".join(parts).strip()
    except PasswordProtected:
        raise
    except Exception as e:
        logger.warning("pdfplumber extraction failed: %s", e)

    # Fallback native extraction via PyMuPDF if text is too thin
    if len(text.strip()) < 100:
        alt_text = _extract_pdf_pymupdf(data)
        if len(alt_text) > len(text):
            text = alt_text

    # OCR fallback for scanned/thin PDFs
    if len(text.strip()) < 100:
        logger.info("PDF has no selectable text, attempting OCR")
        text = _pdf_ocr_fallback(data)

    return _truncate(text)


def _extract_pdf_pymupdf(data: bytes) -> str:
    try:
        fitz = importlib.import_module("fitz")  # PyMuPDF

        doc = fitz.open(stream=data, filetype="pdf")
        try:
            if getattr(doc, "needs_pass", False) or getattr(doc, "is_encrypted", False):
                raise PasswordProtected("PDF is encrypted or password-protected")
            parts = [page.get_text() or "" for page in doc]
            return _truncate("\n".join(parts).strip())
        finally:
            doc.close()
    except PasswordProtected:
        raise
    except Exception as e:
        logger.warning("PyMuPDF extraction failed: %s", e)
        return ""


def _pdf_ocr_fallback(data: bytes) -> str:
    try:
        convert_from_bytes = importlib.import_module("pdf2image").convert_from_bytes
        pytesseract = importlib.import_module("pytesseract")

        images = convert_from_bytes(data, dpi=150)
        parts = [pytesseract.image_to_string(img) for img in images[:MAX_OCR_PAGES]]
        return _truncate("\n".join(parts).strip())
    except Exception as e:
        logger.warning("PDF OCR fallback failed: %s", e)
        return ""


def _extract_image(data: bytes) -> str:
    try:
        image_module = importlib.import_module("PIL.Image")
        pytesseract = importlib.import_module("pytesseract")

        img = image_module.open(io.BytesIO(data))
        text = pytesseract.image_to_string(img) or ""
        return _truncate(text.strip())
    except Exception as e:
        logger.warning("Image OCR failed: %s", e)
        return ""


def _extract_docx(data: bytes) -> str:
    try:
        Document = importlib.import_module("docx").Document

        doc = Document(io.BytesIO(data))
        parts: list[str] = []

        for para in doc.paragraphs:
            if para.text and para.text.strip():
                parts.append(para.text.strip())

        for table in doc.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                row_text = " | ".join(c for c in cells if c)
                if row_text:
                    parts.append(row_text)

        return _truncate("\n".join(parts))
    except Exception as e:
        logger.warning("DOCX extraction failed: %s", e)
        return ""


def _extract_csv(data: bytes) -> str:
    try:
        text = data.decode("utf-8", errors="replace")
        rows = text.splitlines()[:MAX_SPREADSHEET_ROWS]
        return _truncate("\n".join(rows))
    except Exception as e:
        logger.warning("CSV extraction failed: %s", e)
        return ""


def _extract_spreadsheet(data: bytes, filename: str) -> str:
    try:
        openpyxl = importlib.import_module("openpyxl")
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as e:
        logger.warning("Spreadsheet extraction failed for %s: %s", filename, e)
        return ""

    rows: list[str] = []
    row_count = 0

    try:
        for sheet in wb.worksheets:
            rows.append(f"[Sheet: {sheet.title}]")

            for row in sheet.iter_rows(values_only=True):
                if row_count >= MAX_SPREADSHEET_ROWS:
                    break

                cells = [str(c) if c is not None else "" for c in row]
                line = "\t".join(cells).strip()
                if line:
                    rows.append(line)

                row_count += 1

            if row_count >= MAX_SPREADSHEET_ROWS:
                break

            if len("\n".join(rows)) > MAX_EXTRACTED_CHARS:
                break

        return _truncate("\n".join(rows))
    finally:
        try:
            wb.close()
        except Exception:
            pass


def _extract_calendar(data: bytes) -> str:
    try:
        Calendar = importlib.import_module("icalendar").Calendar

        cal = Calendar.from_ical(data)
        parts: list[str] = []

        for component in cal.walk():
            if component.name != "VEVENT":
                continue

            summary = str(component.get("SUMMARY", ""))
            description = str(component.get("DESCRIPTION", ""))
            location = str(component.get("LOCATION", ""))

            dtstart = component.get("DTSTART")
            dtend = component.get("DTEND")

            start_val = str(getattr(dtstart, "dt", dtstart) or "")
            end_val = str(getattr(dtend, "dt", dtend) or "")

            entry = f"Event: {summary}\nStart: {start_val}\nEnd: {end_val}"
            if location:
                entry += f"\nLocation: {location}"
            if description:
                entry += f"\nDescription: {description[:500]}"

            parts.append(entry)

        return _truncate("\n\n".join(parts))
    except Exception as e:
        logger.warning("ICS extraction failed: %s", e)
        return ""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class DocumentProcessor:
    """Extract plain text from Gmail attachment bytes."""

    def process(self, content_bytes: bytes, mime_type: str, filename: str) -> dict:
        """
        Returns structured extraction result.
        Raises UnsupportedFileType, FileTooLarge, PasswordProtected.
        """
        doc_type = resolve_doc_type(mime_type, filename)
        limit = MAX_BYTES[doc_type]

        if len(content_bytes) > limit:
            raise FileTooLarge(
                f"{filename!r} is {len(content_bytes)} bytes, limit for {doc_type} is {limit}"
            )

        if doc_type == "pdf":
            extracted_text = _extract_pdf(content_bytes)
        elif doc_type == "image":
            extracted_text = _extract_image(content_bytes)
        elif doc_type == "docx":
            extracted_text = _extract_docx(content_bytes)
        elif doc_type == "spreadsheet":
            normalized_mime = (mime_type or "").lower().split(";")[0].strip()
            if normalized_mime == "text/csv" or (filename or "").lower().endswith(".csv"):
                extracted_text = _extract_csv(content_bytes)
            else:
                extracted_text = _extract_spreadsheet(content_bytes, filename)
        elif doc_type == "calendar":
            extracted_text = _extract_calendar(content_bytes)
        else:
            raise UnsupportedFileType(f"No extractor for doc_type={doc_type!r}")

        return {
            "extracted_text": _truncate(extracted_text),
            "document_type": doc_type,
            "attachment_filename": filename or "",
        }

    def extract(self, data: bytes, mime_type: str, filename: str) -> str:
        """
        Backward-compatible helper. Returns extracted text only.
        Raises UnsupportedFileType, FileTooLarge, PasswordProtected.
        """
        return self.process(
            content_bytes=data,
            mime_type=mime_type,
            filename=filename,
        )["extracted_text"]
        