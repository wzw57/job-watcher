from __future__ import annotations

import argparse
import csv
from pathlib import Path
from urllib.parse import quote_plus

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
QUEUE_CSV = ROOT / "data" / "audit" / "source_correction_queue.csv"
TASKS_CSV = ROOT / "data" / "audit" / "search_tasks.csv"


def search_url(provider: str, query: str) -> str:
    encoded = quote_plus(query)
    if provider == "bing":
        return f"https://www.bing.com/search?q={encoded}"
    if provider == "zhihu":
        return f"https://www.zhihu.com/search?type=content&q={encoded}"
    if provider == "baidu":
        return f"https://www.baidu.com/s?wd={encoded}"
    if provider == "bocha":
        return f"https://open.bochaai.com/"
    return ""


def pick_queries(row: pd.Series, max_queries: int) -> list[str]:
    queries: list[str] = []
    for i in range(1, 10):
        key = f"query_{i}"
        if key not in row:
            continue
        value = str(row[key]).strip()
        if value and value != "nan" and value not in queries:
            queries.append(value)
        if len(queries) >= max_queries:
            break
    return queries


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build search tasks from source correction queue.")
    parser.add_argument("--max-companies", type=int, default=50, help="Maximum correction rows to convert.")
    parser.add_argument("--queries-per-company", type=int, default=4)
    parser.add_argument("--providers", nargs="*", default=["zhihu", "bocha", "baidu"])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not QUEUE_CSV.exists():
        raise SystemExit(f"Missing correction queue: {QUEUE_CSV}")

    queue = pd.read_csv(QUEUE_CSV).head(args.max_companies)
    rows: list[dict[str, str]] = []
    task_id = 1
    for _, item in queue.iterrows():
        queries = pick_queries(item, args.queries_per_company)
        for query_index, query in enumerate(queries, start=1):
            for provider in args.providers:
                rows.append(
                    {
                        "task_id": task_id,
                        "company_key": item["company_key"],
                        "company_name": item["company_name"],
                        "priority": item["priority"],
                        "original_url": item["original_url"],
                        "recommended_action": item["recommended_action"],
                        "reason": item["reason"],
                        "query_index": query_index,
                        "query": query,
                        "provider": provider,
                        "search_url": search_url(provider, query),
                        "status": "pending",
                    }
                )
                task_id += 1

    TASKS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with TASKS_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"search tasks: {len(rows)}")
    print(f"output: {TASKS_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
