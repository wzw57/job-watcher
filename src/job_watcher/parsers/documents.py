from __future__ import annotations

import csv
import io
import re
import zipfile
from pathlib import PurePosixPath
from xml.etree import ElementTree


SPACE_RE = re.compile(r"[ \t]+")


class DocumentParseError(RuntimeError):
    def __init__(self, message: str, *, code: str = "document_parse_failed") -> None:
        super().__init__(message)
        self.code = code


def parse_document(data: bytes, filename: str, content_type: str = "") -> str:
    suffix = PurePosixPath(filename.split("?", 1)[0]).suffix.lower()
    try:
        if suffix == ".pdf" or "application/pdf" in content_type:
            return parse_pdf(data)
        if suffix == ".docx" or "wordprocessingml" in content_type:
            return parse_docx(data)
        if suffix == ".xlsx" or "spreadsheetml" in content_type:
            return parse_xlsx(data)
        if suffix == ".csv" or "text/csv" in content_type:
            return parse_csv(data)
        if suffix in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"} or content_type.lower().startswith("image/"):
            raise DocumentParseError(
                "image attachment requires OCR or manual review",
                code="ocr_required",
            )
        if suffix in {".doc", ".xls"}:
            raise DocumentParseError(
                f"legacy Office format requires conversion before parsing: {suffix}",
                code="legacy_office_conversion_required",
            )
    except DocumentParseError:
        raise
    except Exception as exc:  # document parsers must produce a reviewable error.
        raise DocumentParseError(f"failed to parse {suffix or content_type}: {exc}") from exc
    raise DocumentParseError(
        f"unsupported document type: {suffix or content_type}",
        code="unsupported_document_type",
    )


def parse_pdf(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ModuleNotFoundError as exc:
        raise DocumentParseError(
            "PDF parser unavailable: install pypdf",
            code="pdf_parser_unavailable",
        ) from exc
    reader = PdfReader(io.BytesIO(data))
    text = normalize("\n".join(page.extract_text() or "" for page in reader.pages))
    if not text:
        raise DocumentParseError(
            "PDF contains no extractable text; preserve the file and send it to OCR or manual review",
            code="ocr_required",
        )
    return text


def parse_docx(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    return normalize("\n".join(node.text or "" for node in root.iter() if node.tag.endswith("}t")))


def parse_xlsx(data: bytes) -> str:
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = ["".join(n.text or "" for n in item.iter() if n.tag.endswith("}t")) for item in root if item.tag.endswith("}si")]
        rows: list[str] = []
        for name in sorted(n for n in archive.namelist() if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")):
            root = ElementTree.fromstring(archive.read(name))
            for row in (n for n in root.iter() if n.tag.endswith("}row")):
                values: list[str] = []
                for cell in (n for n in row if n.tag.endswith("}c")):
                    value = next((n.text or "" for n in cell if n.tag.endswith("}v")), "")
                    if cell.attrib.get("t") == "s" and value.isdigit() and int(value) < len(shared):
                        value = shared[int(value)]
                    values.append(value)
                if values:
                    rows.append("\t".join(values))
    return normalize("\n".join(rows))


def parse_csv(data: bytes) -> str:
    text = data.decode("utf-8-sig", errors="replace")
    return normalize("\n".join("\t".join(row) for row in csv.reader(io.StringIO(text))))


def normalize(text: str) -> str:
    return "\n".join(SPACE_RE.sub(" ", line).strip() for line in text.splitlines() if line.strip())
