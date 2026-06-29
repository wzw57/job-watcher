from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Iterable

from job_watcher.config import Settings


SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_key TEXT NOT NULL UNIQUE,
        source_row INTEGER,
        original_group_name TEXT,
        group_name TEXT,
        original_company_name TEXT,
        company_name TEXT NOT NULL,
        normalized_name TEXT,
        aliases TEXT,
        entity_type TEXT,
        region TEXT,
        priority_raw TEXT,
        priority TEXT,
        difficulty TEXT,
        education_barrier TEXT,
        recommended_directions TEXT,
        action_status TEXT,
        ownership_type TEXT DEFAULT 'unknown',
        verification_status TEXT NOT NULL DEFAULT 'candidate',
        enabled INTEGER NOT NULL DEFAULT 1,
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER REFERENCES companies(id),
        source_key TEXT NOT NULL UNIQUE,
        name TEXT,
        url TEXT NOT NULL,
        original_url TEXT,
        source_type TEXT NOT NULL DEFAULT 'unknown',
        provider TEXT,
        trust_level INTEGER NOT NULL DEFAULT 50,
        verification_status TEXT NOT NULL DEFAULT 'candidate',
        requires_browser INTEGER NOT NULL DEFAULT 0,
        enabled INTEGER NOT NULL DEFAULT 1,
        parent_source_id INTEGER REFERENCES sources(id),
        discovered_by TEXT NOT NULL DEFAULT 'import',
        discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_verified_at TEXT,
        last_checked_at TEXT,
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_verifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id INTEGER REFERENCES sources(id),
        url TEXT NOT NULL,
        http_status TEXT,
        final_url TEXT,
        content_type TEXT,
        page_title TEXT,
        verification_status TEXT NOT NULL,
        error TEXT,
        verified_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS search_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER REFERENCES companies(id),
        source_id INTEGER REFERENCES sources(id),
        query TEXT NOT NULL,
        provider TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        reason TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        executed_at TEXT,
        error TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS search_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_id INTEGER REFERENCES search_tasks(id),
        company_id INTEGER REFERENCES companies(id),
        provider TEXT NOT NULL,
        rank INTEGER,
        title TEXT,
        url TEXT NOT NULL,
        snippet TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(company_id, provider, url)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS correction_candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER REFERENCES companies(id),
        source_id INTEGER REFERENCES sources(id),
        search_result_id INTEGER REFERENCES search_results(id),
        candidate_url TEXT NOT NULL,
        candidate_title TEXT,
        candidate_snippet TEXT,
        candidate_source_type TEXT,
        score INTEGER NOT NULL DEFAULT 0,
        confidence TEXT,
        score_reasons TEXT,
        review_status TEXT NOT NULL DEFAULT 'pending',
        decision TEXT,
        review_notes TEXT,
        reviewed_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(company_id, candidate_url)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS crawl_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id INTEGER REFERENCES sources(id),
        url TEXT NOT NULL,
        status_code INTEGER,
        final_url TEXT,
        title TEXT,
        raw_html_path TEXT,
        raw_text_path TEXT,
        content_hash TEXT,
        fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        error TEXT,
        UNIQUE(source_id, content_hash)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_leads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_id INTEGER REFERENCES companies(id),
        source_id INTEGER REFERENCES sources(id),
        snapshot_id INTEGER REFERENCES crawl_snapshots(id),
        title TEXT,
        url TEXT NOT NULL,
        source_type TEXT,
        content_hash TEXT,
        target_year TEXT,
        recruitment_type TEXT,
        location TEXT,
        matched_keywords TEXT,
        computer_relevance_score INTEGER NOT NULL DEFAULT 0,
        security_relevance_score INTEGER NOT NULL DEFAULT 0,
        trust_score INTEGER NOT NULL DEFAULT 0,
        overall_score INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'new',
        summary TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(source_id, content_hash)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_companies_priority ON companies(priority)",
    "CREATE INDEX IF NOT EXISTS idx_companies_status ON companies(verification_status)",
    "CREATE INDEX IF NOT EXISTS idx_sources_company ON sources(company_id)",
    "CREATE INDEX IF NOT EXISTS idx_sources_status ON sources(verification_status)",
    "CREATE INDEX IF NOT EXISTS idx_candidates_status ON correction_candidates(review_status)",
    "CREATE INDEX IF NOT EXISTS idx_snapshots_source ON crawl_snapshots(source_id)",
    "CREATE INDEX IF NOT EXISTS idx_leads_status ON job_leads(status)",
    "CREATE INDEX IF NOT EXISTS idx_leads_company ON job_leads(company_id)",
)


def connect(settings: Settings) -> sqlite3.Connection:
    db_path = settings.paths.database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(settings: Settings) -> None:
    with connect(settings) as conn:
        execute_schema(conn, SCHEMA_STATEMENTS)


def execute_schema(conn: sqlite3.Connection, statements: Iterable[str]) -> None:
    for statement in statements:
        conn.execute(statement)
    conn.commit()
