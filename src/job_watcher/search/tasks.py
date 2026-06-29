from __future__ import annotations

import csv
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from job_watcher.config import Settings


SEARCH_SOURCE_CSV = Path("config/search_sources.csv")

PROVIDERS = ("baidu", "zhihu")

GLOBAL_LOCATION_QUERIES = [
    "青岛 国企 2027届 校园招聘",
    "青岛 央企 2027届 秋招",
    "山东 青岛 国企 2027届 校招",
    "青岛 网络安全 2027届 校园招聘",
    "青岛 信息安全 2027届 校招",
    "青岛 数据安全 央企 2027届",
    "青岛 国资 国企 2027届 招聘",
    "黄岛 西海岸 国企 2027届 校招",
    "崂山 信息安全 2027届 校园招聘",
]

NATIONAL_SOE_QUERIES = [
    "央企 2027届 校园招聘 青岛",
    "国企 2027届 校招 青岛",
    "中央企业 2027届 青岛 招聘",
    "央企 山东 青岛 2027届 信息技术 校招",
    "央企 山东 青岛 2027届 网络安全",
    "国资央企 青岛 2027届 校园招聘",
]

ROLE_LOCATION_QUERIES = [
    "网络安全 信息安全 青岛 2027届 校园招聘",
    "安全运营 SOC 青岛 2027届 校招",
    "等保测评 青岛 2027届 招聘",
    "数据安全 青岛 2027届 校园招聘",
    "信息技术 青岛 国企 2027届",
    "数字化 青岛 央企 2027届 校招",
]


@dataclass(frozen=True)
class GenerateSearchTasksResult:
    search_sources_imported: int
    tasks_inserted: int
    known_company_tasks: int
    broad_discovery_tasks: int
    site_tasks: int


def import_search_sources(conn: sqlite3.Connection, settings: Settings) -> int:
    path = settings.root_dir / SEARCH_SOURCE_CSV
    if not path.exists():
        raise FileNotFoundError(path)
    count = 0
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            conn.execute(
                """
                INSERT INTO search_sources (
                    name, url, tier, source_kind, scope, access_method, frequency,
                    trust_level, site_query_host, enabled, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    url = excluded.url,
                    tier = excluded.tier,
                    source_kind = excluded.source_kind,
                    scope = excluded.scope,
                    access_method = excluded.access_method,
                    frequency = excluded.frequency,
                    trust_level = excluded.trust_level,
                    site_query_host = excluded.site_query_host,
                    enabled = excluded.enabled,
                    notes = excluded.notes,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    row["name"],
                    row["url"],
                    row["tier"],
                    row["source_kind"],
                    row["scope"],
                    row["access_method"],
                    row["frequency"],
                    int(row["trust_level"] or 60),
                    row["site_query_host"],
                    row["notes"],
                ),
            )
            count += 1
    conn.commit()
    return count


def generate_search_tasks(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    providers: tuple[str, ...] = PROVIDERS,
    priority_scope: tuple[str, ...] = ("P0", "P1"),
    max_companies: int = 80,
) -> GenerateSearchTasksResult:
    sources_count = import_search_sources(conn, settings)
    known = generate_known_company_tasks(conn, providers, priority_scope, max_companies)
    broad = generate_broad_discovery_tasks(conn, providers)
    site = generate_site_search_tasks(conn, providers)
    conn.commit()
    return GenerateSearchTasksResult(
        search_sources_imported=sources_count,
        tasks_inserted=known + broad + site,
        known_company_tasks=known,
        broad_discovery_tasks=broad,
        site_tasks=site,
    )


def generate_known_company_tasks(
    conn: sqlite3.Connection,
    providers: tuple[str, ...],
    priority_scope: tuple[str, ...],
    max_companies: int,
) -> int:
    placeholders = ",".join("?" for _ in priority_scope)
    rows = conn.execute(
        f"""
        SELECT id, company_name, group_name, priority
        FROM companies
        WHERE enabled = 1
          AND priority IN ({placeholders})
        ORDER BY CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END, id
        LIMIT ?
        """,
        [*priority_scope, max_companies],
    ).fetchall()
    inserted = 0
    for row in rows:
        for query in known_company_queries(row["company_name"], row["group_name"] or ""):
            inserted += insert_task_once(
                conn,
                company_id=int(row["id"]),
                provider_tuple=providers,
                query=query,
                reason="known_company_2027",
            )
    return inserted


def known_company_queries(company_name: str, group_name: str) -> list[str]:
    base = [
        f"{company_name} 2027届 校园招聘",
        f"{company_name} 2027届 秋招",
        f"{company_name} 2027届 提前批",
        f"{company_name} 2027届 网申",
        f"{company_name} 网络安全 2027届 校招",
    ]
    if group_name and group_name != company_name:
        base.extend(
            [
                f"{group_name} 青岛 2027届 校园招聘",
                f"{group_name} 山东 青岛 2027届 校招",
            ]
        )
    return dedupe(base)


def generate_broad_discovery_tasks(conn: sqlite3.Connection, providers: tuple[str, ...]) -> int:
    inserted = 0
    for query in GLOBAL_LOCATION_QUERIES + NATIONAL_SOE_QUERIES + ROLE_LOCATION_QUERIES:
        inserted += insert_task_once(conn, company_id=None, provider_tuple=providers, query=query, reason="broad_discovery")
    return inserted


def generate_site_search_tasks(conn: sqlite3.Connection, providers: tuple[str, ...]) -> int:
    sources = conn.execute(
        """
        SELECT name, site_query_host, tier, source_kind
        FROM search_sources
        WHERE enabled = 1
          AND site_query_host IS NOT NULL
          AND site_query_host != ''
        ORDER BY CASE tier WHEN 'S' THEN 0 WHEN 'A' THEN 1 ELSE 2 END, id
        """
    ).fetchall()
    templates = [
        "site:{host} 2027届 校园招聘",
        "site:{host} 2027届 秋招",
        "site:{host} 2027届 青岛",
        "site:{host} 网络安全 2027届",
    ]
    inserted = 0
    for source in sources:
        for template in templates:
            query = template.format(host=source["site_query_host"])
            inserted += insert_task_once(conn, company_id=None, provider_tuple=providers, query=query, reason="site_search")
    return inserted


def insert_task_once(
    conn: sqlite3.Connection,
    *,
    company_id: int | None,
    provider_tuple: tuple[str, ...],
    query: str,
    reason: str,
) -> int:
    inserted = 0
    for provider in provider_tuple:
        exists = conn.execute(
            """
            SELECT 1 FROM search_tasks
            WHERE COALESCE(company_id, 0) = COALESCE(?, 0)
              AND provider = ?
              AND query = ?
              AND reason = ?
              AND status IN ('pending', 'done')
            LIMIT 1
            """,
            (company_id, provider, query, reason),
        ).fetchone()
        if exists:
            continue
        conn.execute(
            """
            INSERT INTO search_tasks (company_id, query, provider, reason, status)
            VALUES (?, ?, ?, ?, 'pending')
            """,
            (company_id, query, provider, reason),
        )
        inserted += 1
    return inserted


def dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result
