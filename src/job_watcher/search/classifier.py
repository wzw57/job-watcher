from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from urllib.parse import urlparse

from job_watcher.crawler.keywords import (
    CAMPUS_RECRUITMENT_KEYWORDS,
    COMPUTER_KEYWORDS,
    RECRUITMENT_CONTEXT_KEYWORDS,
    SECURITY_KEYWORDS,
    TARGET_2027_KEYWORDS,
    matched_keywords,
)


LOCATION_KEYWORDS = ["青岛", "山东", "黄岛", "西海岸", "崂山", "即墨", "胶州", "平度", "莱西", "城阳", "市北", "市南"]
OWNERSHIP_KEYWORDS = ["国企", "央企", "国资", "中央企业", "国有企业", "集团", "股份有限公司", "有限公司"]
PORTAL_KEYWORDS = ["网申", "投递入口", "招聘官网", "招聘系统", "报名入口", "职位列表", "岗位列表", "人才招聘"]
STALE_YEAR_KEYWORDS = ["2026届", "2026 届", "26届", "2025届", "2025 届", "25届"]
AGGREGATOR_DOMAINS = ["gaoxiaojob.com", "bianzhia.com", "yingjiesheng.com", "51job.com", "zhaopin.com", "liepin.com"]
HIGH_TRUST_DOMAINS = ["gov.cn", "sasac.gov.cn", "job.mohrss.gov.cn", "iguopin.com"]


@dataclass(frozen=True)
class ClassificationResult:
    results_checked: int
    leads_inserted: int
    sources_inserted: int
    candidates_inserted: int
    discovered_companies_inserted: int
    invalid_marked: int


@dataclass(frozen=True)
class SearchClassification:
    category: str
    score: int
    matched: list[str]
    target_year: str
    recruitment_type: str
    location: str
    company_name: str
    reasons: list[str]


def classify_unprocessed_results(conn: sqlite3.Connection, *, limit: int = 200) -> ClassificationResult:
    rows = conn.execute(
        """
        SELECT sr.id, sr.task_id, sr.company_id, sr.provider, sr.title, sr.url, sr.snippet,
               st.query, st.reason, c.company_name, c.priority
        FROM search_results sr
        LEFT JOIN search_tasks st ON st.id = sr.task_id
        LEFT JOIN companies c ON c.id = sr.company_id
        WHERE NOT EXISTS (
            SELECT 1 FROM correction_candidates cc WHERE cc.search_result_id = sr.id
        )
          AND NOT EXISTS (
            SELECT 1 FROM job_leads jl WHERE jl.summary LIKE '%search_result_id=' || sr.id || '%'
        )
          AND NOT EXISTS (
            SELECT 1 FROM discovered_companies dc WHERE dc.first_result_id = sr.id
        )
        ORDER BY sr.id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    counts = {
        "results_checked": 0,
        "leads_inserted": 0,
        "sources_inserted": 0,
        "candidates_inserted": 0,
        "discovered_companies_inserted": 0,
        "invalid_marked": 0,
    }
    for row in rows:
        counts["results_checked"] += 1
        classification = classify_row(row)
        if classification.category == "confirmed_2027_lead":
            counts["leads_inserted"] += insert_lead(conn, row, classification)
        elif classification.category == "recruitment_portal":
            inserted_source = insert_source(conn, row, classification)
            counts["sources_inserted"] += inserted_source
            if not inserted_source:
                counts["candidates_inserted"] += insert_candidate(conn, row, classification)
        elif classification.category == "external_company_lead":
            counts["discovered_companies_inserted"] += insert_discovered_company(conn, row, classification)
            counts["candidates_inserted"] += insert_candidate(conn, row, classification)
        elif classification.category == "review_candidate":
            counts["candidates_inserted"] += insert_candidate(conn, row, classification)
        else:
            counts["invalid_marked"] += insert_candidate(conn, row, classification, review_status="rejected")
        conn.commit()
    return ClassificationResult(**counts)


def classify_row(row: sqlite3.Row) -> SearchClassification:
    title = row["title"] or ""
    snippet = row["snippet"] or ""
    query = row["query"] or ""
    url = row["url"] or ""
    company_name = row["company_name"] or infer_company_name(title, snippet)
    text = f"{title} {snippet} {query} {url}"

    target = matched_keywords(text, TARGET_2027_KEYWORDS)
    campus = matched_keywords(text, CAMPUS_RECRUITMENT_KEYWORDS)
    context = matched_keywords(text, RECRUITMENT_CONTEXT_KEYWORDS)
    security = matched_keywords(text, SECURITY_KEYWORDS)
    computer = matched_keywords(text, COMPUTER_KEYWORDS)
    location = matched_keywords(text, LOCATION_KEYWORDS)
    ownership = matched_keywords(text, OWNERSHIP_KEYWORDS)
    stale = matched_keywords(text, STALE_YEAR_KEYWORDS)
    portal = matched_keywords(text, PORTAL_KEYWORDS)
    domain = urlparse(url).netloc.lower()

    score = 0
    reasons: list[str] = []
    if target:
        score += 30
        reasons.append("明确2027届：" + "、".join(target))
    if campus:
        score += 20
        reasons.append("校园招聘语义：" + "、".join(campus))
    if location:
        score += 12
        reasons.append("青岛/山东相关：" + "、".join(location[:3]))
    if ownership:
        score += 8
        reasons.append("央国企/国资相关：" + "、".join(ownership[:3]))
    if row["company_id"]:
        score += 12
        reasons.append("匹配已知企业")
    if security:
        score += 12
        reasons.append("网络安全相关：" + "、".join(security[:3]))
    elif computer:
        score += 7
        reasons.append("泛计算机相关：" + "、".join(computer[:3]))
    if any(item in domain for item in HIGH_TRUST_DOMAINS):
        score += 8
        reasons.append("高可信域名")
    if any(item in domain for item in AGGREGATOR_DOMAINS):
        score -= 6
        reasons.append("聚合来源需复核")
    if stale:
        score -= 45
        reasons.append("旧届别：" + "、".join(stale))

    matched = sorted(set(target + campus + context + security + computer + location + ownership))
    bounded = max(0, min(100, score))
    target_year = "2027" if target else ""
    recruitment_type = "campus" if campus else ""
    location_text = ",".join(location)

    if stale:
        category = "invalid"
    elif target and campus and row["company_id"]:
        category = "confirmed_2027_lead"
    elif target and campus and location:
        category = "external_company_lead"
    elif portal and not (target and campus):
        category = "recruitment_portal"
    elif target or campus or security or location:
        category = "review_candidate"
    else:
        category = "invalid"

    return SearchClassification(
        category=category,
        score=bounded,
        matched=matched,
        target_year=target_year,
        recruitment_type=recruitment_type,
        location=location_text,
        company_name=company_name,
        reasons=reasons or ["未命中有效2027届招聘证据"],
    )


def insert_lead(conn: sqlite3.Connection, row: sqlite3.Row, item: SearchClassification) -> int:
    content_hash = hashlib.sha256(f"search:{row['id']}:{row['url']}".encode("utf-8")).hexdigest()
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO job_leads (
            company_id, source_id, snapshot_id, title, url, source_type, content_hash,
            target_year, recruitment_type, location, matched_keywords,
            computer_relevance_score, security_relevance_score, trust_score,
            overall_score, status, summary
        ) VALUES (?, NULL, NULL, ?, ?, 'search_result', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
        """,
        (
            row["company_id"],
            row["title"],
            row["url"],
            content_hash,
            item.target_year,
            item.recruitment_type,
            item.location,
            ",".join(item.matched),
            score_keyword_group(item.matched, COMPUTER_KEYWORDS),
            score_keyword_group(item.matched, SECURITY_KEYWORDS),
            70,
            item.score,
            make_summary(row, item),
        ),
    )
    return cur.rowcount


def insert_source(conn: sqlite3.Connection, row: sqlite3.Row, item: SearchClassification) -> int:
    if not row["company_id"]:
        return 0
    source_key = "search-source:" + hashlib.sha1(f"{row['company_id']}|{row['url']}".encode("utf-8")).hexdigest()[:16]
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO sources (
            company_id, source_key, name, url, original_url, source_type, provider,
            trust_level, verification_status, enabled, discovered_by, notes
        ) VALUES (?, ?, ?, ?, ?, 'official_recruitment', 'search_monitor',
                  70, 'candidate', 1, 'search_monitor', ?)
        """,
        (
            row["company_id"],
            source_key,
            row["title"] or item.company_name or "搜索发现招聘入口",
            row["url"],
            row["url"],
            make_summary(row, item),
        ),
    )
    return cur.rowcount


def insert_candidate(
    conn: sqlite3.Connection,
    row: sqlite3.Row,
    item: SearchClassification,
    *,
    review_status: str = "pending",
) -> int:
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO correction_candidates (
            company_id, search_result_id, candidate_url, candidate_title,
            candidate_snippet, candidate_source_type, score, confidence,
            score_reasons, review_status
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["company_id"],
            int(row["id"]),
            row["url"],
            row["title"],
            row["snippet"],
            item.category,
            item.score,
            confidence(item.score),
            "；".join(item.reasons),
            review_status,
        ),
    )
    return cur.rowcount


def insert_discovered_company(conn: sqlite3.Connection, row: sqlite3.Row, item: SearchClassification) -> int:
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO discovered_companies (
            company_name, matched_location, matched_ownership, matched_direction,
            first_result_id, evidence_url, evidence_title, evidence_snippet,
            score, review_status, notes
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
        """,
        (
            item.company_name or "待识别企业",
            item.location,
            ",".join(matched_keywords(f"{row['title']} {row['snippet']}", OWNERSHIP_KEYWORDS)),
            ",".join(matched_keywords(f"{row['title']} {row['snippet']}", SECURITY_KEYWORDS + COMPUTER_KEYWORDS)),
            int(row["id"]),
            row["url"],
            row["title"],
            row["snippet"],
            item.score,
            make_summary(row, item),
        ),
    )
    return cur.rowcount


def infer_company_name(title: str, snippet: str) -> str:
    text = f"{title} {snippet}"
    patterns = [
        r"([\u4e00-\u9fa5A-Za-z0-9（）()]{2,36}(?:有限公司|股份有限公司|集团|分公司))",
        r"([\u4e00-\u9fa5A-Za-z0-9（）()]{4,40})(?:2027届|2027 届|校园招聘|校招|秋招)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return ""


def score_keyword_group(matched: list[str], group: list[str]) -> int:
    group_set = set(group)
    return min(100, sum(1 for item in matched if item in group_set) * 20)


def make_summary(row: sqlite3.Row, item: SearchClassification) -> str:
    return (
        f"search_result_id={row['id']}\n"
        f"query={row['query'] or ''}\n"
        f"provider={row['provider']}\n"
        f"category={item.category}\n"
        f"reasons={'；'.join(item.reasons)}\n"
        f"snippet={row['snippet'] or ''}"
    )


def confidence(score: int) -> str:
    if score >= 75:
        return "high"
    if score >= 55:
        return "medium"
    return "low"
