from __future__ import annotations

import sqlite3

from job_watcher.storage.db import COLUMN_MIGRATIONS, SCHEMA_STATEMENTS, execute_column_migrations, execute_schema
from job_watcher.storage.legacy_migration import migrate_legacy_data


def database() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    tables = tuple(s for s in SCHEMA_STATEMENTS if not s.lstrip().upper().startswith("CREATE INDEX"))
    indexes = tuple(s for s in SCHEMA_STATEMENTS if s.lstrip().upper().startswith("CREATE INDEX"))
    execute_schema(conn, tables)
    execute_column_migrations(conn, COLUMN_MIGRATIONS)
    execute_schema(conn, indexes)
    conn.execute("INSERT INTO companies(company_key,company_name) VALUES ('c1','测试企业')")
    conn.execute("INSERT INTO sources(source_key,url) VALUES ('s1','https://example.com')")
    company_id = conn.execute("SELECT id FROM companies").fetchone()[0]
    source_id = conn.execute("SELECT id FROM sources").fetchone()[0]
    conn.execute("INSERT INTO crawl_snapshots(source_id,url,title,content_hash,fetched_at) VALUES (?,?,?,?,?)", (source_id,'https://example.com/a','公告','h1','2026-01-01'))
    snapshot_id = conn.execute("SELECT id FROM crawl_snapshots").fetchone()[0]
    conn.execute("""INSERT INTO job_leads(company_id,source_id,snapshot_id,title,url,content_hash,target_year,recruitment_type,location,trust_score,overall_score,status,summary)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (company_id,source_id,snapshot_id,'2027校招','https://example.com/a','lead1','2027','campus','青岛',80,90,'new','摘要'))
    conn.execute("""INSERT INTO job_leads(company_id,source_id,title,url,content_hash,status)
                    VALUES (?,?,?,?,?,?)""", (company_id,source_id,'无效线索','https://example.com/b','lead2','invalid'))
    conn.commit()
    return conn


def test_legacy_migration_is_traceable_and_idempotent() -> None:
    conn = database()
    first = migrate_legacy_data(conn)
    second = migrate_legacy_data(conn)
    assert first["foreign_key_violations"] == second["foreign_key_violations"] == 0
    assert conn.execute("SELECT COUNT(*) FROM crawl_snapshots").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM job_leads").fetchone()[0] == 2
    assert conn.execute("SELECT COUNT(*) FROM raw_items").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM job_events").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM job_positions").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM review_tasks WHERE task_type='legacy_migration'").fetchone()[0] == 1
    linked = conn.execute("SELECT legacy_snapshot_id,job_event_id,merge_status FROM raw_items").fetchone()
    assert linked["legacy_snapshot_id"] == 1 and linked["job_event_id"] is not None and linked["merge_status"] == "linked"
    event = conn.execute("SELECT legacy_lead_id FROM job_events").fetchone()
    position = conn.execute("SELECT legacy_lead_id FROM job_positions").fetchone()
    assert event[0] == position[0] == 1
