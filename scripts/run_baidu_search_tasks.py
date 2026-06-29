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

from job_watcher.search.baidu_provider import BaiduWebSearchProvider  # noqa: E402


TASKS_CSV = ROOT / "data" / "audit" / "search_tasks.csv"
RESULTS_CSV = ROOT / "data" / "manual_search_results.csv"
FIELDNAMES = ["task_id", "company_key", "company_name", "query", "provider", "rank", "title", "url", "snippet"]


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
    parser = argparse.ArgumentParser(description="Run Baidu web search tasks.")
    parser.add_argument("--query", default="")
    parser.add_argument("--max-tasks", type=int, default=20)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--sleep", type=float, default=0.5)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    provider = BaiduWebSearchProvider(timeout=args.timeout)
    if args.query:
        for rank, result in enumerate(provider.search(args.query, count=args.count), start=1):
            print(f"{rank}. {result.title}\n   {result.url}\n   {result.snippet[:180]}")
        return 0

    if not TASKS_CSV.exists():
        raise SystemExit(f"Missing search tasks: {TASKS_CSV}")
    tasks = pd.read_csv(TASKS_CSV)
    tasks = tasks[tasks["provider"] == "baidu"].head(args.max_tasks)
    total = 0
    for _, task in tasks.iterrows():
        query = str(task["query"])
        print(f"task={task['task_id']} query={query}")
        results = provider.search(query, count=args.count)
        rows = [
            {
                "task_id": str(task["task_id"]),
                "company_key": str(task["company_key"]),
                "company_name": str(task["company_name"]),
                "query": query,
                "provider": "baidu",
                "rank": str(rank),
                "title": result.title,
                "url": result.url,
                "snippet": result.snippet,
            }
            for rank, result in enumerate(results, start=1)
        ]
        append_rows(RESULTS_CSV, rows)
        total += len(rows)
        time.sleep(args.sleep)
    print(f"appended rows: {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
