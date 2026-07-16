from __future__ import annotations

import csv
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from job_watcher.collectors.base import CollectionResult, Collector


@dataclass(frozen=True)
class CollectorSample:
    sample_key: str
    name: str
    url: str
    category: str
    expected_statuses: tuple[str, ...]
    notes: str = ""


@dataclass(frozen=True)
class SampleCheck:
    sample_key: str
    name: str
    url: str
    category: str
    expected_statuses: tuple[str, ...]
    status: str
    matched_expectation: bool
    http_status: int | None
    final_url: str
    title: str
    text_chars: int
    quality_score: int | None
    error_type: str
    error_message: str


def load_collector_samples(path: Path) -> list[CollectorSample]:
    if not path.exists():
        raise FileNotFoundError(f"collector sample file not found: {path}")
    samples: list[CollectorSample] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for line_number, row in enumerate(csv.DictReader(handle), start=2):
            if not _truthy(row.get("enabled", "true")):
                continue
            key = (row.get("sample_key") or "").strip()
            url = (row.get("url") or "").strip()
            statuses = tuple(s.strip() for s in (row.get("expected_statuses") or "").split("|") if s.strip())
            if not key or not url or not statuses:
                raise ValueError(f"invalid collector sample at line {line_number}: key, url, and expected_statuses are required")
            if key in seen:
                raise ValueError(f"duplicate collector sample_key: {key}")
            if not url.startswith(("https://", "http://")):
                raise ValueError(f"collector sample URL must be HTTP(S): {url}")
            seen.add(key)
            samples.append(CollectorSample(
                sample_key=key,
                name=(row.get("name") or key).strip(),
                url=url,
                category=(row.get("category") or "other").strip(),
                expected_statuses=statuses,
                notes=(row.get("notes") or "").strip(),
            ))
    if len(samples) < 20:
        raise ValueError(f"collector acceptance pool must contain at least 20 enabled samples; found {len(samples)}")
    return samples


def validate_collector_samples(
    collector: Collector,
    samples: list[CollectorSample],
    *,
    limit: int = 0,
    category: str = "",
    max_workers: int = 1,
) -> dict[str, object]:
    selected = [sample for sample in samples if not category or sample.category == category]
    if limit > 0:
        selected = selected[:limit]

    def check(sample: CollectorSample) -> SampleCheck:
        try:
            result = collector.collect(sample.url)
        except Exception as exc:  # acceptance runs must report every sample.
            result = CollectionResult(
                "internal_error", sample.url, sample.url,
                error_type=type(exc).__name__, error_message=str(exc)[:500],
            )
        raw_quality = result.metadata.get("quality_score")
        quality_score = int(raw_quality) if isinstance(raw_quality, (int, float)) else None
        return SampleCheck(
            sample_key=sample.sample_key,
            name=sample.name,
            url=sample.url,
            category=sample.category,
            expected_statuses=sample.expected_statuses,
            status=result.status,
            matched_expectation=result.status in sample.expected_statuses,
            http_status=result.http_status,
            final_url=result.final_url,
            title=result.title,
            text_chars=len(result.text),
            quality_score=quality_score,
            error_type=result.error_type,
            error_message=result.error_message,
        )

    if max_workers > 1 and len(selected) > 1:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            checks = list(executor.map(check, selected))
    else:
        checks = [check(sample) for sample in selected]
    matched = sum(check.matched_expectation for check in checks)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "selected": len(checks),
        "matched": matched,
        "unexpected": len(checks) - matched,
        "status_counts": _counts(check.status for check in checks),
        "category_counts": _counts(check.category for check in checks),
        "checks": [asdict(check) for check in checks],
    }


def write_validation_report(report: dict[str, object], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _truthy(value: str) -> bool:
    return value.strip().lower() not in {"0", "false", "no", "off"}
