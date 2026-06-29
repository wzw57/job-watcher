from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any
from urllib.request import Request, urlopen


API_URL = "https://qianfan.baidubce.com/v2/ai_search/web_search"


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str
    source: str = "baidu_web_search"


class BaiduWebSearchProvider:
    def __init__(self, api_key: str | None = None, timeout: int = 30) -> None:
        self.api_key = api_key or os.getenv("BAIDU_SEARCH_API_KEY", "")
        self.timeout = timeout
        self.resolve_ip = os.getenv("BAIDU_RESOLVE_IP", "")
        if not self.api_key:
            raise ValueError("BAIDU_SEARCH_API_KEY is required")

    def search(self, query: str, count: int = 10) -> list[SearchResult]:
        count = max(1, min(20, count))
        body = {
            "messages": [
                {
                    "role": "user",
                    "content": query,
                }
            ],
            "resource_type_filter": [{"type": "web", "top_k": count}],
        }
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        if self.resolve_ip:
            response = self._search_with_curl_resolve(payload)
            ensure_success(response)
            return parse_response(response)
        req = Request(
            API_URL,
            data=payload,
            headers={
                "X-Appbuilder-Authorization": f"Bearer {self.api_key}",
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "qingdao-job-watcher/0.1",
            },
            method="POST",
        )
        with urlopen(req, timeout=self.timeout) as resp:
            response = json.loads(resp.read().decode("utf-8"))
        ensure_success(response)
        return parse_response(response)

    def _search_with_curl_resolve(self, payload: bytes) -> Any:
        cmd = [
            "curl",
            "--ssl-no-revoke",
            "--resolve",
            f"qianfan.baidubce.com:443:{self.resolve_ip}",
            "-sS",
            "--max-time",
            str(self.timeout),
            "-X",
            "POST",
            API_URL,
            "-H",
            f"X-Appbuilder-Authorization: Bearer {self.api_key}",
            "-H",
            f"Authorization: Bearer {self.api_key}",
            "-H",
            "Content-Type: application/json",
            "--data-binary",
            "@-",
        ]
        proc = subprocess.run(cmd, input=payload, capture_output=True, timeout=self.timeout + 5)
        stdout = proc.stdout.decode("utf-8", errors="replace")
        stderr = proc.stderr.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            raise RuntimeError(stderr.strip() or f"curl failed with code {proc.returncode}")
        return json.loads(stdout)


def ensure_success(payload: Any) -> None:
    if not isinstance(payload, dict):
        return
    code = payload.get("code", payload.get("Code", payload.get("error_code")))
    if code in (None, 0, 200, "0", "200"):
        return
    message = payload.get("message") or payload.get("msg") or payload.get("error_msg") or "unknown error"
    raise RuntimeError(f"Baidu API error {code}: {message}")


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

    for key in ("results", "search_results", "references", "items", "list", "data"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = find_items(value)
            if nested:
                return nested

    for value in payload.values():
        if isinstance(value, dict):
            nested = find_items(value)
            if nested:
                return nested
    return []


def normalize_item(item: dict[str, Any]) -> SearchResult | None:
    title = first_text(item, ["title", "name", "Title"])
    url = first_text(item, ["url", "link", "href", "Url"])
    snippet = first_text(item, ["summary", "snippet", "content", "description", "text"])
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
