from __future__ import annotations

from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit


ATTACHMENT_EXTENSIONS = (".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv")


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
