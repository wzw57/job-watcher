from __future__ import annotations

from dataclasses import replace

from job_watcher.collectors.base import CollectionResult
from job_watcher.collectors.fallback import FallbackCollector
from job_watcher.collectors.http import HttpCollector
from job_watcher.config import load_settings


class StaticCollector:
    def __init__(self, result: CollectionResult) -> None:
        self.result = result
        self.calls = 0

    def collect(self, url: str) -> CollectionResult:
        self.calls += 1
        return self.result


class Response:
    status = 200
    headers = {"Content-Type": "text/html"}
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def read(self, limit: int) -> bytes: return b"12345"
    def geturl(self) -> str: return "https://example.com"


class DocumentErrorResponse(Response):
    status = 404
    headers = {"Content-Type": "application/pdf"}
    def read(self, limit: int) -> bytes: return b"not-a-pdf"
    def geturl(self) -> str: return "https://example.com/missing.pdf"


def test_browser_fallback_is_explicit_and_traceable() -> None:
    primary = StaticCollector(CollectionResult("needs_browser", "u", "u"))
    browser = StaticCollector(CollectionResult("success", "u", "u", text="rendered"))
    result = FallbackCollector(primary, browser, browser_enabled=True).collect("u")
    assert result.succeeded and result.metadata["fallback_from"] == "needs_browser" and browser.calls == 1
    browser.calls = 0
    result = FallbackCollector(primary, browser, browser_enabled=False).collect("u")
    assert result.status == "needs_browser" and browser.calls == 0


def test_http_collector_rejects_oversized_response(monkeypatch) -> None:
    settings = load_settings()
    settings = replace(settings, crawler=replace(settings.crawler, max_response_bytes=4, retry_attempts=1))
    monkeypatch.setattr("job_watcher.collectors.http.urlopen", lambda *args, **kwargs: Response())
    result = HttpCollector(settings).collect("https://example.com")
    assert result.status == "too_large" and result.error_type == "response_too_large"


def test_document_http_error_is_not_misclassified_as_parse_failure(monkeypatch) -> None:
    settings = replace(load_settings(), crawler=replace(load_settings().crawler, retry_attempts=1))
    monkeypatch.setattr("job_watcher.collectors.http.urlopen", lambda *args, **kwargs: DocumentErrorResponse())
    result = HttpCollector(settings).collect("https://example.com/missing.pdf")
    assert result.status == "http_error" and result.error_type == "http_404"
    assert result.content_bytes == b"not-a-pdf"
