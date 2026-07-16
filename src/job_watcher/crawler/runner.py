from __future__ import annotations

import gzip
import hashlib
import html
import json
import re
import sqlite3
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from job_watcher.collectors import CollectionResult, Collector, build_collector
from job_watcher.config import Settings
from job_watcher.crawler.keywords import (
    CAMPUS_RECRUITMENT_KEYWORDS,
    COMPUTER_KEYWORDS,
    RECRUITMENT_CONTEXT_KEYWORDS,
    RECRUITMENT_KEYWORDS,
    SECURITY_KEYWORDS,
    TARGET_2027_KEYWORDS,
    matched_keywords,
)


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
    raw_items_new: int
    reviews_created: int


def run_crawl_once(
    conn: sqlite3.Connection,
    settings: Settings,
    *,
    limit: int = 20,
    priority_scope: tuple[str, ...] = ("P0", "P1"),
    collector: Collector | None = None,
) -> CrawlResult:
    collector = collector or build_collector(settings)
    sources = select_sources(conn, limit=limit, priority_scope=priority_scope)
    counts = {
        "checked": 0,
        "fetched": 0,
        "snapshots_inserted": 0,
        "duplicate_snapshots": 0,
        "leads_inserted": 0,
        "errors": 0,
        "raw_items_new": 0,
        "reviews_created": 0,
    }
    for source in sources:
        counts["checked"] += 1
        run_id = start_source_run(conn, int(source["id"]))
        started = time.monotonic()
        try:
            result = collector.collect(source["url"])
            raw_item_id, raw_is_new = save_raw_item(conn, settings, source, result)
            counts["raw_items_new"] += int(raw_is_new)
            if not result.succeeded:
                counts["errors"] += 1
                created = ensure_collection_review(conn, source, raw_item_id, result)
                counts["reviews_created"] += int(created)
                finish_source_run(conn, run_id, result, started, items_seen=1, items_new=int(raw_is_new))
                mark_source_health(conn, int(source["id"]), result)
                conn.commit()
                continue
            run_result = result if raw_is_new else replace(result, status="no_content_change")
            items_seen = 1
            items_new = int(raw_is_new)
            attachment_failures = 0
            for attachment in result.attachments[:settings.crawler.max_attachments]:
                attachment_result = collector.collect(attachment["url"])
                attachment_result = replace(
                    attachment_result,
                    metadata={**dict(attachment_result.metadata), "parent_url": result.final_url, "link_label": attachment.get("label", "")},
                )
                attachment_id, attachment_is_new = save_raw_item(conn, settings, source, attachment_result)
                items_seen += 1
                items_new += int(attachment_is_new)
                counts["raw_items_new"] += int(attachment_is_new)
                if not attachment_result.succeeded:
                    attachment_failures += 1
                    counts["errors"] += 1
                    counts["reviews_created"] += int(ensure_collection_review(conn, source, attachment_id, attachment_result))
            fetched = collection_result_dict(result)
            counts["fetched"] += 1
            snapshot_id, inserted = save_snapshot(conn, settings, source, fetched)
            if inserted:
                counts["snapshots_inserted"] += 1
                lead_inserted = maybe_insert_lead(conn, source, snapshot_id, fetched)
                if lead_inserted:
                    counts["leads_inserted"] += 1
            else:
                counts["duplicate_snapshots"] += 1
            final_run_result = replace(run_result, status="partial_success", error_type="attachment_failure",
                                       error_message=f"{attachment_failures} attachment(s) failed") if attachment_failures else run_result
            finish_source_run(conn, run_id, final_run_result, started, items_seen=items_seen, items_new=items_new)
            mark_source_health(conn, int(source["id"]), run_result)
        except Exception as exc:  # noqa: BLE001 - crawler should keep moving across sources.
            counts["errors"] += 1
            result = CollectionResult("internal_error", source["url"], source["url"], error_type=type(exc).__name__, error_message=str(exc)[:500])
            finish_source_run(conn, run_id, result, started, items_seen=0, items_new=0)
            mark_source_checked(conn, int(source["id"]), str(exc)[:500])
        conn.commit()
        time.sleep(0.4)
    return CrawlResult(**counts)


def collection_result_dict(result: CollectionResult) -> dict[str, Any]:
    return {"url": result.requested_url, "status_code": result.http_status or 0,
            "final_url": result.final_url, "content_type": result.content_type,
            "html": result.html, "title": result.title, "text": result.text,
            "content_hash": result.content_hash}


def start_source_run(conn: sqlite3.Connection, source_id: int) -> int:
    cur = conn.execute("INSERT INTO source_runs(source_id,status) VALUES (?, 'running')", (source_id,))
    return int(cur.lastrowid)


def finish_source_run(conn: sqlite3.Connection, run_id: int, result: CollectionResult, started: float, *, items_seen: int, items_new: int) -> None:
    conn.execute(
        """UPDATE source_runs SET finished_at=CURRENT_TIMESTAMP, status=?, http_status=?,
           items_seen=?, items_new=?, duration_ms=?, error_type=?, error_message=? WHERE id=?""",
        (result.status, result.http_status, items_seen, items_new, int((time.monotonic()-started)*1000),
         result.error_type or None, result.error_message or None, run_id),
    )


def save_raw_item(conn: sqlite3.Connection, settings: Settings, source: sqlite3.Row, result: CollectionResult) -> tuple[int, bool]:
    canonical = result.final_url or result.requested_url
    existing = conn.execute("SELECT id,content_hash FROM raw_items WHERE source_id=? AND canonical_url=?", (source["id"], canonical)).fetchone()
    is_new = existing is None or (bool(result.content_hash) and existing["content_hash"] != result.content_hash)
    crawl_status = "success" if result.succeeded else result.status
    parse_status = "parsed" if result.succeeded else ("failed" if result.status == "parse_failed" else "pending")
    url_hash = hashlib.sha256(canonical.encode()).hexdigest()
    stored_path = persist_binary_evidence(settings, int(source["id"]), result) if result.content_bytes else ""
    metadata = {"http_status": result.http_status, "content_type": result.content_type,
                "error_type": result.error_type, **dict(result.metadata)}
    if stored_path:
        metadata["stored_path"] = stored_path
    conn.execute(
        """INSERT INTO raw_items(source_id,entity_hint,title,url,canonical_url,content_text,content_html_path,attachments_json,content_hash,url_hash,
           crawl_status,parse_status,credibility,merge_status,raw_metadata_json,updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'unprocessed',?,CURRENT_TIMESTAMP)
           ON CONFLICT(source_id,canonical_url) DO UPDATE SET title=excluded.title,content_text=excluded.content_text,
           content_html_path=excluded.content_html_path,attachments_json=excluded.attachments_json,content_hash=excluded.content_hash,crawl_status=excluded.crawl_status,parse_status=excluded.parse_status,
           raw_metadata_json=excluded.raw_metadata_json,last_seen_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP""",
        (source["id"], source["company_name"], result.title, result.requested_url, canonical, result.text,
         stored_path or None, json.dumps(list(result.attachments), ensure_ascii=False), result.content_hash or None,
         url_hash, crawl_status, parse_status, int(source["trust_level"] or 50), json.dumps(metadata, ensure_ascii=False)),
    )
    row = conn.execute("SELECT id FROM raw_items WHERE source_id=? AND canonical_url=?", (source["id"], canonical)).fetchone()
    return int(row["id"]), is_new


def persist_binary_evidence(settings: Settings, source_id: int, result: CollectionResult) -> str:
    stamp = time.strftime("%Y/%m/%d")
    directory = settings.paths.snapshots_dir / "attachments" / stamp
    directory.mkdir(parents=True, exist_ok=True)
    suffix = Path(result.final_url.split("?", 1)[0]).suffix.lower()
    if suffix not in {".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv"}:
        suffix = ".bin"
    digest = result.content_hash or hashlib.sha256(result.content_bytes).hexdigest()
    path = directory / f"source-{source_id}-{digest[:16]}{suffix}"
    if not path.exists():
        path.write_bytes(result.content_bytes)
    return str(path)


def ensure_collection_review(conn: sqlite3.Connection, source: sqlite3.Row, raw_item_id: int, result: CollectionResult) -> bool:
    if result.status not in {"blocked", "needs_browser", "parse_failed", "http_error", "network_error", "too_large", "browser_error", "browser_unavailable"}:
        return False
    title = f"来源采集异常：{source['name'] or source['url']} [{result.status}]"
    existing = conn.execute("SELECT id FROM review_tasks WHERE source_id=? AND task_type='collection_failure' AND title=? AND status IN ('pending','in_progress')", (source["id"], title)).fetchone()
    if existing:
        return False
    conn.execute(
        """INSERT INTO review_tasks(task_type,company_id,source_id,raw_item_id,title,description,suggested_action,priority)
           VALUES ('collection_failure',?,?,?,?,?,?,?)""",
        (source["company_id"], source["id"], raw_item_id, title,
         result.error_message or result.error_type, "切换浏览器采集或人工核验来源", "A" if result.status in {"blocked","needs_browser"} else "B"),
    )
    return True


def mark_source_health(conn: sqlite3.Connection, source_id: int, result: CollectionResult) -> None:
    healthy = result.succeeded
    conn.execute(
        """UPDATE sources SET last_checked_at=CURRENT_TIMESTAMP,
           last_verified_at=CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE last_verified_at END,
           last_success_at=CASE WHEN ? THEN CURRENT_TIMESTAMP ELSE last_success_at END,
           last_content_at=CASE WHEN ? AND ? <> '' THEN CURRENT_TIMESTAMP ELSE last_content_at END,
           health_status=?, consecutive_failures=CASE WHEN ? THEN 0 ELSE consecutive_failures+1 END,
           requires_browser=CASE WHEN ?='needs_browser' THEN 1 ELSE requires_browser END,
           updated_at=CURRENT_TIMESTAMP WHERE id=?""",
        (healthy,healthy,healthy,result.content_hash,"healthy" if healthy else result.status,healthy,result.status,source_id),
    )


def select_sources(conn: sqlite3.Connection, *, limit: int, priority_scope: tuple[str, ...]) -> list[sqlite3.Row]:
    placeholders = ",".join("?" for _ in priority_scope)
    return conn.execute(
        f"""
        SELECT s.id, s.company_id, s.name, s.url, s.source_type, s.trust_level,
               s.verification_status, c.company_name, c.priority
        FROM sources s
        LEFT JOIN companies c ON c.id = s.company_id
        WHERE s.enabled = 1
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
    target_2027 = matched_keywords(text, TARGET_2027_KEYWORDS)
    campus_recruitment = matched_keywords(text, CAMPUS_RECRUITMENT_KEYWORDS)
    recruitment_context = matched_keywords(text, RECRUITMENT_CONTEXT_KEYWORDS)
    recruitment = matched_keywords(text, RECRUITMENT_KEYWORDS)
    security = matched_keywords(text, SECURITY_KEYWORDS)
    computer = matched_keywords(text, COMPUTER_KEYWORDS)

    # A generic application portal is useful as a source, but it is not a
    # 2027 campus recruitment lead until both year and campus-recruitment
    # intent are present on the page.
    if not target_2027 or not campus_recruitment:
        return False

    target_year = "2027"
    recruitment_type = "campus"
    computer_score = min(100, len(computer) * 12)
    security_score = min(100, len(security) * 18)
    trust_score = int(source["trust_level"] or 0)
    overall_score = min(
        100,
        len(target_2027) * 24
        + len(campus_recruitment) * 16
        + len(recruitment_context) * 4
        + computer_score // 2
        + security_score
        + trust_score // 5,
    )
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
