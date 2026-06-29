from __future__ import annotations

import sqlite3
from dataclasses import dataclass


VERIFIED_STATUSES = (
    "verified_official",
    "verified_recruitment",
    "verified_government",
    "verified_platform",
)


@dataclass(frozen=True)
class CoverageSummary:
    total_companies: int
    with_verified_source: int
    with_recruitment_source: int
    with_candidate_only: int
    without_sources: int
    with_needs_search: int
    with_needs_browser: int

    @property
    def verified_rate(self) -> float:
        if self.total_companies == 0:
            return 0.0
        return self.with_verified_source / self.total_companies

    @property
    def recruitment_rate(self) -> float:
        if self.total_companies == 0:
            return 0.0
        return self.with_recruitment_source / self.total_companies


def coverage_summary(conn: sqlite3.Connection, priorities: tuple[str, ...] = ("P0", "P1")) -> CoverageSummary:
    priority_sql, values = priority_filter(priorities)
    row = conn.execute(
        f"""
        WITH scoped AS (
            SELECT id FROM companies WHERE {priority_sql}
        ),
        source_flags AS (
            SELECT
                c.id AS company_id,
                MAX(CASE WHEN s.verification_status IN ({placeholders(VERIFIED_STATUSES)}) THEN 1 ELSE 0 END) AS has_verified,
                MAX(CASE WHEN s.verification_status = 'verified_recruitment' THEN 1 ELSE 0 END) AS has_recruitment,
                MAX(CASE WHEN s.verification_status = 'candidate' THEN 1 ELSE 0 END) AS has_candidate,
                MAX(CASE WHEN s.verification_status = 'needs_search' THEN 1 ELSE 0 END) AS has_needs_search,
                MAX(CASE WHEN s.verification_status = 'needs_browser' THEN 1 ELSE 0 END) AS has_needs_browser,
                COUNT(s.id) AS source_count
            FROM scoped c
            LEFT JOIN sources s ON s.company_id = c.id
            GROUP BY c.id
        )
        SELECT
            COUNT(*) AS total_companies,
            SUM(CASE WHEN has_verified = 1 THEN 1 ELSE 0 END) AS with_verified_source,
            SUM(CASE WHEN has_recruitment = 1 THEN 1 ELSE 0 END) AS with_recruitment_source,
            SUM(CASE WHEN has_verified = 0 AND has_candidate = 1 THEN 1 ELSE 0 END) AS with_candidate_only,
            SUM(CASE WHEN source_count = 0 THEN 1 ELSE 0 END) AS without_sources,
            SUM(CASE WHEN has_needs_search = 1 THEN 1 ELSE 0 END) AS with_needs_search,
            SUM(CASE WHEN has_needs_browser = 1 THEN 1 ELSE 0 END) AS with_needs_browser
        FROM source_flags
        """,
        [*values, *VERIFIED_STATUSES],
    ).fetchone()
    return CoverageSummary(
        total_companies=int(row["total_companies"] or 0),
        with_verified_source=int(row["with_verified_source"] or 0),
        with_recruitment_source=int(row["with_recruitment_source"] or 0),
        with_candidate_only=int(row["with_candidate_only"] or 0),
        without_sources=int(row["without_sources"] or 0),
        with_needs_search=int(row["with_needs_search"] or 0),
        with_needs_browser=int(row["with_needs_browser"] or 0),
    )


def coverage_by_priority(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute(
        f"""
        WITH source_flags AS (
            SELECT
                c.id AS company_id,
                c.priority,
                MAX(CASE WHEN s.verification_status IN ({placeholders(VERIFIED_STATUSES)}) THEN 1 ELSE 0 END) AS has_verified,
                MAX(CASE WHEN s.verification_status = 'verified_recruitment' THEN 1 ELSE 0 END) AS has_recruitment,
                COUNT(s.id) AS source_count
            FROM companies c
            LEFT JOIN sources s ON s.company_id = c.id
            GROUP BY c.id
        )
        SELECT
            priority,
            COUNT(*) AS total,
            SUM(CASE WHEN has_verified = 1 THEN 1 ELSE 0 END) AS verified,
            SUM(CASE WHEN has_recruitment = 1 THEN 1 ELSE 0 END) AS recruitment,
            SUM(CASE WHEN source_count = 0 THEN 1 ELSE 0 END) AS no_source
        FROM source_flags
        GROUP BY priority
        ORDER BY CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 ELSE 4 END
        """,
        VERIFIED_STATUSES,
    ).fetchall()


def companies_needing_sources(
    conn: sqlite3.Connection,
    priorities: tuple[str, ...] = ("P0", "P1"),
    limit: int = 100,
) -> list[sqlite3.Row]:
    priority_sql, values = priority_filter(priorities)
    return conn.execute(
        f"""
        WITH source_flags AS (
            SELECT
                c.id AS company_id,
                MAX(CASE WHEN s.verification_status IN ({placeholders(VERIFIED_STATUSES)}) THEN 1 ELSE 0 END) AS has_verified,
                MAX(CASE WHEN s.verification_status = 'verified_recruitment' THEN 1 ELSE 0 END) AS has_recruitment,
                COUNT(s.id) AS source_count
            FROM companies c
            LEFT JOIN sources s ON s.company_id = c.id
            WHERE {priority_sql}
            GROUP BY c.id
        )
        SELECT
            c.id,
            c.priority,
            c.group_name,
            c.company_name,
            c.region,
            c.recommended_directions,
            sf.source_count,
            sf.has_verified,
            sf.has_recruitment
        FROM source_flags sf
        JOIN companies c ON c.id = sf.company_id
        WHERE sf.has_verified = 0
        ORDER BY
            CASE c.priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END,
            sf.source_count ASC,
            c.company_name
        LIMIT ?
        """,
        [*VERIFIED_STATUSES, *values, limit],
    ).fetchall()


def placeholders(values: tuple[str, ...]) -> str:
    return ",".join("?" for _ in values)


def priority_filter(priorities: tuple[str, ...]) -> tuple[str, list[str]]:
    if not priorities:
        return "1 = 1", []
    return f"priority IN ({placeholders(priorities)})", list(priorities)
