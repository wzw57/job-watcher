from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse


OFFICIAL_HINTS = [
    "官网",
    "官方网站",
    "集团",
    "有限公司",
    "股份有限公司",
    "关于我们",
]

RECRUITMENT_HINTS = [
    "招聘",
    "校园招聘",
    "校招",
    "社会招聘",
    "人才招聘",
    "网申",
    "职位",
    "岗位",
    "应届生",
    "2027届",
    "2027 届",
    "秋招",
]

GOVERNMENT_DOMAINS = [
    "gov.cn",
    "qingdao.gov.cn",
    "hrss.qingdao.gov.cn",
    "jimo.gov.cn",
    "xihaian.gov.cn",
]

PUBLIC_PLATFORM_DOMAINS = [
    "iguopin.com",
]

RECRUITMENT_PLATFORM_DOMAINS = [
    "hotjob.cn",
    "chinasyks.org.cn",
    "51job.com",
    "zhaopin.com",
    "liepin.com",
    "yingjiesheng.com",
]

LOW_AUTHORITY_DOMAINS = [
    "qcc.com",
    "fandom.com",
    "bendibao.com",
    "xinpianbang.com",
    "gaoxiaojob.com",
    "bianzhia.com",
    "jobui.com",
    "shuidi.cn",
    "jrzp.com",
    "quickjob.cn",
    "coovee.com",
    "zhipin.com",
    "gwy.com",
    "sohu.com",
    "163.com",
    "qq.com",
]

SECURITY_HINTS = [
    "网络安全",
    "信息安全",
    "数据安全",
    "等保",
    "安全运营",
    "应急响应",
    "漏洞",
    "攻防",
    "密码",
    "信创安全",
]

COMPUTER_HINTS = [
    "软件",
    "计算机",
    "信息技术",
    "信息化",
    "数字化",
    "系统",
    "运维",
    "数据",
    "云计算",
    "网络",
]


@dataclass(frozen=True)
class CandidateScore:
    score: int
    source_type: str
    confidence: str
    reasons: list[str]


def compact_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def domain_of(url: str) -> str:
    return urlparse(url).netloc.lower()


def contains_any(text: str, words: list[str]) -> list[str]:
    return [word for word in words if word.lower() in text.lower()]


def company_tokens(company_name: str) -> list[str]:
    raw = re.split(r"[（）()/、|｜\s]+", company_name)
    tokens = [token for token in raw if len(token) >= 3]
    if company_name and company_name not in tokens:
        tokens.insert(0, company_name)
    return tokens[:6]


def infer_source_type(url: str, title: str, snippet: str) -> str:
    domain = domain_of(url)
    text = f"{title} {snippet} {url}".lower()
    if any(item in domain for item in GOVERNMENT_DOMAINS):
        return "government"
    if any(item in domain for item in PUBLIC_PLATFORM_DOMAINS):
        return "public_platform"
    if any(item in domain for item in RECRUITMENT_PLATFORM_DOMAINS):
        return "recruitment_platform"
    if any(item in domain for item in LOW_AUTHORITY_DOMAINS):
        return "low_authority"
    if contains_any(text, RECRUITMENT_HINTS):
        return "possible_recruitment"
    return "possible_official"


def score_candidate(company_name: str, url: str, title: str, snippet: str) -> CandidateScore:
    title = compact_text(title)
    snippet = compact_text(snippet)
    domain = domain_of(url)
    text = f"{title} {snippet} {url}"
    reasons: list[str] = []
    score = 0

    tokens = company_tokens(company_name)
    title_company_hits = contains_any(title, tokens)
    snippet_company_hits = contains_any(snippet, tokens)
    url_company_hits = contains_any(url, tokens)
    if title_company_hits:
        score += 32
        reasons.append("标题匹配公司名：" + "、".join(title_company_hits[:3]))
    elif url_company_hits:
        score += 16
        reasons.append("URL 匹配公司名：" + "、".join(url_company_hits[:3]))
    elif snippet_company_hits:
        score += 10
        reasons.append("摘要匹配公司名：" + "、".join(snippet_company_hits[:3]))

    recruitment_hits = contains_any(text, RECRUITMENT_HINTS)
    if recruitment_hits:
        score += 25
        reasons.append("招聘相关：" + "、".join(recruitment_hits[:4]))

    official_hits = contains_any(text, OFFICIAL_HINTS)
    if official_hits:
        score += 12
        reasons.append("官方相关：" + "、".join(official_hits[:3]))

    security_hits = contains_any(text, SECURITY_HINTS)
    if security_hits:
        score += 12
        reasons.append("网络安全相关：" + "、".join(security_hits[:3]))

    computer_hits = contains_any(text, COMPUTER_HINTS)
    if computer_hits:
        score += 8
        reasons.append("泛计算机相关：" + "、".join(computer_hits[:3]))

    if any(item in domain for item in GOVERNMENT_DOMAINS):
        score += 18
        reasons.append("政府/公共部门域名")

    if any(item in domain for item in PUBLIC_PLATFORM_DOMAINS):
        score += 15
        reasons.append("国聘/公共招聘平台")

    if any(item in domain for item in RECRUITMENT_PLATFORM_DOMAINS):
        score += 8
        reasons.append("招聘平台域名")
        if not title_company_hits:
            score -= 24
            reasons.append("招聘平台标题未匹配公司")

    if any(item in domain for item in LOW_AUTHORITY_DOMAINS):
        score -= 28
        reasons.append("低权威或聚合域名")

    if any(item in domain for item in LOW_AUTHORITY_DOMAINS) and not title_company_hits:
        score -= 18
        reasons.append("低权威来源且标题未匹配公司")

    source_type = infer_source_type(url, title, snippet)
    bounded_score = max(0, min(100, score))
    if bounded_score >= 75:
        confidence = "high"
    elif bounded_score >= 50:
        confidence = "medium"
    else:
        confidence = "low"

    return CandidateScore(
        score=bounded_score,
        source_type=source_type,
        confidence=confidence,
        reasons=reasons or ["未命中明显特征"],
    )
