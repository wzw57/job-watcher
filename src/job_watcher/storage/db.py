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
    CREATE TABLE IF NOT EXISTS search_sources (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        url TEXT NOT NULL,
        tier TEXT,
        source_kind TEXT,
        scope TEXT,
        access_method TEXT,
        frequency TEXT,
        trust_level INTEGER NOT NULL DEFAULT 60,
        site_query_host TEXT,
        enabled INTEGER NOT NULL DEFAULT 1,
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    """
    CREATE TABLE IF NOT EXISTS discovered_companies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company_name TEXT NOT NULL,
        matched_location TEXT,
        matched_ownership TEXT,
        matched_direction TEXT,
        first_result_id INTEGER REFERENCES search_results(id),
        evidence_url TEXT,
        evidence_title TEXT,
        evidence_snippet TEXT,
        score INTEGER NOT NULL DEFAULT 0,
        review_status TEXT NOT NULL DEFAULT 'pending',
        decision TEXT,
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(company_name, evidence_url)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS raw_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id INTEGER REFERENCES sources(id),
        search_task_id INTEGER REFERENCES search_tasks(id),
        entity_hint TEXT,
        title TEXT,
        url TEXT NOT NULL,
        canonical_url TEXT,
        published_at_raw TEXT,
        published_at TEXT,
        discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        content_text TEXT,
        content_html_path TEXT,
        attachments_json TEXT,
        content_hash TEXT,
        url_hash TEXT,
        crawl_status TEXT NOT NULL DEFAULT 'pending',
        parse_status TEXT NOT NULL DEFAULT 'pending',
        credibility INTEGER NOT NULL DEFAULT 50,
        job_event_id INTEGER REFERENCES job_events(id),
        merge_status TEXT NOT NULL DEFAULT 'unprocessed',
        raw_metadata_json TEXT,
        legacy_snapshot_id INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(source_id, canonical_url)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id INTEGER REFERENCES companies(id),
        publisher_entity_id INTEGER REFERENCES companies(id),
        employer_entity_id INTEGER REFERENCES companies(id),
        contract_entity_id INTEGER REFERENCES companies(id),
        title TEXT NOT NULL,
        recruitment_type TEXT NOT NULL DEFAULT 'unknown',
        cohorts_json TEXT,
        locations_json TEXT,
        qingdao_level TEXT NOT NULL DEFAULT 'pending',
        degree_requirements_json TEXT,
        major_requirements_json TEXT,
        political_requirement TEXT,
        headcount INTEGER,
        published_at TEXT,
        deadline_at TEXT,
        application_url TEXT,
        employment_type TEXT NOT NULL DEFAULT 'unknown',
        source_confidence INTEGER NOT NULL DEFAULT 0,
        match_score INTEGER NOT NULL DEFAULT 0,
        match_level TEXT NOT NULL DEFAULT 'pending',
        match_reasons_json TEXT,
        status TEXT NOT NULL DEFAULT 'pending_review',
        first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_verified_at TEXT,
        manual_tags_json TEXT,
        notes TEXT,
        legacy_lead_id INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS job_positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_event_id INTEGER NOT NULL REFERENCES job_events(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        category TEXT,
        location TEXT,
        department TEXT,
        headcount INTEGER,
        degree TEXT,
        majors_json TEXT,
        description TEXT,
        requirements TEXT,
        match_score INTEGER NOT NULL DEFAULT 0,
        match_reasons_json TEXT,
        legacy_lead_id INTEGER,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS applications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_event_id INTEGER NOT NULL REFERENCES job_events(id) ON DELETE CASCADE,
        position_id INTEGER REFERENCES job_positions(id) ON DELETE SET NULL,
        company_id INTEGER REFERENCES companies(id),
        status TEXT NOT NULL DEFAULT 'undecided',
        priority TEXT NOT NULL DEFAULT 'B',
        resume_version TEXT,
        applied_at TEXT,
        channel TEXT,
        account_hint TEXT,
        next_action TEXT,
        next_action_at TEXT,
        written_test_at TEXT,
        interview_at TEXT,
        result TEXT,
        notes TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(job_event_id, position_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS review_tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        task_type TEXT NOT NULL,
        company_id INTEGER REFERENCES companies(id),
        source_id INTEGER REFERENCES sources(id),
        raw_item_id INTEGER REFERENCES raw_items(id),
        job_event_id INTEGER REFERENCES job_events(id),
        title TEXT NOT NULL,
        description TEXT,
        suggested_action TEXT,
        priority TEXT NOT NULL DEFAULT 'B',
        status TEXT NOT NULL DEFAULT 'pending',
        resolution TEXT,
        due_at TEXT,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        resolved_at TEXT,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS source_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
        started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        finished_at TEXT,
        status TEXT NOT NULL DEFAULT 'running',
        http_status INTEGER,
        items_seen INTEGER NOT NULL DEFAULT 0,
        items_new INTEGER NOT NULL DEFAULT 0,
        duration_ms INTEGER,
        error_type TEXT,
        error_message TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS change_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_event_id INTEGER REFERENCES job_events(id) ON DELETE CASCADE,
        raw_item_id INTEGER REFERENCES raw_items(id) ON DELETE CASCADE,
        field_name TEXT NOT NULL,
        old_value TEXT,
        new_value TEXT,
        detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        acknowledged_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS daily_briefs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        brief_date TEXT NOT NULL UNIQUE,
        summary TEXT,
        content_json TEXT NOT NULL,
        generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    "CREATE INDEX IF NOT EXISTS idx_search_tasks_status ON search_tasks(status)",
    "CREATE INDEX IF NOT EXISTS idx_search_sources_tier ON search_sources(tier)",
    "CREATE INDEX IF NOT EXISTS idx_discovered_companies_status ON discovered_companies(review_status)",
    "CREATE INDEX IF NOT EXISTS idx_raw_items_merge_status ON raw_items(merge_status)",
    "CREATE INDEX IF NOT EXISTS idx_raw_items_url_hash ON raw_items(url_hash)",
    "CREATE INDEX IF NOT EXISTS idx_job_events_entity ON job_events(entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_job_events_status ON job_events(status)",
    "CREATE INDEX IF NOT EXISTS idx_job_events_deadline ON job_events(deadline_at)",
    "CREATE INDEX IF NOT EXISTS idx_job_positions_event ON job_positions(job_event_id)",
    "CREATE INDEX IF NOT EXISTS idx_applications_status ON applications(status)",
    "CREATE INDEX IF NOT EXISTS idx_review_tasks_status ON review_tasks(status, priority)",
    "CREATE INDEX IF NOT EXISTS idx_source_runs_source ON source_runs(source_id, started_at)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_raw_items_legacy_snapshot ON raw_items(legacy_snapshot_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_job_events_legacy_lead ON job_events(legacy_lead_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_job_positions_legacy_lead ON job_positions(legacy_lead_id)",
)


COLUMN_MIGRATIONS: dict[str, tuple[str, ...]] = {
    "companies": (
        "parent_id INTEGER REFERENCES companies(id)",
        "root_group_id INTEGER REFERENCES companies(id)",
        "short_name TEXT",
        "industry TEXT",
        "district TEXT",
        "qingdao_relation TEXT NOT NULL DEFAULT 'pending'",
        "credit_code TEXT",
        "official_domain TEXT",
        "monitor_status TEXT NOT NULL DEFAULT 'uncovered'",
        "job_value INTEGER NOT NULL DEFAULT 0",
        "tech_friendliness INTEGER NOT NULL DEFAULT 0",
        "evidence_level TEXT NOT NULL DEFAULT 'unverified'",
        "evidence_url TEXT",
    ),
    "sources": (
        "source_level TEXT NOT NULL DEFAULT 'unknown'",
        "domain TEXT",
        "account_name TEXT",
        "account_id TEXT",
        "auth_subject TEXT",
        "monitor_method TEXT NOT NULL DEFAULT 'http'",
        "content_type TEXT NOT NULL DEFAULT 'unknown'",
        "schedule TEXT",
        "active_season_json TEXT",
        "health_status TEXT NOT NULL DEFAULT 'unknown'",
        "last_success_at TEXT",
        "last_content_at TEXT",
        "consecutive_failures INTEGER NOT NULL DEFAULT 0",
        "parser_name TEXT",
    ),
    "search_tasks": (
        "task_type TEXT NOT NULL DEFAULT 'job_discovery'",
        "query_template TEXT",
        "site_filter TEXT",
        "priority TEXT NOT NULL DEFAULT 'B'",
        "schedule TEXT",
        "time_range_days INTEGER",
        "next_run_at TEXT",
        "last_result_count INTEGER NOT NULL DEFAULT 0",
        "new_result_count INTEGER NOT NULL DEFAULT 0",
        "failure_count INTEGER NOT NULL DEFAULT 0",
        "enabled INTEGER NOT NULL DEFAULT 1",
    ),
    "raw_items": (
        "legacy_snapshot_id INTEGER",
    ),
    "job_events": (
        "legacy_lead_id INTEGER",
    ),
    "job_positions": (
        "legacy_lead_id INTEGER",
    ),
}


def connect(settings: Settings) -> sqlite3.Connection:
    db_path = settings.paths.database_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(settings: Settings) -> None:
    with connect(settings) as conn:
        table_statements = tuple(s for s in SCHEMA_STATEMENTS if not s.lstrip().upper().startswith("CREATE INDEX"))
        index_statements = tuple(s for s in SCHEMA_STATEMENTS if s.lstrip().upper().startswith("CREATE INDEX"))
        execute_schema(conn, table_statements)
        execute_column_migrations(conn, COLUMN_MIGRATIONS)
        execute_schema(conn, index_statements)


def execute_schema(conn: sqlite3.Connection, statements: Iterable[str]) -> None:
    for statement in statements:
        conn.execute(statement)
    conn.commit()


def execute_column_migrations(conn: sqlite3.Connection, migrations: dict[str, tuple[str, ...]]) -> None:
    """Add compatible columns to databases created by pre-V1 versions.

    SQLite has no portable ``ADD COLUMN IF NOT EXISTS``. Inspecting table
    metadata keeps startup migrations idempotent while preserving all existing
    company, source, search and lead records.
    """
    for table, definitions in migrations.items():
        table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
        ).fetchone()
        if table_exists is None:
            continue
        existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
        for definition in definitions:
            column_name = definition.split(maxsplit=1)[0]
            if column_name not in existing:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {definition}")
                existing.add(column_name)
    conn.commit()
