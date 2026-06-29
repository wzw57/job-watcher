from __future__ import annotations

import csv
import hashlib
import argparse
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
AUDIT_DIR = DATA_DIR / "audit"
PROCESSED_DIR = DATA_DIR / "processed"
EXCEL_PATH = ROOT / "青岛国企.xlsx"


URL_RE = re.compile(r"https?://[^\s，,；;]+", re.IGNORECASE)
PRIORITY_RE = re.compile(r"P[0-4]")


def clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def normalize_priority(value: str) -> str:
    match = PRIORITY_RE.search(value)
    return match.group(0) if match else ""


def split_urls(value: str) -> list[str]:
    urls = URL_RE.findall(value or "")
    normalized: list[str] = []
    seen: set[str] = set()
    for url in urls:
        url = url.strip().rstrip("。).）]")
        if url not in seen:
            normalized.append(url)
            seen.add(url)
    return normalized


def infer_source_type(url: str, notes: str) -> str:
    host = urlparse(url).netloc.lower()
    text = f"{url} {notes}".lower()
    if any(key in host for key in ["gov.cn", "qingdao.gov.cn", "hrss.qingdao.gov.cn"]):
        return "government"
    if "iguopin.com" in host:
        return "public_platform"
    if any(key in host for key in ["51job.com", "zhaopin.com", "liepin.com", "bosszhipin.com"]):
        return "commercial_platform"
    if any(key in text for key in ["hotjob", "campus", "zhaopin", "jobs", "recruit"]):
        return "official_recruitment"
    return "official_or_unknown"


@dataclass(frozen=True)
class UrlCheck:
    url: str
    ok: bool
    status: str
    final_url: str
    error: str


def check_url(url: str, timeout: int = 6) -> UrlCheck:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126 Safari/537.36"
        )
    }
    for method in ("HEAD", "GET"):
        try:
            req = Request(url, headers=headers, method=method)
            with urlopen(req, timeout=timeout) as resp:
                code = getattr(resp, "status", resp.getcode())
                final_url = resp.geturl()
                return UrlCheck(url, 200 <= code < 400, str(code), final_url, "")
        except HTTPError as exc:
            if method == "HEAD" and exc.code in {403, 405, 501}:
                continue
            return UrlCheck(url, 200 <= exc.code < 400, str(exc.code), url, str(exc.reason))
        except (URLError, TimeoutError, OSError) as exc:
            if method == "HEAD":
                continue
            return UrlCheck(url, False, "", url, type(exc).__name__ + ": " + str(exc)[:180])
    return UrlCheck(url, False, "", url, "unknown error")


def load_companies() -> pd.DataFrame:
    xls = pd.ExcelFile(EXCEL_PATH)
    sheet_name = "主体公司" if "主体公司" in xls.sheet_names else xls.sheet_names[1]
    raw = pd.read_excel(EXCEL_PATH, sheet_name=sheet_name)
    raw.columns = [clean_text(c) for c in raw.columns]
    return raw


def make_clean_companies(raw: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, str]]]:
    rows: list[dict[str, object]] = []
    issues: list[dict[str, str]] = []

    for idx, row in raw.iterrows():
        row_no = idx + 2
        group_name = clean_text(row.get("归属集团"))
        company_name = clean_text(row.get("主体公司/机构"))
        entity_type = clean_text(row.get("层级/性质"))
        region = clean_text(row.get("区域"))
        priority_raw = clean_text(row.get("优先级"))
        priority = normalize_priority(priority_raw)
        difficulty = clean_text(row.get("应聘难度"))
        education_barrier = clean_text(row.get("是否卡学历"))
        directions = clean_text(row.get("推荐岗位/方向"))
        action_status = clean_text(row.get("状态/动作"))
        urls_raw = clean_text(row.get("URL（官网/招聘入口）"))
        url_notes = clean_text(row.get("URL校准/备注"))
        urls = split_urls(urls_raw)

        if not group_name:
            issues.append({"row_no": str(row_no), "severity": "high", "field": "归属集团", "issue": "缺失归属集团"})
        if not company_name:
            issues.append({"row_no": str(row_no), "severity": "high", "field": "主体公司/机构", "issue": "缺失主体公司/机构"})
        if not priority:
            issues.append({"row_no": str(row_no), "severity": "medium", "field": "优先级", "issue": f"无法解析优先级：{priority_raw}"})
        if not urls:
            issues.append({"row_no": str(row_no), "severity": "medium", "field": "URL（官网/招聘入口）", "issue": "未识别到 URL"})

        normalized_name = re.sub(r"[（）()\\s]", "", company_name)
        stable_key = hashlib.sha1(f"{group_name}|{company_name}".encode("utf-8")).hexdigest()[:12]

        rows.append(
            {
                "company_key": stable_key,
                "source_row": row_no,
                "group_name": group_name,
                "company_name": company_name,
                "normalized_name": normalized_name,
                "entity_type": entity_type,
                "region": region,
                "priority_raw": priority_raw,
                "priority": priority,
                "difficulty": difficulty,
                "education_barrier": education_barrier,
                "recommended_directions": directions,
                "action_status": action_status,
                "source_urls": "\n".join(urls),
                "url_count": len(urls),
                "url_notes": url_notes,
                "enabled": priority in {"P0", "P1"},
            }
        )

    clean = pd.DataFrame(rows)

    duplicated_names = clean[clean.duplicated(["normalized_name"], keep=False)].sort_values("normalized_name")
    for _, row in duplicated_names.iterrows():
        issues.append(
            {
                "row_no": str(row["source_row"]),
                "severity": "medium",
                "field": "主体公司/机构",
                "issue": f"疑似重复主体：{row['company_name']}",
            }
        )

    return clean, issues


def iter_source_rows(clean: pd.DataFrame) -> Iterable[dict[str, object]]:
    for _, row in clean.iterrows():
        urls = str(row["source_urls"]).splitlines() if row["source_urls"] else []
        for index, url in enumerate(urls, start=1):
            yield {
                "company_key": row["company_key"],
                "company_name": row["company_name"],
                "priority": row["priority"],
                "enabled": row["enabled"],
                "source_index": index,
                "url": url,
                "source_type": infer_source_type(url, str(row["url_notes"])),
                "url_notes": row["url_notes"],
            }


def check_urls(source_rows: list[dict[str, object]], max_urls: int = 120) -> pd.DataFrame:
    priority_urls = sorted(
        {
            str(row["url"])
            for row in source_rows
            if row.get("url") and bool(row.get("enabled"))
        }
    )
    unique_urls = priority_urls[:max_urls]
    checks: dict[str, UrlCheck] = {}
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(check_url, url): url for url in unique_urls}
        for future in as_completed(futures):
            result = future.result()
            checks[result.url] = result
            time.sleep(0.05)

    rows: list[dict[str, object]] = []
    for row in source_rows:
        result = checks.get(str(row["url"]))
        rows.append(
            {
                **row,
                "url_checked": result is not None,
                "url_ok": result.ok if result else False,
                "http_status": result.status if result else "",
                "final_url": result.final_url if result else "",
                "url_error": result.error if result else "not checked in this audit run",
            }
        )
    return pd.DataFrame(rows)


def write_report(clean: pd.DataFrame, sources: pd.DataFrame, issues: list[dict[str, str]]) -> None:
    priority_counts = clean["priority_raw"].value_counts(dropna=False)
    normalized_priority_counts = clean["priority"].value_counts(dropna=False)
    source_type_counts = sources["source_type"].value_counts(dropna=False)
    url_checked_counts = sources["url_checked"].value_counts(dropna=False)
    url_ok_counts = sources.loc[sources["url_checked"], "url_ok"].value_counts(dropna=False)
    enabled_count = int(clean["enabled"].sum())
    duplicate_count = int(clean.duplicated(["normalized_name"], keep=False).sum())

    issue_df = pd.DataFrame(issues)
    high_issues = int((issue_df["severity"] == "high").sum()) if not issue_df.empty else 0
    medium_issues = int((issue_df["severity"] == "medium").sum()) if not issue_df.empty else 0

    lines = [
        "# 青岛国企企业表数据审计报告",
        "",
        "## 审计范围",
        "",
        f"- 原始文件：`{EXCEL_PATH.name}`",
        "- 原始 sheet：`主体公司`",
        f"- 企业记录：{len(clean)} 条",
        f"- 拆分 URL 来源：{len(sources)} 条",
        f"- 第一版默认启用 P0/P1 企业：{enabled_count} 条",
        "",
        "## 优先级分布",
        "",
        "原始优先级：",
        "",
        "```text",
        priority_counts.to_string(),
        "```",
        "",
        "标准化优先级：",
        "",
        "```text",
        normalized_priority_counts.to_string(),
        "```",
        "",
        "## URL 来源类型",
        "",
        "```text",
        source_type_counts.to_string(),
        "```",
        "",
        "## URL 可访问性",
        "",
        "检测范围：本轮只检测默认启用企业（P0/P1）的部分唯一 URL，避免首次审计耗时过长。",
        "",
        "URL 是否检测：",
        "",
        "```text",
        url_checked_counts.to_string(),
        "```",
        "",
        "已检测 URL 可访问性：",
        "",
        "```text",
        url_ok_counts.to_string(),
        "```",
        "",
        "说明：URL 检测只代表本次 HTTP 访问结果。部分站点会拦截 HEAD/GET、限制海外 VPS 或临时超时，不能直接等同于 URL 错误。",
        "",
        "## 数据问题摘要",
        "",
        f"- 高优先级问题：{high_issues} 条",
        f"- 中优先级问题：{medium_issues} 条",
        f"- 疑似重复主体记录：{duplicate_count} 条",
        "",
        "详细问题见：`data/audit/company_cleaning_issues.csv`",
        "",
        "## 本轮清洗产物",
        "",
        "- `data/processed/companies_seed.csv`：企业主数据种子表",
        "- `data/processed/company_sources_seed.csv`：企业 URL 来源种子表",
        "- `data/audit/company_cleaning_issues.csv`：字段和重复问题清单",
        "- `data/audit/url_check_results.csv`：URL 检测结果",
        "",
        "## 建议",
        "",
        "1. 第一版只默认启用 P0/P1 企业，避免抓取范围过大。",
        "2. URL 不可访问的记录先标记为待复核，不直接删除。",
        "3. 对疑似重复主体保留原记录，后续在看板里做合并或别名关系。",
        "4. 对 official_or_unknown 类型来源，后续应进一步标注官网、招聘页、第三方汇总或工商线索。",
    ]
    (AUDIT_DIR / "company_data_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit and normalize the Qingdao SOE company workbook.")
    parser.add_argument("--max-urls", type=int, default=120, help="Maximum unique enabled URLs to check.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    if not EXCEL_PATH.exists():
        print(f"Excel file not found: {EXCEL_PATH}", file=sys.stderr)
        return 1

    raw = load_companies()
    clean, issues = make_clean_companies(raw)
    source_rows = list(iter_source_rows(clean))
    sources = pd.DataFrame(source_rows)
    checked_sources = check_urls(source_rows, max_urls=args.max_urls)

    clean.to_csv(PROCESSED_DIR / "companies_seed.csv", index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
    sources.to_csv(PROCESSED_DIR / "company_sources_seed.csv", index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)
    pd.DataFrame(issues).to_csv(AUDIT_DIR / "company_cleaning_issues.csv", index=False, encoding="utf-8-sig")
    checked_sources.to_csv(AUDIT_DIR / "url_check_results.csv", index=False, encoding="utf-8-sig")
    write_report(clean, checked_sources, issues)

    print(f"companies: {len(clean)}")
    print(f"sources: {len(sources)}")
    print(f"issues: {len(issues)}")
    print(f"url ok: {int(checked_sources['url_ok'].sum())}/{len(checked_sources)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
