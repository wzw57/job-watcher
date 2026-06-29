from __future__ import annotations

import csv
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
VERIFICATION_CSV = ROOT / "data" / "audit" / "source_verification_results.csv"
QUEUE_CSV = ROOT / "data" / "audit" / "source_correction_queue.csv"

NON_AUTHORITATIVE_DOMAINS = {
    "www.qcc.com": "工商/商业查询页，不适合作为招聘监控源",
    "railway.fandom.com": "百科页面，不适合作为招聘监控源",
    "www.xinpianbang.com": "品牌/媒体页面，不适合作为招聘监控源",
    "www.etmoc.com": "行业信息页，需要核实是否官方",
    "jn.bendibao.com": "本地宝聚合页，只能作线索",
    "www.gaoxiaojob.com": "聚合公告页，只能作线索",
    "www.bianzhia.com": "聚合公告页，只能作线索",
}


def build_queries(company_name: str) -> list[str]:
    base = [
        f"{company_name} 官网",
        f"{company_name} 招聘",
        f"{company_name} 校园招聘",
        f"{company_name} 2027届 校园招聘",
        f"{company_name} 网申",
        f"{company_name} 国聘",
        f"{company_name} 网络安全 招聘",
        f"{company_name} 信息安全 招聘",
        f"{company_name} 青岛 招聘",
    ]
    return base


def infer_action(row: pd.Series) -> tuple[str, str]:
    status = str(row.get("verification_status", ""))
    domain = urlparse(str(row.get("url", ""))).netloc.lower()
    source_type = str(row.get("source_type", ""))

    if domain in NON_AUTHORITATIVE_DOMAINS:
        return "search_official_replacement", NON_AUTHORITATIVE_DOMAINS[domain]
    if status in {"timeout", "error", "not_found", "server_error", "http_error"}:
        return "search_replacement_or_retry", f"URL 核验状态为 {status}，需要重试并检索替代来源"
    if status == "blocked":
        return "search_replacement_or_browser_check", "站点阻止自动访问，需浏览器核验或搜索替代来源"
    if status == "needs_browser":
        return "browser_check", "普通 HTTP 只看到 JS 外壳，需浏览器或专用 adapter"
    if source_type in {"commercial_platform"}:
        return "search_official_confirmation", "商业平台只作线索，需要找官方或政府来源确认"
    return "review_recruitment_relevance", "URL 可访问，但仍需确认是否为招聘相关来源"


def main() -> int:
    if not VERIFICATION_CSV.exists():
        raise SystemExit(f"Missing verification results: {VERIFICATION_CSV}")

    df = pd.read_csv(VERIFICATION_CSV)
    rows: list[dict[str, str]] = []
    for _, row in df.iterrows():
        action, reason = infer_action(row)
        queries = build_queries(str(row["company_name"]))
        rows.append(
            {
                "company_key": row["company_key"],
                "company_name": row["company_name"],
                "priority": row["priority"],
                "original_url": row["url"],
                "verification_status": row["verification_status"],
                "http_status": row.get("http_status", ""),
                "page_title": row.get("page_title", ""),
                "recommended_action": action,
                "reason": reason,
                "query_1": queries[0],
                "query_2": queries[1],
                "query_3": queries[2],
                "query_4": queries[3],
                "query_5": queries[4],
                "review_status": "pending",
            }
        )

    QUEUE_CSV.parent.mkdir(parents=True, exist_ok=True)
    with QUEUE_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"correction queue rows: {len(rows)}")
    print(f"output: {QUEUE_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
