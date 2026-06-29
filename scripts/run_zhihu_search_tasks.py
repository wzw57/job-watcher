from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_watcher.search.zhihu_provider import ZhihuGlobalSearchProvider  # noqa: E402


TASKS_CSV = ROOT / "data" / "audit" / "search_tasks.csv"
RESULTS_CSV = ROOT / "data" / "manual_search_results.csv"


FIELDNAMES = [
    "task_id",
    "company_key",
    "company_name",
    "query",
    "provider",
    "rank",
    "title",
    "url",
    "snippet",
]


def existing_task_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        df = pd.read_csv(path, usecols=["task_id", "provider"])
    except Exception:
        return set()
    zhihu = df[df["provider"] == "zhihu"]
    return set(zhihu["task_id"].dropna().astype(str))


def append_rows(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    exists = path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Zhihu global_search tasks.")
    parser.add_argument("--query", default="", help="Run one ad-hoc query instead of reading task CSV.")
    parser.add_argument("--max-tasks", type=int, default=20)
    parser.add_argument("--count", type=int, default=5, help="Results per query, max 20.")
    parser.add_argument("--search-db", default="all", choices=["all", "realtime", "static"])
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--sleep", type=float, default=0.5, help="Seconds between API calls.")
    parser.add_argument("--resume", action="store_true", help="Skip tasks already in result CSV.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    provider = ZhihuGlobalSearchProvider(timeout=args.timeout)
    if args.query:
        results = provider.search(query=args.query, count=args.count, search_db=args.search_db)
        for rank, result in enumerate(results, start=1):
            print(f"{rank}. {result.title}\n   {result.url}\n   {result.snippet[:160]}")
        return 0

    if not TASKS_CSV.exists():
        raise SystemExit(f"Missing search tasks: {TASKS_CSV}")

    tasks = pd.read_csv(TASKS_CSV)
    tasks = tasks[tasks["provider"] == "zhihu"].copy()
    if args.resume:
        done = existing_task_ids(RESULTS_CSV)
        tasks = tasks[~tasks["task_id"].astype(str).isin(done)]
    tasks = tasks.head(args.max_tasks)

    total_rows = 0
    for index, task in tasks.iterrows():
        task_id = str(task["task_id"])
        query = str(task["query"])
        print(f"[{total_rows + 1}] task={task_id} query={query}")
        results = []
        last_error: Exception | None = None
        for attempt in range(1, args.retries + 2):
            try:
                results = provider.search(query=query, count=args.count, search_db=args.search_db)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                print(f"  attempt {attempt} error: {type(exc).__name__}: {exc}", file=sys.stderr)
                time.sleep(args.sleep * attempt)
        if last_error is not None:
            continue

        rows: list[dict[str, str]] = []
        for rank, result in enumerate(results, start=1):
            rows.append(
                {
                    "task_id": task_id,
                    "company_key": str(task["company_key"]),
                    "company_name": str(task["company_name"]),
                    "query": query,
                    "provider": "zhihu",
                    "rank": str(rank),
                    "title": result.title,
                    "url": result.url,
                    "snippet": result.snippet,
                }
            )
        append_rows(RESULTS_CSV, rows)
        total_rows += len(rows)
        print(f"  results: {len(rows)}")
        time.sleep(args.sleep)

    print(f"appended rows: {total_rows}")
    print(f"results: {RESULTS_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
