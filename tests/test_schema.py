from __future__ import annotations

import sqlite3

from job_watcher.storage.db import COLUMN_MIGRATIONS, SCHEMA_STATEMENTS, execute_column_migrations, execute_schema


def table_names(conn: sqlite3.Connection) -> set[str]:
    return {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def test_schema_initialization_is_idempotent() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")

    execute_schema(conn, SCHEMA_STATEMENTS)
    execute_column_migrations(conn, COLUMN_MIGRATIONS)
    execute_schema(conn, SCHEMA_STATEMENTS)
    execute_column_migrations(conn, COLUMN_MIGRATIONS)

    assert {
        "companies",
        "sources",
        "raw_items",
        "job_events",
        "job_positions",
        "applications",
        "review_tasks",
        "source_runs",
        "change_events",
        "daily_briefs",
    } <= table_names(conn)
    assert {"parent_id", "root_group_id", "monitor_status", "qingdao_relation"} <= column_names(conn, "companies")
    assert {"health_status", "monitor_method", "last_success_at"} <= column_names(conn, "sources")


def test_old_database_gets_non_destructive_columns() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE companies (id INTEGER PRIMARY KEY, company_name TEXT NOT NULL)")
    conn.execute("CREATE TABLE sources (id INTEGER PRIMARY KEY, url TEXT NOT NULL)")
    conn.execute("CREATE TABLE search_tasks (id INTEGER PRIMARY KEY, query TEXT NOT NULL)")
    conn.execute("INSERT INTO companies(company_name) VALUES ('测试企业')")

    execute_column_migrations(conn, COLUMN_MIGRATIONS)

    assert conn.execute("SELECT company_name FROM companies").fetchone()[0] == "测试企业"
    assert "monitor_status" in column_names(conn, "companies")
    assert "health_status" in column_names(conn, "sources")
    assert "task_type" in column_names(conn, "search_tasks")


def test_column_migrations_skip_missing_tables() -> None:
    conn = sqlite3.connect(":memory:")
    execute_column_migrations(conn, COLUMN_MIGRATIONS)
    assert table_names(conn) == set()
