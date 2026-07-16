from __future__ import annotations

import html
import hashlib
import sqlite3
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from job_watcher.config import Settings, load_settings
from job_watcher.reporting.coverage import companies_needing_sources, coverage_by_priority, coverage_summary
from job_watcher.storage.db import connect, init_db


PAGE_SIZE = 50


def run_server(settings: Settings) -> None:
    init_db(settings)
    server = ThreadingHTTPServer((settings.web.host, settings.web.port), make_handler(settings))
    print(f"Web dashboard: http://{settings.web.host}:{settings.web.port}")
    server.serve_forever()


def make_handler(settings: Settings) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            route_get(self, settings)

        def do_POST(self) -> None:  # noqa: N802
            route_post(self, settings)

        def log_message(self, format: str, *args: Any) -> None:
            print("%s - %s" % (self.address_string(), format % args))

    return Handler


def route_get(handler: BaseHTTPRequestHandler, settings: Settings) -> None:
    parsed = urlparse(handler.path)
    params = parse_qs(parsed.query)
    if parsed.path == "/":
        redirect(handler, "/radar")
        return
    if parsed.path == "/radar":
        render(handler, "今日雷达", render_radar(settings))
        return
    if parsed.path == "/jobs":
        render(handler, "招聘事件库", render_jobs(settings, params))
        return
    if parsed.path == "/applications":
        render(handler, "投递进度", render_applications(settings, params))
        return
    if parsed.path == "/reviews":
        render(handler, "人工核验", render_reviews(settings, params))
        return
    if parsed.path == "/companies":
        render(handler, "企业库", render_companies(settings, params))
        return
    if parsed.path == "/coverage":
        render(handler, "可信来源覆盖率", render_coverage(settings, params))
        return
    if parsed.path == "/sources":
        render(handler, "来源管理", render_sources(settings, params))
        return
    if parsed.path == "/candidates":
        render(handler, "修正候选", render_candidates(settings, params))
        return
    if parsed.path == "/leads":
        render(handler, "招聘线索", render_leads(settings, params))
        return
    if parsed.path == "/search-results":
        render(handler, "搜索发现", render_search_results(settings, params))
        return
    if parsed.path == "/discovered-companies":
        render(handler, "表外企业候选", render_discovered_companies(settings, params))
        return
    if parsed.path == "/health":
        send_text(handler, "ok")
        return
    send_text(handler, "not found", status=HTTPStatus.NOT_FOUND)


def route_post(handler: BaseHTTPRequestHandler, settings: Settings) -> None:
    parsed = urlparse(handler.path)
    length = int(handler.headers.get("Content-Length", "0"))
    body = handler.rfile.read(length).decode("utf-8")
    form = {key: values[0] for key, values in parse_qs(body).items()}
    if parsed.path == "/candidates/update":
        update_candidate(settings, form)
        redirect(handler, form.get("next", "/candidates"))
        return
    if parsed.path == "/sources/update":
        update_source(settings, form)
        redirect(handler, form.get("next", "/sources"))
        return
    if parsed.path == "/jobs/update":
        update_job(settings, form)
        redirect(handler, form.get("next", "/jobs"))
        return
    if parsed.path == "/applications/save":
        save_application(settings, form)
        redirect(handler, form.get("next", "/applications"))
        return
    if parsed.path == "/reviews/update":
        update_review(settings, form)
        redirect(handler, form.get("next", "/reviews"))
        return
    send_text(handler, "not found", status=HTTPStatus.NOT_FOUND)


def render_radar(settings: Settings) -> str:
    with connect(settings) as conn:
        counts = conn.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM job_events WHERE date(first_seen_at) = date('now', 'localtime')) AS new_today,
              (SELECT COUNT(*) FROM job_events WHERE status IN ('open', 'pending_review')) AS open_jobs,
              (SELECT COUNT(*) FROM job_events WHERE deadline_at IS NOT NULL
                 AND date(deadline_at) BETWEEN date('now', 'localtime') AND date('now', 'localtime', '+7 days')) AS closing_soon,
              (SELECT COUNT(*) FROM review_tasks WHERE status = 'pending') AS pending_reviews,
              (SELECT COUNT(*) FROM applications WHERE status NOT IN ('offer', 'rejected', 'abandoned')) AS active_applications,
              (SELECT COUNT(*) FROM sources WHERE health_status IN ('error', 'blocked', 'structure_changed', 'stale')) AS unhealthy_sources
            """
        ).fetchone()
        jobs = conn.execute(
            """
            SELECT je.id, je.title, je.match_score, je.match_level, je.qingdao_level,
                   je.deadline_at, je.status, je.application_url, c.company_name
            FROM job_events je
            LEFT JOIN companies c ON c.id = je.entity_id
            WHERE je.status IN ('open', 'pending_review')
            ORDER BY je.match_score DESC, je.first_seen_at DESC
            LIMIT 12
            """
        ).fetchall()
        reviews = conn.execute(
            """
            SELECT id, priority, task_type, title, created_at
            FROM review_tasks WHERE status = 'pending'
            ORDER BY CASE priority WHEN 'S' THEN 0 WHEN 'A' THEN 1 WHEN 'B' THEN 2 ELSE 3 END, created_at
            LIMIT 10
            """
        ).fetchall()

    cards = f"""
    <div class="cards">
      <div class="card"><strong>{counts['new_today']}</strong><span>今日新增</span></div>
      <div class="card"><strong>{counts['open_jobs']}</strong><span>开放/待核招聘</span></div>
      <div class="card"><strong>{counts['closing_soon']}</strong><span>7日内截止</span></div>
      <div class="card"><strong>{counts['active_applications']}</strong><span>进行中投递</span></div>
      <div class="card"><strong>{counts['pending_reviews']}</strong><span>待人工核验</span></div>
      <div class="card"><strong>{counts['unhealthy_sources']}</strong><span>异常渠道</span></div>
    </div>
    """
    job_table = table_html(
        ["匹配", "企业", "招聘事件", "青岛关系", "截止", "状态", "入口"],
        [[r["match_score"], html.escape(r["company_name"] or "待识别"), html.escape(r["title"]),
          r["qingdao_level"], r["deadline_at"] or "-", r["status"], link(r["application_url"])] for r in jobs],
    )
    review_table = table_html(
        ["优先级", "类型", "任务", "创建时间"],
        [[r["priority"], r["task_type"], html.escape(r["title"]), r["created_at"]] for r in reviews],
    )
    return cards + "<h3>优先查看</h3>" + job_table + "<h3>待核验事项</h3>" + review_table


def render_jobs(settings: Settings, params: dict[str, list[str]]) -> str:
    status, match_level, qingdao_level, q = (first(params, key) for key in ("status", "match_level", "qingdao_level", "q"))
    where, values = [], []
    for column, value in (("je.status", status), ("je.match_level", match_level), ("je.qingdao_level", qingdao_level)):
        if value:
            where.append(f"{column} = ?")
            values.append(value)
    if q:
        where.append("(je.title LIKE ? OR c.company_name LIKE ? OR c.group_name LIKE ?)")
        values.extend([f"%{q}%"] * 3)
    where_sql = " WHERE " + " AND ".join(where) if where else ""
    with connect(settings) as conn:
        rows = conn.execute(
            f"""
            SELECT je.id, je.title, je.recruitment_type, je.qingdao_level, je.deadline_at,
                   je.application_url, je.match_score, je.match_level, je.status, je.first_seen_at,
                   c.company_name, c.priority,
                   (SELECT COUNT(*) FROM raw_items ri WHERE ri.job_event_id = je.id) AS source_count,
                   (SELECT COUNT(*) FROM job_positions jp WHERE jp.job_event_id = je.id) AS position_count
            FROM job_events je LEFT JOIN companies c ON c.id = je.entity_id
            {where_sql}
            ORDER BY je.match_score DESC, je.first_seen_at DESC LIMIT 300
            """, values,
        ).fetchall()
    filters = filter_bar("/jobs", {"q": q}, extra=(
        '<select name="status"><option value="">全部状态</option>' + options(["pending_review", "open", "closing_soon", "closed", "invalid"], status) + '</select>'
        '<select name="match_level"><option value="">全部匹配度</option>' + options(["strong", "worth_reviewing", "possible", "pending", "mismatch"], match_level) + '</select>'
        '<select name="qingdao_level"><option value="">全部地点</option>' + options(["confirmed", "possible", "shandong", "national", "pending", "outside"], qingdao_level) + '</select>'
    ))
    rows_html = []
    for r in rows:
        rows_html.append([r["priority"] or "-", html.escape(r["company_name"] or "待识别"), r["match_score"],
            r["match_level"], html.escape(r["title"]), r["recruitment_type"], r["qingdao_level"],
            r["position_count"], r["source_count"], r["deadline_at"] or "-", link(r["application_url"]),
            job_status_form(r["id"], r["status"], current_path(params, "/jobs"))])
    return filters + summary(len(rows), 1) + table_html(
        ["优先级", "企业", "分数", "匹配", "招聘事件", "类型", "地点", "岗位", "来源", "截止", "报名", "状态"], rows_html)


def render_applications(settings: Settings, params: dict[str, list[str]]) -> str:
    status = first(params, "status")
    where, values = (" WHERE a.status = ?", [status]) if status else ("", [])
    with connect(settings) as conn:
        rows = conn.execute(
            f"""SELECT a.id, a.status, a.priority, a.resume_version, a.applied_at, a.next_action,
                       a.next_action_at, a.result, a.notes, je.title, c.company_name
                FROM applications a JOIN job_events je ON je.id = a.job_event_id
                LEFT JOIN companies c ON c.id = a.company_id {where}
                ORDER BY COALESCE(a.next_action_at, '9999-12-31'), a.updated_at DESC""", values,
        ).fetchall()
    filters = filter_bar("/applications", {"q": ""}, extra='<select name="status"><option value="">全部状态</option>' + options(application_statuses(), status) + '</select>')
    rows_html = [[r["priority"], html.escape(r["company_name"] or "-"), html.escape(r["title"]), r["resume_version"] or "-",
        r["applied_at"] or "-", r["next_action"] or "-", r["next_action_at"] or "-", r["result"] or "-",
        application_form(r["id"], r["status"], "/applications")] for r in rows]
    return filters + table_html(["优先级", "企业", "岗位/批次", "简历", "投递时间", "下一步", "提醒", "结果", "状态"], rows_html)


def render_reviews(settings: Settings, params: dict[str, list[str]]) -> str:
    status = first(params, "status") or "pending"
    with connect(settings) as conn:
        rows = conn.execute(
            """SELECT rt.id, rt.priority, rt.task_type, rt.title, rt.description, rt.suggested_action,
                      rt.status, rt.created_at, c.company_name, s.url
               FROM review_tasks rt LEFT JOIN companies c ON c.id = rt.company_id
               LEFT JOIN sources s ON s.id = rt.source_id WHERE rt.status = ?
               ORDER BY CASE rt.priority WHEN 'S' THEN 0 WHEN 'A' THEN 1 WHEN 'B' THEN 2 ELSE 3 END, rt.created_at""",
            (status,),
        ).fetchall()
    filters = filter_bar("/reviews", {"q": ""}, extra='<select name="status">' + options(["pending", "in_progress", "resolved", "ignored"], status) + '</select>')
    rows_html = [[r["priority"], r["task_type"], html.escape(r["company_name"] or "-"), html.escape(r["title"]),
        truncate(r["description"], 160), truncate(r["suggested_action"], 100), link(r["url"]),
        review_form(r["id"], r["status"], "/reviews")] for r in rows]
    return filters + summary(len(rows), 1) + table_html(["优先级", "类型", "企业", "问题", "说明", "建议", "证据", "处理"], rows_html)


def render_companies(settings: Settings, params: dict[str, list[str]]) -> str:
    priority = first(params, "priority")
    status = first(params, "status")
    q = first(params, "q")
    page = int(first(params, "page") or "1")
    offset = (page - 1) * PAGE_SIZE

    where = []
    values: list[Any] = []
    if priority:
        where.append("priority = ?")
        values.append(priority)
    if status:
        where.append("verification_status = ?")
        values.append(status)
    if q:
        where.append("(company_name LIKE ? OR group_name LIKE ? OR recommended_directions LIKE ?)")
        values.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    where_sql = " WHERE " + " AND ".join(where) if where else ""

    with connect(settings) as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM companies{where_sql}", values).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT id, company_key, priority, group_name, company_name, region,
                   entity_type, recommended_directions, verification_status, enabled
            FROM companies
            {where_sql}
            ORDER BY
              CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 ELSE 4 END,
              company_name
            LIMIT ? OFFSET ?
            """,
            [*values, PAGE_SIZE, offset],
        ).fetchall()

    filters = filter_bar(
        "/companies",
        {
            "priority": priority,
            "status": status,
            "q": q,
        },
        extra="""
        <select name="priority">
          <option value="">全部优先级</option>
          {priority_options}
        </select>
        <select name="status">
          <option value="">全部状态</option>
          {status_options}
        </select>
        """.format(
            priority_options=options(["P0", "P1", "P2", "P3", "P4"], priority),
            status_options=options(["candidate", "verified", "corrected", "needs_review", "out_of_scope"], status),
        ),
    )
    table = table_html(
        ["优先级", "集团", "主体公司", "区域", "性质", "推荐方向", "状态", "启用"],
        [
            [
                r["priority"],
                r["group_name"],
                r["company_name"],
                r["region"],
                r["entity_type"],
                truncate(r["recommended_directions"], 80),
                r["verification_status"],
                "是" if r["enabled"] else "否",
            ]
            for r in rows
        ],
    )
    return filters + summary(total, page) + table + pager("/companies", params, total, page)


def render_coverage(settings: Settings, params: dict[str, list[str]]) -> str:
    with connect(settings) as conn:
        summary_row = coverage_summary(conn, tuple(settings.priority_scope))
        by_priority = coverage_by_priority(conn)
        needing = companies_needing_sources(conn, tuple(settings.priority_scope), limit=100)

    cards = f"""
    <div class="cards">
      <div class="card"><strong>{summary_row.total_companies}</strong><span>P0/P1 企业</span></div>
      <div class="card"><strong>{summary_row.with_verified_source}</strong><span>已有可信来源 ({summary_row.verified_rate:.1%})</span></div>
      <div class="card"><strong>{summary_row.with_recruitment_source}</strong><span>已有招聘入口 ({summary_row.recruitment_rate:.1%})</span></div>
      <div class="card"><strong>{summary_row.with_candidate_only}</strong><span>仅候选来源</span></div>
      <div class="card"><strong>{summary_row.without_sources}</strong><span>无来源</span></div>
    </div>
    """
    priority_table = table_html(
        ["优先级", "企业数", "可信来源", "招聘入口", "无来源"],
        [
            [
                r["priority"],
                r["total"],
                r["verified"],
                r["recruitment"],
                r["no_source"],
            ]
            for r in by_priority
        ],
    )
    needing_table = table_html(
        ["优先级", "集团", "主体公司", "区域", "候选来源数", "推荐方向"],
        [
            [
                r["priority"],
                r["group_name"],
                r["company_name"],
                r["region"],
                r["source_count"],
                truncate(r["recommended_directions"], 100),
            ]
            for r in needing
        ],
    )
    return (
        cards
        + "<h3>按优先级统计</h3>"
        + priority_table
        + "<h3>待补全可信来源的 P0/P1 企业</h3>"
        + needing_table
    )


def render_sources(settings: Settings, params: dict[str, list[str]]) -> str:
    status = first(params, "status")
    source_type = first(params, "source_type")
    q = first(params, "q")
    page = int(first(params, "page") or "1")
    offset = (page - 1) * PAGE_SIZE

    where = []
    values: list[Any] = []
    if status:
        where.append("s.verification_status = ?")
        values.append(status)
    if source_type:
        where.append("s.source_type = ?")
        values.append(source_type)
    if q:
        where.append("(s.url LIKE ? OR s.name LIKE ? OR c.company_name LIKE ?)")
        values.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    where_sql = " WHERE " + " AND ".join(where) if where else ""

    with connect(settings) as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM sources s LEFT JOIN companies c ON c.id = s.company_id{where_sql}",
            values,
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT s.id, s.name, s.url, s.source_type, s.provider, s.trust_level,
                   s.verification_status, s.requires_browser, s.enabled,
                   c.company_name, c.priority
            FROM sources s
            LEFT JOIN companies c ON c.id = s.company_id
            {where_sql}
            ORDER BY s.enabled DESC, s.trust_level DESC, s.id
            LIMIT ? OFFSET ?
            """,
            [*values, PAGE_SIZE, offset],
        ).fetchall()

    filters = filter_bar(
        "/sources",
        {"status": status, "source_type": source_type, "q": q},
        extra="""
        <select name="status"><option value="">全部状态</option>{status_options}</select>
        <select name="source_type"><option value="">全部类型</option>{type_options}</select>
        """.format(
            status_options=options(
                [
                    "candidate",
                    "verified_official",
                    "verified_recruitment",
                    "verified_government",
                    "verified_platform",
                    "needs_search",
                    "needs_browser",
                    "invalid_replaced",
                    "invalid_unresolved",
                ],
                status,
            ),
            type_options=options(
                [
                    "official_or_unknown",
                    "official_recruitment",
                    "government",
                    "public_platform",
                    "campus",
                    "commercial_platform",
                ],
                source_type,
            ),
        ),
    )
    rows_html = []
    for r in rows:
        rows_html.append(
            [
                r["priority"] or "-",
                r["company_name"] or r["name"] or "全局来源",
                link(r["url"]),
                r["source_type"],
                r["provider"],
                r["trust_level"],
                status_form("/sources/update", r["id"], r["verification_status"], "source_id", source_statuses(), current_path(params, "/sources")),
                "是" if r["requires_browser"] else "否",
                "是" if r["enabled"] else "否",
            ]
        )
    table = table_html(["优先级", "公司/来源", "URL", "类型", "Provider", "信任", "状态", "浏览器", "启用"], rows_html)
    return filters + summary(total, page) + table + pager("/sources", params, total, page)


def render_candidates(settings: Settings, params: dict[str, list[str]]) -> str:
    status = first(params, "status") or "pending"
    q = first(params, "q")
    page = int(first(params, "page") or "1")
    offset = (page - 1) * PAGE_SIZE

    where = []
    values: list[Any] = []
    if status:
        where.append("cc.review_status = ?")
        values.append(status)
    if q:
        where.append("(cc.candidate_url LIKE ? OR cc.candidate_title LIKE ? OR c.company_name LIKE ?)")
        values.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    where_sql = " WHERE " + " AND ".join(where) if where else ""

    with connect(settings) as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM correction_candidates cc LEFT JOIN companies c ON c.id = cc.company_id{where_sql}",
            values,
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT cc.id, cc.candidate_title, cc.candidate_url, cc.candidate_source_type,
                   cc.score, cc.confidence, cc.score_reasons, cc.review_status,
                   cc.decision, c.company_name, c.priority
            FROM correction_candidates cc
            LEFT JOIN companies c ON c.id = cc.company_id
            {where_sql}
            ORDER BY cc.score DESC, cc.id
            LIMIT ? OFFSET ?
            """,
            [*values, PAGE_SIZE, offset],
        ).fetchall()

    filters = filter_bar(
        "/candidates",
        {"status": status, "q": q},
        extra="<select name=\"status\"><option value=\"\">全部状态</option>{}</select>".format(
            options(["pending", "accepted", "rejected", "needs_more_search"], status)
        ),
    )
    rows_html = []
    for r in rows:
        rows_html.append(
            [
                r["priority"] or "-",
                r["company_name"] or "-",
                r["score"],
                r["confidence"],
                r["candidate_source_type"],
                html.escape(r["candidate_title"] or ""),
                link(r["candidate_url"]),
                truncate(r["score_reasons"], 100),
                candidate_form(r["id"], current_path(params, "/candidates")),
            ]
        )
    table = table_html(["优先级", "公司", "分数", "置信", "类型", "标题", "URL", "原因", "处理"], rows_html)
    return filters + summary(total, page) + table + pager("/candidates", params, total, page)


def render_leads(settings: Settings, params: dict[str, list[str]]) -> str:
    status = first(params, "status") or "new"
    q = first(params, "q")
    page = int(first(params, "page") or "1")
    offset = (page - 1) * PAGE_SIZE

    where = []
    values: list[Any] = []
    if status:
        where.append("jl.status = ?")
        values.append(status)
    if q:
        where.append("(jl.title LIKE ? OR jl.url LIKE ? OR jl.matched_keywords LIKE ? OR c.company_name LIKE ?)")
        values.extend([f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"])
    where_sql = " WHERE " + " AND ".join(where) if where else ""

    with connect(settings) as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM job_leads jl LEFT JOIN companies c ON c.id = jl.company_id{where_sql}",
            values,
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT jl.id, jl.title, jl.url, jl.source_type, jl.target_year,
                   jl.recruitment_type, jl.matched_keywords,
                   jl.computer_relevance_score, jl.security_relevance_score,
                   jl.trust_score, jl.overall_score, jl.status, jl.created_at,
                   c.company_name, c.priority
            FROM job_leads jl
            LEFT JOIN companies c ON c.id = jl.company_id
            {where_sql}
            ORDER BY jl.overall_score DESC, jl.created_at DESC, jl.id DESC
            LIMIT ? OFFSET ?
            """,
            [*values, PAGE_SIZE, offset],
        ).fetchall()

    filters = filter_bar(
        "/leads",
        {"status": status, "q": q},
        extra="<select name=\"status\"><option value=\"\">全部状态</option>{}</select>".format(
            options(["new", "pending_review", "confirmed", "ignored", "duplicate", "invalid", "expired"], status)
        ),
    )
    table = table_html(
        ["优先级", "公司", "总分", "安全", "计算机", "信任", "届别", "类型", "标题", "URL", "关键词", "状态", "发现时间"],
        [
            [
                r["priority"] or "-",
                r["company_name"] or "全局来源",
                r["overall_score"],
                r["security_relevance_score"],
                r["computer_relevance_score"],
                r["trust_score"],
                r["target_year"] or "-",
                r["recruitment_type"] or "-",
                html.escape(r["title"] or ""),
                link(r["url"]),
                html.escape(r["matched_keywords"] or ""),
                r["status"],
                r["created_at"],
            ]
            for r in rows
        ],
    )
    return filters + summary(total, page) + table + pager("/leads", params, total, page)


def render_search_results(settings: Settings, params: dict[str, list[str]]) -> str:
    provider = first(params, "provider")
    q = first(params, "q")
    page = int(first(params, "page") or "1")
    offset = (page - 1) * PAGE_SIZE

    where = []
    values: list[Any] = []
    if provider:
        where.append("sr.provider = ?")
        values.append(provider)
    if q:
        where.append("(sr.title LIKE ? OR sr.url LIKE ? OR sr.snippet LIKE ? OR st.query LIKE ?)")
        values.extend([f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"])
    where_sql = " WHERE " + " AND ".join(where) if where else ""

    with connect(settings) as conn:
        total = conn.execute(
            f"SELECT COUNT(*) FROM search_results sr LEFT JOIN search_tasks st ON st.id = sr.task_id{where_sql}",
            values,
        ).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT sr.id, sr.provider, sr.rank, sr.title, sr.url, sr.snippet,
                   st.query, st.reason, c.company_name, c.priority
            FROM search_results sr
            LEFT JOIN search_tasks st ON st.id = sr.task_id
            LEFT JOIN companies c ON c.id = sr.company_id
            {where_sql}
            ORDER BY sr.created_at DESC, sr.id DESC
            LIMIT ? OFFSET ?
            """,
            [*values, PAGE_SIZE, offset],
        ).fetchall()

    filters = filter_bar(
        "/search-results",
        {"provider": provider, "q": q},
        extra="<select name=\"provider\"><option value=\"\">全部 Provider</option>{}</select>".format(
            options(["baidu", "zhihu", "bocha"], provider)
        ),
    )
    table = table_html(
        ["ID", "Provider", "任务", "优先级", "公司", "标题", "URL", "摘要"],
        [
            [
                r["id"],
                r["provider"],
                html.escape(f"{r['reason'] or ''}: {r['query'] or ''}"),
                r["priority"] or "-",
                r["company_name"] or "表外/全局",
                html.escape(r["title"] or ""),
                link(r["url"]),
                truncate(r["snippet"], 120),
            ]
            for r in rows
        ],
    )
    return filters + summary(total, page) + table + pager("/search-results", params, total, page)


def render_discovered_companies(settings: Settings, params: dict[str, list[str]]) -> str:
    status = first(params, "status") or "pending"
    q = first(params, "q")
    page = int(first(params, "page") or "1")
    offset = (page - 1) * PAGE_SIZE

    where = []
    values: list[Any] = []
    if status:
        where.append("review_status = ?")
        values.append(status)
    if q:
        where.append("(company_name LIKE ? OR evidence_title LIKE ? OR evidence_snippet LIKE ?)")
        values.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    where_sql = " WHERE " + " AND ".join(where) if where else ""

    with connect(settings) as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM discovered_companies{where_sql}", values).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT id, company_name, matched_location, matched_ownership,
                   matched_direction, evidence_url, evidence_title, score,
                   review_status, created_at
            FROM discovered_companies
            {where_sql}
            ORDER BY score DESC, created_at DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [*values, PAGE_SIZE, offset],
        ).fetchall()

    filters = filter_bar(
        "/discovered-companies",
        {"status": status, "q": q},
        extra="<select name=\"status\"><option value=\"\">全部状态</option>{}</select>".format(
            options(["pending", "accepted", "ignored", "needs_more_search"], status)
        ),
    )
    table = table_html(
        ["ID", "候选企业", "分数", "区域", "性质", "方向", "证据标题", "URL", "状态", "发现时间"],
        [
            [
                r["id"],
                html.escape(r["company_name"] or ""),
                r["score"],
                html.escape(r["matched_location"] or ""),
                html.escape(r["matched_ownership"] or ""),
                html.escape(r["matched_direction"] or ""),
                html.escape(r["evidence_title"] or ""),
                link(r["evidence_url"]),
                r["review_status"],
                r["created_at"],
            ]
            for r in rows
        ],
    )
    return filters + summary(total, page) + table + pager("/discovered-companies", params, total, page)


def update_candidate(settings: Settings, form: dict[str, str]) -> None:
    candidate_id = int(form["candidate_id"])
    decision = form.get("decision", "")
    if decision == "reject":
        review_status = "rejected"
    elif decision == "needs_more_search":
        review_status = "needs_more_search"
    else:
        review_status = "accepted"
    with connect(settings) as conn:
        candidate = conn.execute(
            """
            SELECT cc.id, cc.company_id, cc.candidate_url, cc.candidate_title,
                   cc.candidate_source_type, cc.score, cc.score_reasons,
                   c.company_name
            FROM correction_candidates cc
            LEFT JOIN companies c ON c.id = cc.company_id
            WHERE cc.id = ?
            """,
            (candidate_id,),
        ).fetchone()
        if candidate is None:
            raise ValueError(f"Candidate not found: {candidate_id}")
        conn.execute(
            """
            UPDATE correction_candidates
            SET review_status = ?, decision = ?, review_notes = ?, reviewed_at = CURRENT_TIMESTAMP,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (review_status, decision, form.get("review_notes", ""), candidate_id),
        )
        if review_status == "accepted":
            upsert_source_from_candidate(conn, candidate, decision, form.get("review_notes", ""))
        conn.commit()


def upsert_source_from_candidate(
    conn: sqlite3.Connection,
    candidate: sqlite3.Row,
    decision: str,
    review_notes: str,
) -> None:
    mapping = {
        "accept_official": ("official_or_unknown", "verified_official", 90, 1),
        "accept_recruitment": ("official_recruitment", "verified_recruitment", 88, 1),
        "accept_government": ("government", "verified_government", 90, 1),
        "accept_platform": ("public_platform", "verified_platform", 75, 1),
        "accept_reference": ("search_reference", "candidate", 45, 0),
    }
    source_type, verification_status, trust_level, enabled = mapping.get(
        decision,
        ("search", "candidate", 50, 0),
    )
    company_id = int(candidate["company_id"])
    url = candidate["candidate_url"]
    existing = conn.execute(
        "SELECT id FROM sources WHERE company_id = ? AND url = ?",
        (company_id, url),
    ).fetchone()
    notes = "\n".join(
        item
        for item in [
            f"Accepted from correction candidate #{candidate['id']}.",
            f"Decision: {decision}.",
            f"Score: {candidate['score']}.",
            f"Reasons: {candidate['score_reasons'] or ''}",
            f"Review notes: {review_notes}" if review_notes else "",
        ]
        if item
    )
    if existing:
        conn.execute(
            """
            UPDATE sources
            SET name = ?, source_type = ?, provider = 'correction_candidate',
                trust_level = ?, verification_status = ?, enabled = ?,
                discovered_by = 'review', notes = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                candidate["candidate_title"] or candidate["company_name"] or "修正候选来源",
                source_type,
                trust_level,
                verification_status,
                enabled,
                notes,
                int(existing["id"]),
            ),
        )
        return

    source_key = make_review_source_key(company_id, url)
    conn.execute(
        """
        INSERT INTO sources (
            company_id, source_key, name, url, original_url, source_type,
            provider, trust_level, verification_status, requires_browser,
            enabled, discovered_by, notes, updated_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, 'correction_candidate', ?, ?, 0,
            ?, 'review', ?, CURRENT_TIMESTAMP
        )
        """,
        (
            company_id,
            source_key,
            candidate["candidate_title"] or candidate["company_name"] or "修正候选来源",
            url,
            url,
            source_type,
            trust_level,
            verification_status,
            enabled,
            notes,
        ),
    )


def make_review_source_key(company_id: int, url: str) -> str:
    digest = hashlib.sha1(f"{company_id}|{url}".encode("utf-8")).hexdigest()[:16]
    return f"review:{company_id}:{digest}"


def update_source(settings: Settings, form: dict[str, str]) -> None:
    source_id = int(form["source_id"])
    status = form.get("status", "candidate")
    with connect(settings) as conn:
        conn.execute(
            "UPDATE sources SET verification_status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (status, source_id),
        )
        conn.commit()


def update_job(settings: Settings, form: dict[str, str]) -> None:
    with connect(settings) as conn:
        conn.execute(
            "UPDATE job_events SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (form.get("status", "pending_review"), int(form["job_event_id"])),
        )
        conn.commit()


def save_application(settings: Settings, form: dict[str, str]) -> None:
    with connect(settings) as conn:
        conn.execute(
            "UPDATE applications SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (form.get("status", "undecided"), int(form["application_id"])),
        )
        conn.commit()


def update_review(settings: Settings, form: dict[str, str]) -> None:
    status = form.get("status", "pending")
    with connect(settings) as conn:
        conn.execute(
            """UPDATE review_tasks SET status = ?, resolution = ?,
                      resolved_at = CASE WHEN ? IN ('resolved', 'ignored') THEN CURRENT_TIMESTAMP ELSE NULL END,
                      updated_at = CURRENT_TIMESTAMP WHERE id = ?""",
            (status, form.get("resolution", ""), status, int(form["review_task_id"])),
        )
        conn.commit()


def render(handler: BaseHTTPRequestHandler, title: str, body: str) -> None:
    content = layout(title, body).encode("utf-8")
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Content-Length", str(len(content)))
    handler.end_headers()
    handler.wfile.write(content)


def layout(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} - Job Watcher</title>
  <style>
    body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; color: #1f2933; background: #f7f8fa; }}
    header {{ background: #152238; color: white; padding: 14px 22px; }}
    header h1 {{ margin: 0; font-size: 18px; }}
    nav {{ display: flex; gap: 10px; padding: 10px 22px; background: white; border-bottom: 1px solid #d8dee8; }}
    nav a {{ color: #1d4ed8; text-decoration: none; font-size: 14px; }}
    main {{ padding: 18px 22px; }}
    form.filter {{ display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap; }}
    input, select, button {{ font-size: 14px; padding: 6px 8px; border: 1px solid #c6ccd6; border-radius: 4px; background: white; }}
    button {{ background: #1d4ed8; color: white; border-color: #1d4ed8; cursor: pointer; }}
    table {{ width: 100%; border-collapse: collapse; background: white; font-size: 13px; }}
    th, td {{ border: 1px solid #d8dee8; padding: 7px 8px; vertical-align: top; }}
    th {{ background: #eef2f7; text-align: left; position: sticky; top: 0; }}
    .summary {{ margin: 8px 0 12px; color: #52606d; font-size: 13px; }}
    .pager {{ margin-top: 12px; display: flex; gap: 12px; }}
    .inline {{ display: inline-flex; gap: 5px; align-items: center; }}
    .url {{ max-width: 360px; word-break: break-all; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin-bottom: 18px; }}
    .card {{ background: white; border: 1px solid #d8dee8; padding: 14px; border-radius: 6px; }}
    .card strong {{ display: block; font-size: 26px; margin-bottom: 4px; }}
    .card span {{ color: #52606d; font-size: 13px; }}
  </style>
</head>
<body>
  <header><h1>秋招雷达 · Qingdao Job Radar</h1></header>
  <nav>
    <a href="/radar">今日雷达</a>
    <a href="/jobs">招聘事件</a>
    <a href="/applications">投递进度</a>
    <a href="/reviews">人工核验</a>
    <a href="/companies">企业库</a>
    <a href="/coverage">覆盖中心</a>
    <a href="/sources">来源管理</a>
    <a href="/sources?status=verified_official">已确认官网</a>
    <a href="/sources?status=verified_recruitment">已确认招聘</a>
    <a href="/candidates">修正候选</a>
    <a href="/leads">招聘线索</a>
    <a href="/search-results">搜索发现</a>
    <a href="/discovered-companies">表外企业</a>
    <a href="/health">Health</a>
  </nav>
  <main>
    <h2>{html.escape(title)}</h2>
    {body}
  </main>
</body>
</html>"""


def filter_bar(action: str, params: dict[str, str], extra: str = "") -> str:
    q = html.escape(params.get("q") or "")
    return f"""<form class="filter" method="get" action="{action}">
      <input type="search" name="q" value="{q}" placeholder="搜索公司、URL、方向">
      {extra}
      <button type="submit">筛选</button>
    </form>"""


def table_html(headers: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body_rows = []
    for row in rows:
        body_rows.append("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>")
    return "<table><thead><tr>" + head + "</tr></thead><tbody>" + "".join(body_rows) + "</tbody></table>"


def options(values: list[str], selected: str) -> str:
    return "".join(
        f'<option value="{html.escape(value)}"{" selected" if value == selected else ""}>{html.escape(value)}</option>'
        for value in values
    )


def job_status_form(job_event_id: int, status: str, next_path: str) -> str:
    return f'''<form class="inline" method="post" action="/jobs/update">
      <input type="hidden" name="job_event_id" value="{job_event_id}">
      <input type="hidden" name="next" value="{html.escape(next_path)}">
      <select name="status">{options(["pending_review", "open", "closing_soon", "closed", "invalid"], status)}</select>
      <button type="submit">保存</button></form>'''


def application_statuses() -> list[str]:
    return ["undecided", "preparing", "applied", "written_test", "interview", "waiting", "offer", "rejected", "abandoned"]


def application_form(application_id: int, status: str, next_path: str) -> str:
    return f'''<form class="inline" method="post" action="/applications/save">
      <input type="hidden" name="application_id" value="{application_id}">
      <input type="hidden" name="next" value="{html.escape(next_path)}">
      <select name="status">{options(application_statuses(), status)}</select>
      <button type="submit">保存</button></form>'''


def review_form(review_task_id: int, status: str, next_path: str) -> str:
    return f'''<form class="inline" method="post" action="/reviews/update">
      <input type="hidden" name="review_task_id" value="{review_task_id}">
      <input type="hidden" name="next" value="{html.escape(next_path)}">
      <select name="status">{options(["pending", "in_progress", "resolved", "ignored"], status)}</select>
      <input name="resolution" placeholder="处理结论">
      <button type="submit">保存</button></form>'''


def summary(total: int, page: int) -> str:
    return f'<div class="summary">共 {total} 条，当前第 {page} 页，每页 {PAGE_SIZE} 条。</div>'


def pager(base: str, params: dict[str, list[str]], total: int, page: int) -> str:
    links = []
    if page > 1:
        links.append(f'<a href="{html.escape(page_url(base, params, page - 1))}">上一页</a>')
    if page * PAGE_SIZE < total:
        links.append(f'<a href="{html.escape(page_url(base, params, page + 1))}">下一页</a>')
    return '<div class="pager">' + " ".join(links) + "</div>" if links else ""


def page_url(base: str, params: dict[str, list[str]], page: int) -> str:
    flat = {key: values[0] for key, values in params.items() if values and key != "page"}
    flat["page"] = str(page)
    return base + "?" + urlencode(flat)


def first(params: dict[str, list[str]], key: str) -> str:
    values = params.get(key)
    return values[0] if values else ""


def current_path(params: dict[str, list[str]], base: str) -> str:
    flat = {key: values[0] for key, values in params.items() if values}
    return base + ("?" + urlencode(flat) if flat else "")


def link(url: str) -> str:
    safe = html.escape(url or "")
    return f'<div class="url"><a href="{safe}" target="_blank" rel="noreferrer">{safe}</a></div>'


def truncate(value: str | None, length: int) -> str:
    text = value or ""
    if len(text) <= length:
        return html.escape(text)
    return html.escape(text[:length] + "...")


def status_form(action: str, item_id: int, current: str, id_name: str, statuses: list[str], next_url: str) -> str:
    return f"""<form class="inline" method="post" action="{action}">
      <input type="hidden" name="{id_name}" value="{item_id}">
      <input type="hidden" name="next" value="{html.escape(next_url)}">
      <select name="status">{options(statuses, current)}</select>
      <button type="submit">保存</button>
    </form>"""


def candidate_form(candidate_id: int, next_url: str) -> str:
    return f"""<form method="post" action="/candidates/update">
      <input type="hidden" name="candidate_id" value="{candidate_id}">
      <input type="hidden" name="next" value="{html.escape(next_url)}">
      <select name="decision">
        {options(["accept_official", "accept_recruitment", "accept_government", "accept_platform", "accept_reference", "reject", "needs_more_search"], "")}
      </select>
      <input name="review_notes" placeholder="备注">
      <button type="submit">提交</button>
    </form>"""


def source_statuses() -> list[str]:
    return [
        "candidate",
        "verified_official",
        "verified_recruitment",
        "verified_government",
        "verified_platform",
        "needs_search",
        "needs_browser",
        "invalid_replaced",
        "invalid_unresolved",
    ]


def redirect(handler: BaseHTTPRequestHandler, location: str) -> None:
    handler.send_response(HTTPStatus.SEE_OTHER)
    handler.send_header("Location", location)
    handler.end_headers()


def send_text(handler: BaseHTTPRequestHandler, text: str, status: HTTPStatus = HTTPStatus.OK) -> None:
    content = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(content)))
    handler.end_headers()
    handler.wfile.write(content)


if __name__ == "__main__":
    run_server(load_settings())
