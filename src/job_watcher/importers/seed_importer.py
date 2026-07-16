from __future__ import annotations

import csv
import hashlib
import sqlite3
from pathlib import Path
from typing import Any

from job_watcher.config import Settings


def import_all_seed_data(settings: Settings, seed_dir: Path | None = None) -> dict[str, int]:
    from job_watcher.importers.seed_data import validate_seed_data

    seed_dir = seed_dir or settings.paths.data_dir / "processed"
    validate_seed_data(seed_dir)
    companies_path = seed_dir / "companies_seed.csv"
    sources_path = seed_dir / "company_sources_seed.csv"
    fixed_sources_path = settings.root_dir / "config" / "sources.yaml"

    from job_watcher.storage.db import connect, init_db

    init_db(settings)
    with connect(settings) as conn:
        companies = import_companies(conn, companies_path)
        sources = import_company_sources(conn, sources_path)
        fixed_sources = import_fixed_sources(conn, fixed_sources_path)
    return {
        "companies": companies,
        "company_sources": sources,
        "fixed_sources": fixed_sources,
    }


def import_correction_candidates(settings: Settings) -> int:
    path = settings.paths.data_dir / "audit" / "correction_candidates.csv"
    from job_watcher.storage.db import connect, init_db

    init_db(settings)
    rows = read_csv(path)
    with connect(settings) as conn:
        count = 0
        for row in rows:
            company_id = get_company_id(conn, row["company_key"])
            conn.execute(
                """
                INSERT INTO correction_candidates (
                    company_id, candidate_url, candidate_title, candidate_snippet,
                    candidate_source_type, score, confidence, score_reasons,
                    review_status, decision, review_notes, updated_at
                ) VALUES (
                    :company_id, :candidate_url, :candidate_title, :candidate_snippet,
                    :candidate_source_type, :score, :confidence, :score_reasons,
                    :review_status, :decision, :review_notes, CURRENT_TIMESTAMP
                )
                ON CONFLICT(company_id, candidate_url) DO UPDATE SET
                    candidate_title=excluded.candidate_title,
                    candidate_snippet=excluded.candidate_snippet,
                    candidate_source_type=excluded.candidate_source_type,
                    score=excluded.score,
                    confidence=excluded.confidence,
                    score_reasons=excluded.score_reasons,
                    updated_at=CURRENT_TIMESTAMP
                """,
                {
                    "company_id": company_id,
                    "candidate_url": row["candidate_url"],
                    "candidate_title": row.get("candidate_title", ""),
                    "candidate_snippet": row.get("candidate_snippet", ""),
                    "candidate_source_type": row.get("candidate_source_type", ""),
                    "score": int(float(row.get("candidate_score") or 0)),
                    "confidence": row.get("candidate_confidence", ""),
                    "score_reasons": row.get("score_reasons", ""),
                    "review_status": row.get("review_status", "pending") or "pending",
                    "decision": row.get("decision", ""),
                    "review_notes": row.get("review_notes", ""),
                },
            )
            count += 1
        conn.commit()
    return count


def import_companies(conn: sqlite3.Connection, path: Path) -> int:
    rows = read_csv(path)
    count = 0
    for row in rows:
        conn.execute(
            """
            INSERT INTO companies (
                company_key, source_row, original_group_name, group_name,
                original_company_name, company_name, normalized_name, entity_type,
                region, priority_raw, priority, difficulty, education_barrier,
                recommended_directions, action_status, verification_status,
                enabled, notes, updated_at
            ) VALUES (
                :company_key, :source_row, :group_name, :group_name,
                :company_name, :company_name, :normalized_name, :entity_type,
                :region, :priority_raw, :priority, :difficulty, :education_barrier,
                :recommended_directions, :action_status, 'candidate',
                :enabled, :url_notes, CURRENT_TIMESTAMP
            )
            ON CONFLICT(company_key) DO UPDATE SET
                source_row=excluded.source_row,
                original_group_name=excluded.original_group_name,
                group_name=excluded.group_name,
                original_company_name=excluded.original_company_name,
                company_name=excluded.company_name,
                normalized_name=excluded.normalized_name,
                entity_type=excluded.entity_type,
                region=excluded.region,
                priority_raw=excluded.priority_raw,
                priority=excluded.priority,
                difficulty=excluded.difficulty,
                education_barrier=excluded.education_barrier,
                recommended_directions=excluded.recommended_directions,
                action_status=excluded.action_status,
                enabled=excluded.enabled,
                notes=excluded.notes,
                updated_at=CURRENT_TIMESTAMP
            """,
            normalize_company_row(row),
        )
        count += 1
    conn.commit()
    return count


def import_company_sources(conn: sqlite3.Connection, path: Path) -> int:
    rows = read_csv(path)
    count = 0
    for row in rows:
        company_id = get_company_id(conn, row["company_key"])
        source_key = make_source_key(row["company_key"], row["url"])
        conn.execute(
            """
            INSERT INTO sources (
                company_id, source_key, name, url, original_url, source_type,
                provider, trust_level, verification_status, requires_browser,
                enabled, discovered_by, notes, updated_at
            ) VALUES (
                :company_id, :source_key, :company_name, :url, :url, :source_type,
                'excel_seed', :trust_level, 'candidate', 0,
                :enabled, 'excel', :url_notes, CURRENT_TIMESTAMP
            )
            ON CONFLICT(source_key) DO UPDATE SET
                company_id=excluded.company_id,
                name=excluded.name,
                url=excluded.url,
                original_url=excluded.original_url,
                source_type=excluded.source_type,
                provider=excluded.provider,
                trust_level=excluded.trust_level,
                enabled=excluded.enabled,
                notes=excluded.notes,
                updated_at=CURRENT_TIMESTAMP
            """,
            {
                "company_id": company_id,
                "source_key": source_key,
                "company_name": row["company_name"],
                "url": row["url"],
                "source_type": row.get("source_type") or "unknown",
                "trust_level": trust_level_for_source(row.get("source_type", "")),
                "enabled": 1 if row.get("priority") in {"P0", "P1"} else 0,
                "url_notes": row.get("url_notes", ""),
            },
        )
        count += 1
    conn.commit()
    return count


def import_fixed_sources(conn: sqlite3.Connection, path: Path) -> int:
    if not path.exists():
        return 0
    sources = read_sources_yaml(path)
    count = 0
    for item in sources:
        url = str(item.get("url", "")).strip()
        if not url:
            continue
        source_key = make_source_key("global", url)
        conn.execute(
            """
            INSERT INTO sources (
                company_id, source_key, name, url, original_url, source_type,
                provider, trust_level, verification_status, requires_browser,
                enabled, discovered_by, notes, updated_at
            ) VALUES (
                NULL, :source_key, :name, :url, :url, :source_type,
                :provider, :trust_level, 'candidate', :requires_browser,
                :enabled, 'fixed_config', :notes, CURRENT_TIMESTAMP
            )
            ON CONFLICT(source_key) DO UPDATE SET
                name=excluded.name,
                url=excluded.url,
                original_url=excluded.original_url,
                source_type=excluded.source_type,
                provider=excluded.provider,
                trust_level=excluded.trust_level,
                requires_browser=excluded.requires_browser,
                enabled=excluded.enabled,
                notes=excluded.notes,
                updated_at=CURRENT_TIMESTAMP
            """,
            {
                "source_key": source_key,
                "name": item.get("name", ""),
                "url": url,
                "source_type": item.get("source_type", "unknown"),
                "provider": item.get("provider", "fixed"),
                "trust_level": int(item.get("trust_level", 50)),
                "requires_browser": 1 if item.get("requires_browser") else 0,
                "enabled": 1 if item.get("enabled", True) else 0,
                "notes": item.get("notes", ""),
            },
        )
        count += 1
    conn.commit()
    return count


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"Seed file not found: {path}")
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def normalize_company_row(row: dict[str, str]) -> dict[str, Any]:
    normalized = dict(row)
    normalized["source_row"] = int(float(row.get("source_row") or 0))
    normalized["enabled"] = 1 if str(row.get("enabled", "")).lower() in {"true", "1", "yes"} else 0
    return normalized


def get_company_id(conn: sqlite3.Connection, company_key: str) -> int:
    row = conn.execute("SELECT id FROM companies WHERE company_key = ?", (company_key,)).fetchone()
    if row is None:
        raise ValueError(f"Company not found for source import: {company_key}")
    return int(row["id"])


def make_source_key(scope: str, url: str) -> str:
    digest = hashlib.sha1(f"{scope}|{url}".encode("utf-8")).hexdigest()[:16]
    return f"{scope}:{digest}"


def trust_level_for_source(source_type: str) -> int:
    return {
        "government": 88,
        "public_platform": 80,
        "official_recruitment": 78,
        "official_or_unknown": 60,
        "commercial_platform": 45,
    }.get(source_type, 50)


def read_sources_yaml(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml
    except ModuleNotFoundError:
        data = {"sources": parse_sources_yaml_subset(text)}
    else:
        data = yaml.safe_load(text) or {}
    sources = data.get("sources", [])
    if not isinstance(sources, list):
        raise ValueError(f"config sources must be a list: {path}")
    return [item for item in sources if isinstance(item, dict)]


def parse_sources_yaml_subset(text: str) -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    current_key: str | None = None

    for raw_line in text.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        stripped = raw_line.strip()
        if stripped == "sources:":
            continue
        if stripped.startswith("- "):
            if current:
                sources.append(current)
            current = {}
            current_key = None
            remainder = stripped[2:].strip()
            if remainder:
                key, value = split_yaml_pair(remainder)
                current[key] = parse_yaml_scalar(value)
                current_key = key
            continue
        if current is None:
            continue
        if ":" in stripped:
            key, value = split_yaml_pair(stripped)
            current[key] = parse_yaml_scalar(value)
            current_key = key
        elif current_key:
            current[current_key] = f"{current.get(current_key, '')}\n{stripped}".strip()

    if current:
        sources.append(current)
    return sources


def split_yaml_pair(line: str) -> tuple[str, str]:
    if ":" not in line:
        raise ValueError(f"Unsupported YAML line: {line}")
    key, value = line.split(":", 1)
    return key.strip(), value.strip()


def parse_yaml_scalar(value: str) -> Any:
    if value in {"true", "True"}:
        return True
    if value in {"false", "False"}:
        return False
    try:
        return int(value)
    except ValueError:
        return value.strip('"').strip("'")
