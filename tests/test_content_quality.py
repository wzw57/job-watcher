from __future__ import annotations

from job_watcher.parsers.quality import assess_content_quality


def test_quality_flags_short_placeholder_and_mojibake() -> None:
    result = assess_content_quality("Loading... \ufffd\ufffd", "")
    assert result.score < 35
    assert "very_short_text" in result.flags
    assert "placeholder_or_loading_page" in result.flags
    assert "encoding_replacement_chars" in result.flags


def test_quality_accepts_substantive_recruitment_text() -> None:
    text = "青岛校园招聘岗位，报名截止2026年9月30日。" * 30
    result = assess_content_quality(text, "2027届校园招聘公告")
    assert result.score >= 70
    assert "recruitment_signal" in result.flags
