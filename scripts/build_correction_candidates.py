from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from job_watcher.search.scoring import score_candidate  # noqa: E402


DEFAULT_RESULTS_CSV = ROOT / "data" / "manual_search_results.csv"
OUTPUT_CSV = ROOT / "data" / "audit" / "correction_candidates.csv"


REQUIRED_COLUMNS = {
    "company_key",
    "company_name",
    "query",
    "provider",
    "rank",
    "title",
    "url",
    "snippet",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Score search results as source correction candidates.")
    parser.add_argument("--input", default=str(DEFAULT_RESULTS_CSV), help="Search result CSV to score.")
    parser.add_argument("--output", default=str(OUTPUT_CSV), help="Candidate output CSV.")
    parser.add_argument("--min-score", type=int, default=30)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    if not input_path.exists():
        example = ROOT / "data" / "manual_search_results.example.csv"
        raise SystemExit(
            f"Missing search results: {input_path}\n"
            f"Create it using the template: {example}"
        )

    df = pd.read_csv(input_path)
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise SystemExit(f"Missing required columns: {', '.join(sorted(missing))}")
    df = df.drop_duplicates(subset=["company_key", "url"]).copy()

    rows: list[dict[str, str | int]] = []
    for _, row in df.iterrows():
        title = "" if pd.isna(row["title"]) else str(row["title"])
        url = "" if pd.isna(row["url"]) else str(row["url"])
        snippet = "" if pd.isna(row["snippet"]) else str(row["snippet"])
        if not url:
            continue
        score = score_candidate(str(row["company_name"]), url, title, snippet)
        if score.score < args.min_score:
            continue
        rows.append(
            {
                "company_key": row["company_key"],
                "company_name": row["company_name"],
                "query": row["query"],
                "provider": row["provider"],
                "rank": row["rank"],
                "candidate_title": title,
                "candidate_url": url,
                "candidate_snippet": snippet,
                "candidate_source_type": score.source_type,
                "candidate_score": score.score,
                "candidate_confidence": score.confidence,
                "score_reasons": "；".join(score.reasons),
                "review_status": "pending",
                "decision": "",
                "review_notes": "",
            }
        )

    rows.sort(key=lambda item: (str(item["company_key"]), -int(item["candidate_score"]), int(item["rank"])))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        fieldnames = [
            "company_key",
            "company_name",
            "query",
            "provider",
            "rank",
            "candidate_title",
            "candidate_url",
            "candidate_snippet",
            "candidate_source_type",
            "candidate_score",
            "candidate_confidence",
            "score_reasons",
            "review_status",
            "decision",
            "review_notes",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"correction candidates: {len(rows)}")
    print(f"output: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
