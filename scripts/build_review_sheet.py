from __future__ import annotations

import csv
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
CANDIDATES_CSV = ROOT / "data" / "audit" / "correction_candidates.csv"
REVIEW_CSV = ROOT / "data" / "audit" / "source_review_sheet.csv"


def main() -> int:
    if not CANDIDATES_CSV.exists():
        raise SystemExit(f"Missing candidates: {CANDIDATES_CSV}")

    df = pd.read_csv(CANDIDATES_CSV)
    df = df.sort_values(["company_name", "candidate_score"], ascending=[True, False])
    df["suggested_decision"] = df["candidate_confidence"].map(
        {
            "high": "review",
            "medium": "review",
            "low": "skip_or_reference",
        }
    ).fillna("review")
    df["accepted_as"] = ""
    df["manual_note"] = ""

    columns = [
        "company_key",
        "company_name",
        "candidate_score",
        "candidate_confidence",
        "candidate_source_type",
        "candidate_title",
        "candidate_url",
        "score_reasons",
        "query",
        "provider",
        "suggested_decision",
        "accepted_as",
        "manual_note",
    ]
    REVIEW_CSV.parent.mkdir(parents=True, exist_ok=True)
    with REVIEW_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for _, row in df[columns].iterrows():
            writer.writerow(row.to_dict())

    print(f"review rows: {len(df)}")
    print(f"output: {REVIEW_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
