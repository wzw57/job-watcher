from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from dataclasses import replace
from pathlib import Path
from typing import Any

from job_watcher.config import load_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="job-watcher")
    subparsers = parser.add_subparsers(dest="command", required=True)

    config_parser = subparsers.add_parser("config-check", help="Load settings and print a safe summary.")
    config_parser.add_argument("--settings", default="", help="Optional settings YAML path.")

    db_parser = subparsers.add_parser("db-init", help="Initialize the SQLite database schema.")
    db_parser.add_argument("--settings", default="", help="Optional settings YAML path.")

    import_parser = subparsers.add_parser("import-seed", help="Import cleaned seed data into SQLite.")
    import_parser.add_argument("--settings", default="", help="Optional settings YAML path.")

    candidate_parser = subparsers.add_parser("import-candidates", help="Import correction candidates into SQLite.")
    candidate_parser.add_argument("--settings", default="", help="Optional settings YAML path.")

    web_parser = subparsers.add_parser("web", help="Run the local web dashboard.")
    web_parser.add_argument("--settings", default="", help="Optional settings YAML path.")
    web_parser.add_argument("--host", default="", help="Override web host.")
    web_parser.add_argument("--port", type=int, default=0, help="Override web port.")

    coverage_parser = subparsers.add_parser("coverage", help="Print verified source coverage summary.")
    coverage_parser.add_argument("--settings", default="", help="Optional settings YAML path.")

    auto_confirm_parser = subparsers.add_parser(
        "auto-confirm-sources",
        help="Conservatively promote low-risk candidate sources to verified sources.",
    )
    auto_confirm_parser.add_argument("--settings", default="", help="Optional settings YAML path.")

    crawl_parser = subparsers.add_parser("crawl-once", help="Fetch verified sources once and generate job leads.")
    crawl_parser.add_argument("--settings", default="", help="Optional settings YAML path.")
    crawl_parser.add_argument("--limit", type=int, default=20, help="Maximum sources to fetch.")
    crawl_parser.add_argument("--timeout", type=int, default=0, help="Temporary crawler timeout override in seconds.")

    args = parser.parse_args(argv)
    if args.command == "config-check":
        return config_check(args.settings or None)
    if args.command == "db-init":
        return db_init(args.settings or None)
    if args.command == "import-seed":
        return import_seed(args.settings or None)
    if args.command == "import-candidates":
        return import_candidates(args.settings or None)
    if args.command == "web":
        return run_web(args.settings or None, args.host or None, args.port or None)
    if args.command == "coverage":
        return print_coverage(args.settings or None)
    if args.command == "auto-confirm-sources":
        return auto_confirm_sources(args.settings or None)
    if args.command == "crawl-once":
        return crawl_once(args.settings or None, args.limit, args.timeout or None)
    parser.error(f"Unknown command: {args.command}")
    return 2


def config_check(settings_path: str | None) -> int:
    settings = load_settings(settings_path)
    summary = {
        "app": asdict(settings.app),
        "paths": {
            "data_dir": str(settings.paths.data_dir),
            "database_path": str(settings.paths.database_path),
            "snapshots_dir": str(settings.paths.snapshots_dir),
        },
        "database": asdict(settings.database),
        "crawler": asdict(settings.crawler),
        "search": {
            "default_count": settings.search.default_count,
            "zhihu_enabled": settings.search.zhihu.enabled,
            "zhihu_key_present": bool(settings.search.zhihu_api_key),
            "zhihu_resolve_ip_present": bool(settings.search.zhihu_resolve_ip),
            "baidu_enabled": settings.search.baidu.enabled,
            "baidu_key_present": bool(settings.search.baidu_api_key),
            "baidu_resolve_ip_present": bool(settings.search.baidu_resolve_ip),
            "bocha_enabled": settings.search.bocha.enabled,
            "bocha_key_present": bool(settings.search.bocha_api_key),
        },
        "web": asdict(settings.web),
        "feishu": {
            "enabled": settings.feishu.enabled,
            "webhook_present": bool(settings.feishu.webhook_url),
        },
        "priority_scope": list(settings.priority_scope),
    }
    print(json.dumps(make_json_safe(summary), ensure_ascii=False, indent=2))
    return 0


def db_init(settings_path: str | None) -> int:
    from job_watcher.storage.db import init_db

    settings = load_settings(settings_path)
    init_db(settings)
    print(f"initialized database: {settings.paths.database_path}")
    return 0


def import_seed(settings_path: str | None) -> int:
    from job_watcher.importers.seed_importer import import_all_seed_data

    settings = load_settings(settings_path)
    result = import_all_seed_data(settings)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"database: {settings.paths.database_path}")
    return 0


def import_candidates(settings_path: str | None) -> int:
    from job_watcher.importers.seed_importer import import_correction_candidates

    settings = load_settings(settings_path)
    count = import_correction_candidates(settings)
    print(json.dumps({"correction_candidates": count}, ensure_ascii=False, indent=2))
    print(f"database: {settings.paths.database_path}")
    return 0


def run_web(settings_path: str | None, host: str | None, port: int | None) -> int:
    from job_watcher.web.simple_app import run_server

    settings = load_settings(settings_path)
    if host or port:
        settings = replace(
            settings,
            web=replace(
                settings.web,
                host=host or settings.web.host,
                port=port or settings.web.port,
            ),
        )
    run_server(settings)
    return 0


def print_coverage(settings_path: str | None) -> int:
    from job_watcher.reporting.coverage import coverage_by_priority, coverage_summary
    from job_watcher.storage.db import connect

    settings = load_settings(settings_path)
    with connect(settings) as conn:
        summary = coverage_summary(conn, tuple(settings.priority_scope))
        by_priority = coverage_by_priority(conn)
    payload = {
        "scope": list(settings.priority_scope),
        "summary": {
            "total_companies": summary.total_companies,
            "with_verified_source": summary.with_verified_source,
            "verified_rate": round(summary.verified_rate, 4),
            "with_recruitment_source": summary.with_recruitment_source,
            "recruitment_rate": round(summary.recruitment_rate, 4),
            "with_candidate_only": summary.with_candidate_only,
            "without_sources": summary.without_sources,
            "with_needs_search": summary.with_needs_search,
            "with_needs_browser": summary.with_needs_browser,
        },
        "by_priority": [dict(row) for row in by_priority],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def auto_confirm_sources(settings_path: str | None) -> int:
    from job_watcher.storage.db import connect
    from job_watcher.verification.auto_confirm import conservative_auto_confirm

    settings = load_settings(settings_path)
    with connect(settings) as conn:
        result = conservative_auto_confirm(conn)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    print(
        "auto-confirmed only government, public platform, campus, and explicit recruitment sources; "
        "official_or_unknown still requires manual review."
    )
    return 0


def crawl_once(settings_path: str | None, limit: int, timeout: int | None) -> int:
    from job_watcher.crawler.runner import run_crawl_once
    from job_watcher.storage.db import connect

    settings = load_settings(settings_path)
    if timeout:
        settings = replace(settings, crawler=replace(settings.crawler, timeout_seconds=timeout))
    with connect(settings) as conn:
        result = run_crawl_once(conn, settings, limit=limit, priority_scope=tuple(settings.priority_scope))
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    print(f"database: {settings.paths.database_path}")
    print(f"snapshots: {settings.paths.snapshots_dir}")
    return 0


def make_json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return make_json_safe(asdict(value))
    if isinstance(value, dict):
        return {key: make_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [make_json_safe(item) for item in value]
    return value


if __name__ == "__main__":
    raise SystemExit(main())
