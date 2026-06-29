from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import HTTPError


API_URL = "https://api.bochaai.com/v1/web-search"


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = "bocha_web_search"


class BochaWebSearchProvider:
    def __init__(self, api_key: str | None = None, timeout: int = 30) -> None:
        self.api_key = api_key or os.getenv("BOCHA_API_KEY", "")
        self.timeout = timeout
        if not self.api_key:
            raise ValueError("BOCHA_API_KEY is required")

    def search(self, query: str, count: int = 10, summary: bool = True, freshness: str = "") -> list[SearchResult]:
        count = max(1, min(50, count))
        body: dict[str, Any] = {
            "query": query,
            "count": count,
            "summary": summary,
        }
        if freshness:
            body["freshness"] = freshness
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = Request(
            API_URL,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "qingdao-job-watcher/0.1",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=self.timeout) as resp:
                response = json.loads(resp.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Bocha HTTP {exc.code}: {body[:500]}") from exc
        ensure_success(response)
        return parse_response(response)


def ensure_success(payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    code = payload.get("code", payload.get("Code"))
    if code in (None, 0, 200, "0", "200"):
        return
    message = payload.get("msg") or payload.get("message") or payload.get("Message") or "unknown error"
    raise RuntimeError(f"Bocha API error {code}: {message}")


def parse_response(payload: Any) -> list[SearchResult]:
    items = find_items(payload)
    results: list[SearchResult] = []
    for item in items:
        result = normalize_item(item)
        if result and result.url:
            results.append(result)
    return results


def find_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    data = payload.get("data") or payload.get("Data")
    if isinstance(data, dict):
        web_pages = data.get("webPages") or data.get("webpages") or data.get("web_pages")
        if isinstance(web_pages, dict):
            value = web_pages.get("value") or web_pages.get("items") or web_pages.get("results")
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        value = data.get("value") or data.get("items") or data.get("results")
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]

    for key in ("webPages", "items", "results", "value", "list"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = find_items(value)
            if nested:
                return nested
    return []


def normalize_item(item: dict[str, Any]) -> SearchResult | None:
    title = first_text(item, ["name", "title", "Title"])
    url = first_text(item, ["url", "Url", "link"])
    snippet = first_text(item, ["snippet", "summary", "content", "description", "text"])
    if not title and not url:
        return None
    return SearchResult(clean_text(title), clean_text(url), clean_text(snippet))


def first_text(item: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def clean_text(value: str) -> str:
    return " ".join(str(value).replace("\n", " ").split())
