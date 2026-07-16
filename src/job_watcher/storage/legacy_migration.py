from __future__ import annotations

import sqlite3

from job_watcher.storage.repositories import JobEventRepository, JobPositionRepository, RawItemRepository, ReviewTaskRepository
from job_watcher.storage.statuses import LEGACY_SKIPPED_LEAD_STATUSES


def migrate_legacy_data(conn: sqlite3.Connection) -> dict[str, int]:
    raw_repo = RawItemRepository(conn)
    event_repo = JobEventRepository(conn)
    position_repo = JobPositionRepository(conn)
    review_repo = ReviewTaskRepository(conn)
    counts = {"snapshots": 0, "events": 0, "positions": 0, "reviews": 0}

    for row in conn.execute("SELECT * FROM crawl_snapshots ORDER BY id"):
        raw_repo.upsert_legacy_snapshot(row)
        counts["snapshots"] += 1

    for row in conn.execute("SELECT * FROM job_leads ORDER BY id"):
        if row["status"] in LEGACY_SKIPPED_LEAD_STATUSES:
            review_repo.ensure_legacy_review(row, f"旧状态为 {row['status']}，未自动生成招聘事实")
            counts["reviews"] += 1
            continue
        event_id = event_repo.upsert_legacy_lead(row)
        position_repo.ensure_legacy_default(event_id, row)
        counts["events"] += 1
        counts["positions"] += 1
        if row["snapshot_id"]:
            conn.execute(
                "UPDATE raw_items SET job_event_id=?, merge_status='linked', updated_at=CURRENT_TIMESTAMP WHERE legacy_snapshot_id=?",
                (event_id, row["snapshot_id"]),
            )
    conn.commit()
    violations = list(conn.execute("PRAGMA foreign_key_check"))
    counts["foreign_key_violations"] = len(violations)
    if violations:
        raise RuntimeError(f"foreign key violations after legacy migration: {violations[:5]}")
    return counts
