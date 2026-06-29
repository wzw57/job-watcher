from __future__ import annotations

import argparse
import csv
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCES_CSV = ROOT / "data" / "processed" / "company_sources_seed.csv"
AUDIT_DIR = ROOT / "data" / "audit"
RESULTS_CSV = AUDIT_DIR / "source_verification_results.csv"
SUMMARY_MD = AUDIT_DIR / "source_verification_summary.md"

META_MARK = "__CURL_META__"
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def decode_bytes(data: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "gbk", "big5"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def extract_title(text: str) -> str:
    match = TITLE_RE.search(text)
    if not match:
        return ""
    title = TAG_RE.sub("", match.group(1))
    return SPACE_RE.sub(" ", title).strip()[:200]


def classify_result(http_status: str, error: str, content: str) -> str:
    if error:
        lowered = error.lower()
        if "timed out" in lowered or "timeout" in lowered:
            return "timeout"
        return "error"
    if not http_status or http_status == "000":
        return "error"
    try:
        code = int(http_status)
    except ValueError:
        return "error"
    if 200 <= code < 400:
        if looks_like_js_shell(content):
            return "needs_browser"
        return "ok"
    if code in {401, 403}:
        return "blocked"
    if code == 404:
        return "not_found"
    if code >= 500:
        return "server_error"
    return "http_error"


def looks_like_js_shell(content: str) -> bool:
    compact = SPACE_RE.sub(" ", content).strip().lower()
    if len(compact) < 800 and any(token in compact for token in ["<script", "app", "root", "vue", "react"]):
        return True
    body_text = TAG_RE.sub(" ", compact)
    body_text = SPACE_RE.sub(" ", body_text).strip()
    return len(body_text) < 80 and "<script" in compact


def verify_url(url: str, max_time: int) -> dict[str, str]:
    cmd = [
        "curl",
        "-L",
        "-sS",
        "--max-time",
        str(max_time),
        "--connect-timeout",
        "4",
        "--compressed",
        "-A",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "-r",
        "0-131071",
        "-w",
        f"\n{META_MARK}%{{http_code}}\t%{{url_effective}}\t%{{content_type}}",
        url,
    ]
    started = datetime.now(timezone.utc)
    try:
        proc = subprocess.run(cmd, capture_output=True, timeout=max_time + 3)
        text = decode_bytes(proc.stdout)
        stderr = decode_bytes(proc.stderr).strip()
    except subprocess.TimeoutExpired as exc:
        return {
            "url": url,
            "verification_status": "timeout",
            "http_status": "",
            "final_url": url,
            "content_type": "",
            "page_title": "",
            "error": f"subprocess timeout after {max_time + 3}s",
            "verified_at": started.isoformat(),
        }
    except FileNotFoundError:
        return {
            "url": url,
            "verification_status": "error",
            "http_status": "",
            "final_url": url,
            "content_type": "",
            "page_title": "",
            "error": "curl executable not found",
            "verified_at": started.isoformat(),
        }

    body, meta = text, ""
    if META_MARK in text:
        body, meta = text.rsplit(META_MARK, 1)
    parts = meta.strip().split("\t")
    http_status = parts[0] if len(parts) >= 1 else ""
    final_url = parts[1] if len(parts) >= 2 else url
    content_type = parts[2] if len(parts) >= 3 else ""
    error = stderr if proc.returncode != 0 else ""

    title = extract_title(body)
    status = classify_result(http_status, error, body)

    return {
        "url": url,
        "verification_status": status,
        "http_status": http_status,
        "final_url": final_url,
        "content_type": content_type,
        "page_title": title,
        "error": error[:300],
        "verified_at": started.isoformat(),
    }


def load_sources(priority: list[str], only_enabled: bool) -> pd.DataFrame:
    df = pd.read_csv(SOURCES_CSV)
    if priority:
        df = df[df["priority"].isin(priority)]
    if only_enabled:
        df = df[df["priority"].isin(["P0", "P1"])]
    return df.copy()


def existing_verified_urls() -> set[str]:
    if not RESULTS_CSV.exists():
        return set()
    try:
        df = pd.read_csv(RESULTS_CSV, usecols=["url"])
    except Exception:
        return set()
    return set(df["url"].dropna().astype(str))


def append_rows(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def write_summary() -> None:
    if not RESULTS_CSV.exists():
        return
    df = pd.read_csv(RESULTS_CSV)
    status_counts = df["verification_status"].value_counts(dropna=False)
    priority_counts = df["priority"].value_counts(dropna=False)
    source_counts = df["source_type"].value_counts(dropna=False)
    domain_counts = df["url"].map(lambda u: urlparse(str(u)).netloc.lower()).value_counts().head(20)

    lines = [
        "# 来源 URL 核验摘要",
        "",
        f"- 已核验记录：{len(df)} 条",
        f"- 更新时间：{datetime.now().isoformat(timespec='seconds')}",
        "",
        "## 核验状态",
        "",
        "```text",
        status_counts.to_string(),
        "```",
        "",
        "## 优先级分布",
        "",
        "```text",
        priority_counts.to_string(),
        "```",
        "",
        "## 来源类型分布",
        "",
        "```text",
        source_counts.to_string(),
        "```",
        "",
        "## 已核验域名 Top 20",
        "",
        "```text",
        domain_counts.to_string(),
        "```",
        "",
        "## 后续处理口径",
        "",
        "- `ok`：可作为可抓取候选来源，但仍需判断是否招聘相关。",
        "- `needs_browser`：普通 HTTP 只能看到 JS 外壳，应进入浏览器或专用 adapter 队列。",
        "- `blocked/timeout/error`：优先通过搜索修正，不直接删除。",
        "- `not_found`：优先搜索替代官网或招聘入口。",
    ]
    SUMMARY_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify candidate source URLs with curl.")
    parser.add_argument("--priority", nargs="*", default=["P0", "P1"], help="Priorities to verify.")
    parser.add_argument("--max", type=int, default=50, help="Maximum new unique URLs to verify.")
    parser.add_argument("--max-time", type=int, default=10, help="Per-URL curl max time in seconds.")
    parser.add_argument("--resume", action="store_true", help="Skip URLs already present in results.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not SOURCES_CSV.exists():
        print(f"Missing sources CSV: {SOURCES_CSV}", file=sys.stderr)
        return 1

    sources = load_sources(args.priority, only_enabled=False)
    seen = existing_verified_urls() if args.resume else set()

    selected_rows = []
    selected_urls = set()
    for _, row in sources.iterrows():
        url = str(row["url"])
        if url in seen or url in selected_urls:
            continue
        selected_rows.append(row)
        selected_urls.add(url)
        if len(selected_rows) >= args.max:
            break

    output_rows: list[dict[str, str]] = []
    for index, row in enumerate(selected_rows, start=1):
        url = str(row["url"])
        print(f"[{index}/{len(selected_rows)}] {url}")
        result = verify_url(url, max_time=args.max_time)
        output_rows.append(
            {
                "company_key": str(row["company_key"]),
                "company_name": str(row["company_name"]),
                "priority": str(row["priority"]),
                "source_index": str(row["source_index"]),
                "source_type": str(row["source_type"]),
                "url_notes": str(row["url_notes"]),
                **result,
            }
        )
        append_rows(RESULTS_CSV, [output_rows[-1]])

    write_summary()
    print(f"verified new urls: {len(output_rows)}")
    print(f"results: {RESULTS_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
