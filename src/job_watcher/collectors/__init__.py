from job_watcher.collectors.base import CollectionResult, Collector
from job_watcher.collectors.browser import BrowserCollector
from job_watcher.collectors.fallback import FallbackCollector
from job_watcher.collectors.http import HttpCollector
from job_watcher.config import Settings


def build_collector(settings: Settings) -> Collector:
    return FallbackCollector(HttpCollector(settings), BrowserCollector(settings),
                             browser_enabled=settings.crawler.browser_fallback_enabled)


__all__ = ["BrowserCollector", "CollectionResult", "Collector", "FallbackCollector", "HttpCollector", "build_collector"]
