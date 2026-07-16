from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

from job_watcher.collectors.base import CollectionResult
from job_watcher.config import PathConfig, load_settings
from job_watcher.crawler.runner import run_crawl_once
from job_watcher.storage.db import COLUMN_MIGRATIONS, SCHEMA_STATEMENTS, execute_column_migrations, execute_schema


class FakeCollector:
    def __init__(self, results: dict[str, CollectionResult]) -> None:
        self.results = results

    def collect(self, url: str) -> CollectionResult:
        return self.results[url]


def database() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    tables = tuple(s for s in SCHEMA_STATEMENTS if not s.lstrip().upper().startswith("CREATE INDEX"))
    indexes = tuple(s for s in SCHEMA_STATEMENTS if s.lstrip().upper().startswith("CREATE INDEX"))
    execute_schema(conn, tables); execute_column_migrations(conn, COLUMN_MIGRATIONS); execute_schema(conn, indexes)
    conn.execute("INSERT INTO companies(company_key,company_name,priority) VALUES ('c1','测试企业','P0')")
    company_id = conn.execute("SELECT id FROM companies").fetchone()[0]
    for key, url in (("ok","https://example.com/ok"),("blocked","https://example.com/blocked")):
        conn.execute("""INSERT INTO sources(company_id,source_key,name,url,verification_status,trust_level,enabled)
                        VALUES (?,?,?,?, 'verified_recruitment',80,1)""", (company_id,key,key,url))
    conn.commit()
    return conn


def settings(tmp_path: Path):
    base = load_settings()
    return replace(base, paths=PathConfig(tmp_path, tmp_path / "db.sqlite", tmp_path / "snapshots"))


def test_pipeline_writes_runs_raw_items_and_deduplicates(tmp_path: Path) -> None:
    conn = database()
    result = CollectionResult("success", "https://example.com/ok", "https://example.com/ok", 200,
                              "text/html", "2027校招", "2027届校园招聘 网络安全", "<html>2027届校园招聘 网络安全</html>", "hash-1")
    collector = FakeCollector({"https://example.com/ok": result,
                               "https://example.com/blocked": CollectionResult("blocked","https://example.com/blocked","https://example.com/blocked",403,error_type="http_403")})
    first = run_crawl_once(conn, settings(tmp_path), limit=2, collector=collector)
    second = run_crawl_once(conn, settings(tmp_path), limit=2, collector=collector)
    assert first.checked == second.checked == 2
    assert conn.execute("SELECT COUNT(*) FROM source_runs").fetchone()[0] == 4
    assert conn.execute("SELECT COUNT(*) FROM source_runs WHERE status='no_content_change'").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM raw_items").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM crawl_snapshots").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM job_leads").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM review_tasks WHERE task_type='collection_failure'").fetchone()[0] == 1
    blocked = conn.execute("SELECT health_status,consecutive_failures FROM sources WHERE source_key='blocked'").fetchone()
    assert blocked["health_status"] == "blocked" and blocked["consecutive_failures"] == 2
    assert list(conn.execute("PRAGMA foreign_key_check")) == []
