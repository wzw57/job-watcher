from __future__ import annotations

import hashlib

from job_watcher.collectors.base import CollectionResult
from job_watcher.config import Settings
from job_watcher.parsers.html import discover_attachments, extract_readable_text
from job_watcher.parsers.quality import assess_content_quality


class BrowserCollector:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def collect(self, url: str) -> CollectionResult:
        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError:
            return CollectionResult("browser_unavailable", url, url, error_type="playwright_not_installed",
                                    error_message="install job-watcher[browser] and Playwright Chromium")
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page(user_agent=self.settings.crawler.user_agent)
                response = page.goto(url, wait_until="networkidle", timeout=self.settings.crawler.timeout_seconds * 1000)
                html = page.content()
                final_url = page.url
                browser.close()
            title, text, extraction = extract_readable_text(html)
            digest = hashlib.sha256(text.encode()).hexdigest()
            if not text:
                return CollectionResult("parse_failed", url, final_url, response.status if response else None,
                                        "text/html", title=title, html=html, content_hash=digest,
                                        error_type="empty_browser_text", error_message="browser rendered page has no text")
            quality = assess_content_quality(text, title)
            return CollectionResult("success", url, final_url, response.status if response else None,
                                    "text/html", title, text, html, digest,
                                    metadata={"collector": "browser", **extraction, "quality_score": quality.score,
                                              "quality_flags": list(quality.flags), "text_chars": quality.text_chars},
                                    attachments=discover_attachments(html, final_url))
        except Exception as exc:
            return CollectionResult("browser_error", url, url, error_type=type(exc).__name__, error_message=str(exc)[:500])
