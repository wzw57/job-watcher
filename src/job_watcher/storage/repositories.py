from __future__ import annotations

import sqlite3
from typing import Any


class BaseRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn


class RawItemRepository(BaseRepository):
    def upsert_legacy_snapshot(self, row: sqlite3.Row) -> int:
        self.conn.execute(
            """INSERT INTO raw_items (
                source_id, title, url, canonical_url, content_html_path, raw_metadata_json,
                content_hash, crawl_status, parse_status, credibility, merge_status,
                discovered_at, last_seen_at, legacy_snapshot_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', 60, 'unprocessed', ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(legacy_snapshot_id) DO UPDATE SET
                source_id=excluded.source_id, title=excluded.title, url=excluded.url,
                canonical_url=excluded.canonical_url, content_html_path=excluded.content_html_path,
                content_hash=excluded.content_hash, crawl_status=excluded.crawl_status,
                last_seen_at=excluded.last_seen_at, updated_at=CURRENT_TIMESTAMP""",
            (row["source_id"], row["title"], row["url"], row["final_url"] or row["url"],
             row["raw_html_path"] or row["raw_text_path"],
             '{"legacy_table":"crawl_snapshots"}', row["content_hash"],
             "success" if not row["error"] else "failed", row["fetched_at"], row["fetched_at"], row["id"]),
        )
        return int(self.conn.execute("SELECT id FROM raw_items WHERE legacy_snapshot_id=?", (row["id"],)).fetchone()[0])


class JobEventRepository(BaseRepository):
    def upsert_legacy_lead(self, row: sqlite3.Row) -> int:
        title = row["title"] or f"旧招聘线索 #{row['id']}"
        self.conn.execute(
            """INSERT INTO job_events (
                entity_id, title, recruitment_type, cohorts_json, locations_json,
                application_url, source_confidence, match_score, status, notes,
                first_seen_at, legacy_lead_id, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending_review', ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(legacy_lead_id) DO UPDATE SET
                entity_id=excluded.entity_id, title=excluded.title,
                recruitment_type=excluded.recruitment_type, application_url=excluded.application_url,
                source_confidence=excluded.source_confidence, match_score=excluded.match_score,
                notes=excluded.notes, updated_at=CURRENT_TIMESTAMP""",
            (row["company_id"], title, row["recruitment_type"] or "unknown",
             f'["{row["target_year"]}"]' if row["target_year"] else "[]",
             f'["{row["location"]}"]' if row["location"] else "[]", row["url"],
             row["trust_score"], row["overall_score"], row["summary"], row["created_at"], row["id"]),
        )
        return int(self.conn.execute("SELECT id FROM job_events WHERE legacy_lead_id=?", (row["id"],)).fetchone()[0])


class JobPositionRepository(BaseRepository):
    def ensure_legacy_default(self, event_id: int, row: sqlite3.Row) -> int:
        self.conn.execute(
            """INSERT INTO job_positions (job_event_id, name, location, description, match_score, legacy_lead_id, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(legacy_lead_id) DO UPDATE SET job_event_id=excluded.job_event_id,
               name=excluded.name, location=excluded.location, description=excluded.description,
               match_score=excluded.match_score, updated_at=CURRENT_TIMESTAMP""",
            (event_id, row["title"] or "待拆分岗位", row["location"], row["summary"], row["overall_score"], row["id"]),
        )
        return int(self.conn.execute("SELECT id FROM job_positions WHERE legacy_lead_id=?", (row["id"],)).fetchone()[0])


class ReviewTaskRepository(BaseRepository):
    def ensure_legacy_review(self, row: sqlite3.Row, reason: str) -> int:
        title = f"旧线索 #{row['id']} 需要人工核验"
        existing = self.conn.execute(
            "SELECT id FROM review_tasks WHERE task_type='legacy_migration' AND title=?", (title,)
        ).fetchone()
        if existing:
            return int(existing[0])
        cur = self.conn.execute(
            """INSERT INTO review_tasks (task_type, company_id, source_id, title, description, suggested_action, priority)
               VALUES ('legacy_migration', ?, ?, ?, ?, '核验后决定是否创建招聘事件', 'B')""",
            (row["company_id"], row["source_id"], title, reason),
        )
        return int(cur.lastrowid)
