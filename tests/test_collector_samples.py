from __future__ import annotations

from pathlib import Path

import pytest

from job_watcher.collectors.base import CollectionResult
from job_watcher.verification.collector_samples import load_collector_samples, validate_collector_samples


class FakeCollector:
    def collect(self, url: str) -> CollectionResult:
        status = "success" if url.endswith("/ok") else "blocked"
        return CollectionResult(
            status, url, url, 200 if status == "success" else 403,
            title="招聘", text="招聘正文" * 30 if status == "success" else "",
            metadata={"quality_score": 80} if status == "success" else {},
        )


def write_samples(path: Path, count: int = 20) -> None:
    rows = ["sample_key,name,url,category,expected_statuses,enabled,notes"]
    for index in range(count):
        suffix = "ok" if index % 2 == 0 else "blocked"
        expected = "success" if suffix == "ok" else "needs_browser"
        rows.append(f"s{index},样本{index},https://example.com/{suffix},test,{expected},true,")
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def test_sample_pool_requires_twenty_enabled_rows(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    write_samples(path, 19)
    with pytest.raises(ValueError, match="at least 20"):
        load_collector_samples(path)


def test_sample_validation_reports_unexpected_results(tmp_path: Path) -> None:
    path = tmp_path / "samples.csv"
    write_samples(path)
    report = validate_collector_samples(FakeCollector(), load_collector_samples(path), max_workers=3)
    assert report["selected"] == 20
    assert report["matched"] == 10
    assert report["unexpected"] == 10
    assert report["status_counts"] == {"blocked": 10, "success": 10}
    first = report["checks"][0]
    assert first["quality_score"] == 80 and first["matched_expectation"] is True
