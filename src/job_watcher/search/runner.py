from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass

from job_watcher.config import Settings
from job_watcher.search.baidu_provider import BaiduWebSearchProvider
from job_watcher.search.bocha_provider import BochaWebSearchProvider
from job_watcher.search.zhihu_provider import ZhihuGlobalSearchProvider


@dataclass(frozen=True)
class SearchRunResult:
    tasks_checked: int
    tasks_done: int
    results_inserted: int
    results_seen: int
    errors: int


def run_pending_search_tasks(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    limit: int = 20,
    count: int = 5,
) -> SearchRunResult:
    tasks = conn.execute(
        """
        SELECT id, company_id, query, provider
        FROM search_tasks
        WHERE status = 'pending'
        ORDER BY
          CASE reason
            WHEN 'broad_discovery' THEN 0
            WHEN 'site_search' THEN 1
            ELSE 2
          END,
          id
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    checked = done = inserted = seen = errors = 0
    for task in tasks:
        checked += 1
        try:
            provider = make_provider(str(task["provider"]), settings)
            results = provider.search(str(task["query"]), count=count)
            for rank, item in enumerate(results, start=1):
                seen += 1
                cur = conn.execute(
                    """
                    INSERT OR IGNORE INTO search_results (
                        task_id, company_id, provider, rank, title, url, snippet
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(task["id"]),
                        task["company_id"],
                        str(task["provider"]),
                        rank,
                        item.title,
                        item.url,
                        item.snippet,
                    ),
                )
                inserted += cur.rowcount
            conn.execute(
                "UPDATE search_tasks SET status = 'done', executed_at = CURRENT_TIMESTAMP, error = NULL WHERE id = ?",
                (int(task["id"]),),
            )
            done += 1
        except Exception as exc:  # noqa: BLE001 - one provider failure must not stop the queue.
            conn.execute(
                """
                UPDATE search_tasks
                SET status = 'error', executed_at = CURRENT_TIMESTAMP, error = ?
                WHERE id = ?
                """,
                (str(exc)[:500], int(task["id"])),
            )
            errors += 1
        conn.commit()
        time.sleep(0.3)
    return SearchRunResult(
        tasks_checked=checked,
        tasks_done=done,
        results_inserted=inserted,
        results_seen=seen,
        errors=errors,
    )


def make_provider(provider: str, settings: Settings):
    if provider == "baidu":
        return BaiduWebSearchProvider(api_key=settings.search.baidu_api_key, timeout=settings.crawler.timeout_seconds)
    if provider == "zhihu":
        return ZhihuGlobalSearchProvider(api_key=settings.search.zhihu_api_key, timeout=settings.crawler.timeout_seconds)
    if provider == "bocha":
        return BochaWebSearchProvider(api_key=settings.search.bocha_api_key, timeout=settings.crawler.timeout_seconds)
    raise ValueError(f"Unsupported search provider: {provider}")
