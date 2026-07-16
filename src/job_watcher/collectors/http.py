from __future__ import annotations

import hashlib
import html
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from job_watcher.collectors.base import CollectionResult
from job_watcher.config import Settings
from job_watcher.parsers.documents import DocumentParseError, parse_document
from job_watcher.parsers.html import ATTACHMENT_EXTENSIONS, discover_attachments


TAG_RE = re.compile(r"<[^>]+>")
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
SPACE_RE = re.compile(r"\s+")
JS_SHELL_MARKERS = ("enable javascript", "请开启javascript", "__next_data__", "id=\"app\"")


class HttpCollector:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def collect(self, url: str) -> CollectionResult:
        request = Request(url, headers={
            "User-Agent": self.settings.crawler.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
        })
        try:
            with urlopen(request, timeout=self.settings.crawler.timeout_seconds) as response:
                raw = response.read()
                final_url = response.geturl()
                status = int(getattr(response, "status", 200))
                content_type = response.headers.get("Content-Type", "")
        except HTTPError as exc:
            raw = exc.read()
            final_url = exc.geturl()
            status = int(exc.code)
            content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
        except (URLError, TimeoutError, OSError) as exc:
            return CollectionResult("network_error", url, url, error_type=type(exc).__name__, error_message=str(exc)[:500])

        if is_document(final_url, content_type):
            digest = hashlib.sha256(raw).hexdigest()
            try:
                text = parse_document(raw, final_url, content_type)
                if not text.strip():
                    raise DocumentParseError("document contains no extractable text; OCR or manual review required")
            except DocumentParseError as exc:
                return CollectionResult("parse_failed", url, final_url, status, content_type,
                                        content_hash=digest, error_type="document_parse_failed",
                                        error_message=str(exc), metadata={"bytes": len(raw), "document": True})
            return CollectionResult("success", url, final_url, status, content_type,
                                    title=final_url.rsplit("/", 1)[-1].split("?", 1)[0], text=text,
                                    content_hash=digest, metadata={"bytes": len(raw), "document": True})

        body = raw.decode(guess_encoding(content_type), errors="replace")
        title, text = extract_text(body)
        digest = hashlib.sha256(normalize_for_hash(text or body).encode()).hexdigest()
        if status in {401, 403, 429}:
            result_status, error_type = "blocked", f"http_{status}"
        elif status >= 400:
            result_status, error_type = "http_error", f"http_{status}"
        elif looks_like_js_shell(body, text):
            result_status, error_type = "needs_browser", "javascript_required"
        elif not text:
            result_status, error_type = "parse_failed", "empty_extracted_text"
        else:
            result_status, error_type = "success", ""
        return CollectionResult(
            result_status, url, final_url, status, content_type, title, text, body, digest,
            error_type, "" if result_status == "success" else f"collection status: {result_status}",
            {"bytes": len(raw)}, discover_attachments(body, final_url),
        )


def guess_encoding(content_type: str) -> str:
    match = re.search(r"charset=([\w-]+)", content_type, re.IGNORECASE)
    return match.group(1) if match else "utf-8"


def extract_text(html_text: str) -> tuple[str, str]:
    title_match = TITLE_RE.search(html_text)
    title = html.unescape(SPACE_RE.sub(" ", title_match.group(1)).strip()) if title_match else ""
    body = SCRIPT_RE.sub(" ", html_text)
    body = TAG_RE.sub(" ", body)
    return title, html.unescape(SPACE_RE.sub(" ", body).strip())


def normalize_for_hash(text: str) -> str:
    return SPACE_RE.sub(" ", text).strip()


def looks_like_js_shell(html_text: str, text: str) -> bool:
    lower = html_text.lower()
    return len(text) < 120 and any(marker in lower for marker in JS_SHELL_MARKERS)


def is_document(url: str, content_type: str) -> bool:
    path = url.split("?", 1)[0].lower()
    return path.endswith(ATTACHMENT_EXTENSIONS) or any(x in content_type.lower() for x in ("application/pdf", "wordprocessingml", "spreadsheetml", "text/csv"))
