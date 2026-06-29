from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_BASE = "https://developer.zhihu.com"
GLOBAL_SEARCH_PATH = "/api/v1/content/global_search"


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = "zhihu_global_search"


class ZhihuGlobalSearchProvider:
    def __init__(self, api_key: str | None = None, timeout: int = 20) -> None:
        self.api_key = api_key or os.getenv("ZHIHU_API_KEY", "")
        self.timeout = timeout
        self.resolve_ip = os.getenv("ZHIHU_RESOLVE_IP", "")
        if not self.api_key:
            raise ValueError("ZHIHU_API_KEY is required")

    def search(
        self,
        query: str,
        count: int = 10,
        filter_expr: str = "",
        search_db: str = "all",
    ) -> list[SearchResult]:
        count = max(1, min(20, count))
        params = {"Query": query, "Count": str(count)}
        if filter_expr:
            params["Filter"] = filter_expr
        if search_db:
            params["SearchDB"] = search_db
        url = f"{API_BASE}{GLOBAL_SEARCH_PATH}?{urlencode(params)}"
        if self.resolve_ip:
            payload = self._search_with_curl_resolve(url)
            return parse_global_search_response(payload)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Request-Timestamp": str(int(time.time())),
            "Accept": "application/json",
            "User-Agent": "qingdao-job-watcher/0.1",
        }
        req = Request(url, headers=headers, method="GET")
        with urlopen(req, timeout=self.timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        ensure_success(payload)
        return parse_global_search_response(payload)

    def _search_with_curl_resolve(self, url: str) -> Any:
        cmd = [
            "curl",
            "--ssl-no-revoke",
            "--resolve",
            f"developer.zhihu.com:443:{self.resolve_ip}",
            "-sS",
            "--max-time",
            str(self.timeout),
            "-H",
            f"Authorization: Bearer {self.api_key}",
            "-H",
            f"X-Request-Timestamp: {int(time.time())}",
            "-H",
            "Content-Type: application/json",
            url,
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=self.timeout + 5)
        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(stderr.strip() or f"curl failed with code {proc.returncode}")
        payload = json.loads(stdout)
        ensure_success(payload)
        return payload


def ensure_success(payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    code = payload.get("Code")
    if code not in (None, 0):
        message = payload.get("Message", "unknown error")
        raise RuntimeError(f"Zhihu API error {code}: {message}")


def parse_global_search_response(payload: Any) -> list[SearchResult]:
    items = find_result_items(payload)
    results: list[SearchResult] = []
    for item in items:
        normalized = normalize_item(item)
        if normalized and normalized.url:
            results.append(normalized)
    return results


def find_result_items(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []

    data = payload.get("Data")
    if isinstance(data, dict):
        items = data.get("Items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]

    for key in ("data", "results", "items", "list"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = find_result_items(value)
            if nested:
                return nested

    for value in payload.values():
        if isinstance(value, dict):
            nested = find_result_items(value)
            if nested:
                return nested
    return []


def normalize_item(item: dict[str, Any]) -> SearchResult | None:
    title = first_text(item, ["Title", "title", "name", "display_name"])
    url = first_text(item, ["Url", "url", "link", "target_url", "source_url", "share_url"])
    snippet = first_text(
        item,
        ["ContentText", "snippet", "summary", "excerpt", "description", "content"],
    )

    if not url:
        nested_url = find_first_url(item)
        url = nested_url or ""
    if not title:
        title = item.get("type", "") if isinstance(item.get("type"), str) else ""
    if not snippet:
        snippet = ""

    if not title and not url:
        return None
    return SearchResult(clean_text(title), clean_text(url), clean_text(snippet))


def first_text(item: dict[str, Any], keys: list[str]) -> str:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value
        if isinstance(value, dict):
            text = first_text(value, keys)
            if text:
                return text
    return ""


def find_first_url(value: Any) -> str:
    if isinstance(value, str) and value.startswith(("http://", "https://")):
        return value
    if isinstance(value, dict):
        for nested in value.values():
            url = find_first_url(nested)
            if url:
                return url
    if isinstance(value, list):
        for nested in value:
            url = find_first_url(nested)
            if url:
                return url
    return ""


def clean_text(value: str) -> str:
    return " ".join(str(value).replace("\n", " ").split())
