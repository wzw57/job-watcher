from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass


RECRUITMENT_MARKERS = (
    "招聘", "岗位", "应聘", "报名", "校招", "校园招聘", "社会招聘",
    "简历", "任职资格", "职位", "网申", "录用", "笔试", "面试",
)
PLACEHOLDER_MARKERS = (
    "enable javascript", "please enable javascript", "请开启javascript",
    "请启用javascript", "正在加载", "loading...", "系统维护中",
)
DATE_PATTERN = re.compile(r"(?:20\d{2}[年./-]\d{1,2}|截止.{0,8}\d{1,2}[日号])")


@dataclass(frozen=True)
class ContentQuality:
    score: int
    flags: tuple[str, ...]
    text_chars: int


def assess_content_quality(text: str, title: str = "") -> ContentQuality:
    """Score extraction quality, not job relevance.

    A generic but well-extracted company page may score as usable even without
    recruitment terms. The flags explain why a result needs review and are
    persisted with the raw evidence.
    """
    clean = " ".join(text.split())
    length = len(clean)
    flags: list[str] = []
    score = 0

    if length == 0:
        return ContentQuality(0, ("empty_text",), 0)
    if length < 80:
        score += 10
        flags.append("very_short_text")
    elif length < 200:
        score += 25
        flags.append("short_text")
    elif length < 800:
        score += 45
    else:
        score += 60

    if title.strip():
        score += 10
    else:
        flags.append("missing_title")

    lower = f"{title} {clean}".lower()
    marker_count = sum(marker in lower for marker in RECRUITMENT_MARKERS)
    score += min(20, marker_count * 4)
    if marker_count:
        flags.append("recruitment_signal")
    if DATE_PATTERN.search(clean):
        score += 5

    replacement_ratio = clean.count("\ufffd") / max(1, length)
    if replacement_ratio > 0.01:
        score -= 35
        flags.append("encoding_replacement_chars")

    words = clean.split()
    if len(words) >= 20:
        most_common = Counter(words).most_common(1)[0][1]
        if most_common / len(words) > 0.35:
            score -= 20
            flags.append("high_repetition")

    if length < 300 and any(marker in lower for marker in PLACEHOLDER_MARKERS):
        score -= 30
        flags.append("placeholder_or_loading_page")

    return ContentQuality(max(0, min(100, score)), tuple(dict.fromkeys(flags)), length)
