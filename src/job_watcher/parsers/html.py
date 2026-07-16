from __future__ import annotations

from html.parser import HTMLParser
import re
from urllib.parse import urljoin, urlsplit, urlunsplit


ATTACHMENT_EXTENSIONS = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv",
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp",
)
SKIP_TAGS = {"script", "style", "noscript", "svg", "canvas", "nav", "footer", "header", "form"}
BLOCK_TAGS = {"p", "div", "li", "tr", "br", "h1", "h2", "h3", "h4", "section", "article"}


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[tuple[str, str]] = []
        self._href = ""
        self._text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "a":
            self._href = dict(attrs).get("href") or ""
            self._text = []

    def handle_data(self, data: str) -> None:
        if self._href:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            self.links.append((self._href, " ".join(self._text).strip()))
            self._href = ""
            self._text = []


class ReadableTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: list[str] = []
        self.all_text: list[str] = []
        self.main_text: list[str] = []
        self._skip_depth = 0
        self._main_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS:
            self._skip_depth += 1
        if tag in {"main", "article"}:
            self._main_depth += 1
        if tag == "title":
            self._in_title = True
        if tag in BLOCK_TAGS and not self._skip_depth:
            self.all_text.append("\n")
            if self._main_depth:
                self.main_text.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        if tag in {"main", "article"} and self._main_depth:
            self._main_depth -= 1
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title.append(data)
        if self._skip_depth or not data.strip():
            return
        self.all_text.append(data)
        if self._main_depth:
            self.main_text.append(data)

def canonicalize_url(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))


def discover_attachments(html_text: str, base_url: str) -> tuple[dict[str, str], ...]:
    parser = LinkParser()
    parser.feed(html_text)
    found: list[dict[str, str]] = []
    seen: set[str] = set()
    for href, label in parser.links:
        absolute = canonicalize_url(urljoin(base_url, href))
        path = urlsplit(absolute).path.lower()
        if not absolute.startswith(("http://", "https://")) or not path.endswith(ATTACHMENT_EXTENSIONS):
            continue
        if absolute in seen:
            continue
        seen.add(absolute)
        found.append({"url": absolute, "label": label, "extension": next(ext for ext in ATTACHMENT_EXTENSIONS if path.endswith(ext))})
    return tuple(found)


def extract_readable_text(html_text: str) -> tuple[str, str, dict[str, object]]:
    parser = ReadableTextParser()
    parser.feed(html_text)
    main = normalize_text(" ".join(parser.main_text))
    all_text = normalize_text(" ".join(parser.all_text))
    selected = main if len(main) >= 120 else all_text
    title = re.sub(r"\s+", " ", " ".join(parser.title)).strip()
    return title, selected, {"used_main_content": selected == main and bool(main), "main_chars": len(main), "text_chars": len(selected)}


def normalize_text(text: str) -> str:
    lines = []
    for line in text.splitlines():
        line = re.sub(r"[ \t\r\f\v]+", " ", line).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)
