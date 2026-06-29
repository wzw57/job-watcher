from __future__ import annotations

import gzip
import hashlib
import html
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from job_watcher.config import Settings
from job_watcher.crawler.keywords import COMPUTER_KEYWORDS, RECRUITMENT_KEYWORDS, SECURITY_KEYWORDS, matched_keywords


TAG_RE = re.compile(r"<[^>]+>")
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
SCRIPT_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
SPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True)
class CrawlResult:
    checked: int
    fetched: int
    snapshots_inserted: int
    duplicate_snapshots: int
    leads_inserted: int
    errors: int


def run_crawl_once(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    limit: int = 20,
    priority_scope: tuple[str, ...] = ("P0", "P1"),
) -> CrawlResult:
    sources = select_sources(conn, limit=limit, priority_scope=priority_scope)
    counts = {
        "checked": 0,
        "fetched": 0,
        "snapshots_inserted": 0,
        "duplicate_snapshots": 0,
        "leads_inserted": 0,
        "errors": 0,
    }
    for source in sources:
        counts["checked"] += 1
        try:
            fetched = fetch_url(source["url"], settings)
            counts["fetched"] += 1
            snapshot_id, inserted = save_snapshot(conn, settings, source, fetched)
            if inserted:
                counts["snapshots_inserted"] += 1
                lead_inserted = maybe_insert_lead(conn, source, snapshot_id, fetched)
                if lead_inserted:
                    counts["leads_inserted"] += 1
            else:
                counts["duplicate_snapshots"] += 1
            mark_source_checked(conn, int(source["id"]), None)
        except Exception as exc:  # noqa: BLE001 - crawler should keep moving across sources.
            counts["errors"] += 1
            mark_source_checked(conn, int(source["id"]), str(exc)[:500])
        conn.commit()
        time.sleep(0.4)
    return CrawlResult(**counts)


def select_sources(conn: sqlite3.Connection, *, limit: int, priority_scope: tuple[str, ...]) -> list[sqlite3.Row]:
    placeholders = ",".join("?" for _ in priority_scope)
    return conn.execute(
        f"""
        SELECT s.id, s.company_id, s.name, s.url, s.source_type, s.trust_level,
               s.verification_status, c.company_name, c.priority
        FROM sources s
        LEFT JOIN companies c ON c.id = s.company_id
        WHERE s.enabled = 1
          AND s.requires_browser = 0
          AND s.verification_status IN (
            'verified_official',
            'verified_recruitment',
            'verified_government',
            'verified_platform'
          )
          AND (c.priority IN ({placeholders}) OR s.company_id IS NULL)
        ORDER BY
          CASE s.verification_status
            WHEN 'verified_recruitment' THEN 0
            WHEN 'verified_official' THEN 1
            WHEN 'verified_government' THEN 2
            ELSE 3
          END,
          s.last_checked_at IS NOT NULL,
          s.last_checked_at,
          s.trust_level DESC
        LIMIT ?
        """,
        [*priority_scope, limit],
    ).fetchall()


def fetch_url(url: str, settings: Settings) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "User-Agent": settings.crawler.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
        },
    )
    try:
        with urlopen(request, timeout=settings.crawler.timeout_seconds) as response:
            raw = response.read()
            final_url = response.geturl()
            status_code = getattr(response, "status", 200)
            content_type = response.headers.get("Content-Type", "")
    except HTTPError as exc:
        raw = exc.read()
        final_url = exc.geturl()
        status_code = exc.code
        content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
    except URLError as exc:
        raise RuntimeError(f"fetch failed: {exc.reason}") from exc

    encoding = guess_encoding(content_type)
    html_text = raw.decode(encoding, errors="replace")
    title, text = extract_text(html_text)
    content_hash = hashlib.sha256(normalize_for_hash(text or html_text).encode("utf-8")).hexdigest()
    return {
        "url": url,
        "status_code": int(status_code),
        "final_url": final_url,
        "content_type": content_type,
        "html": html_text,
        "title": title,
        "text": text,
        "content_hash": content_hash,
    }


def guess_encoding(content_type: str) -> str:
    match = re.search(r"charset=([\w-]+)", content_type, re.IGNORECASE)
    return match.group(1) if match else "utf-8"


def extract_text(html_text: str) -> tuple[str, str]:
    title_match = TITLE_RE.search(html_text)
    title = html.unescape(SPACE_RE.sub(" ", title_match.group(1)).strip()) if title_match else ""
    body = SCRIPT_RE.sub(" ", html_text)
    body = TAG_RE.sub(" ", body)
    body = html.unescape(SPACE_RE.sub(" ", body).strip())
    return title, body


def normalize_for_hash(text: str) -> str:
    return SPACE_RE.sub(" ", text).strip()


def save_snapshot(
    conn: sqlite3.Connection,
    settings: Settings,
    source: sqlite3.Row,
    fetched: dict[str, Any],
) -> tuple[int | None, bool]:
    html_path, text_path = write_snapshot_files(settings, int(source["id"]), fetched)
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO crawl_snapshots (
            source_id, url, status_code, final_url, title, raw_html_path,
            raw_text_path, content_hash, error
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
        """,
        (
            int(source["id"]),
            source["url"],
            fetched["status_code"],
            fetched["final_url"],
            fetched["title"],
            str(html_path),
            str(text_path),
            fetched["content_hash"],
        ),
    )
    if cur.rowcount == 0:
        row = conn.execute(
            "SELECT id FROM crawl_snapshots WHERE source_id = ? AND content_hash = ?",
            (int(source["id"]), fetched["content_hash"]),
        ).fetchone()
        return (int(row["id"]) if row else None), False
    return int(cur.lastrowid), True


def write_snapshot_files(settings: Settings, source_id: int, fetched: dict[str, Any]) -> tuple[Path, Path]:
    stamp = time.strftime("%Y/%m/%d")
    base_dir = settings.paths.snapshots_dir / stamp
    base_dir.mkdir(parents=True, exist_ok=True)
    short_hash = fetched["content_hash"][:16]
    html_path = base_dir / f"source-{source_id}-{short_hash}.html.gz"
    text_path = base_dir / f"source-{source_id}-{short_hash}.txt.gz"
    with gzip.open(html_path, "wt", encoding="utf-8") as f:
        f.write(fetched["html"])
    with gzip.open(text_path, "wt", encoding="utf-8") as f:
        f.write(fetched["text"])
    return html_path, text_path


def maybe_insert_lead(
    conn: sqlite3.Connection,
    source: sqlite3.Row,
    snapshot_id: int | None,
    fetched: dict[str, Any],
) -> bool:
    text = "\n".join([fetched["title"], fetched["text"]])
    recruitment = matched_keywords(text, RECRUITMENT_KEYWORDS)
    security = matched_keywords(text, SECURITY_KEYWORDS)
    computer = matched_keywords(text, COMPUTER_KEYWORDS)
    if not recruitment:
        return False

    target_year = "2027" if any("2027" in item or "27届" in item for item in recruitment) else ""
    recruitment_type = "campus" if any(item in recruitment for item in ["校园招聘", "校招", "应届生", "秋招", "秋季招聘"]) else ""
    computer_score = min(100, len(computer) * 12)
    security_score = min(100, len(security) * 18)
    trust_score = int(source["trust_level"] or 0)
    overall_score = min(100, len(recruitment) * 10 + computer_score // 2 + security_score + trust_score // 5)
    matched = sorted(set(recruitment + security + computer))

    cur = conn.execute(
        """
        INSERT OR IGNORE INTO job_leads (
            company_id, source_id, snapshot_id, title, url, source_type, content_hash,
            target_year, recruitment_type, matched_keywords, computer_relevance_score,
            security_relevance_score, trust_score, overall_score, status, summary
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
        """,
        (
            source["company_id"],
            int(source["id"]),
            snapshot_id,
            fetched["title"] or source["name"] or source["company_name"] or source["url"],
            fetched["final_url"] or source["url"],
            source["source_type"],
            fetched["content_hash"],
            target_year,
            recruitment_type,
            ",".join(matched),
            computer_score,
            security_score,
            trust_score,
            overall_score,
            make_summary(fetched["text"], matched),
        ),
    )
    return cur.rowcount > 0


def make_summary(text: str, matched: list[str]) -> str:
    prefix = text[:240].strip()
    return f"命中关键词：{', '.join(matched)}\n{prefix}"


def mark_source_checked(conn: sqlite3.Connection, source_id: int, error: str | None) -> None:
    conn.execute(
        """
        UPDATE sources
        SET last_checked_at = CURRENT_TIMESTAMP,
            last_verified_at = CASE WHEN ? IS NULL THEN CURRENT_TIMESTAMP ELSE last_verified_at END,
            notes = CASE WHEN ? IS NULL THEN notes ELSE COALESCE(notes, '') || char(10) || ? END,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (error, error, f"crawl error: {error}" if error else None, source_id),
    )
