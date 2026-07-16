from __future__ import annotations

from dataclasses import replace

from job_watcher.collectors.base import CollectionResult, Collector


class FallbackCollector:
    def __init__(self, primary: Collector, browser: Collector, *, browser_enabled: bool) -> None:
        self.primary = primary
        self.browser = browser
        self.browser_enabled = browser_enabled

    def collect(self, url: str) -> CollectionResult:
        primary = self.primary.collect(url)
        if primary.status not in {"needs_browser", "blocked"} or not self.browser_enabled:
            return primary
        rendered = self.browser.collect(url)
        if rendered.succeeded:
            return replace(rendered, metadata={**dict(rendered.metadata), "fallback_from": primary.status})
        return replace(primary, metadata={**dict(primary.metadata), "browser_fallback_status": rendered.status,
                                          "browser_fallback_error": rendered.error_message})
