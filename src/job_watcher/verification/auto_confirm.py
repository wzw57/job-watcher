from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class AutoConfirmResult:
    government: int
    platform: int
    recruitment: int
    total: int


def conservative_auto_confirm(conn: sqlite3.Connection) -> AutoConfirmResult:
    """Promote only low-risk source types to verified statuses.

    This intentionally avoids `official_or_unknown`; those still require manual
    review because many original spreadsheet URLs are unverified.
    """
    government = conn.execute(
        """
        UPDATE sources
        SET verification_status = 'verified_government',
            trust_level = CASE WHEN trust_level < 88 THEN 88 ELSE trust_level END,
            enabled = 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE verification_status = 'candidate'
          AND source_type = 'government'
        """
    ).rowcount
    platform = conn.execute(
        """
        UPDATE sources
        SET verification_status = 'verified_platform',
            trust_level = CASE WHEN trust_level < 75 THEN 75 ELSE trust_level END,
            enabled = 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE verification_status = 'candidate'
          AND source_type IN ('public_platform', 'campus')
        """
    ).rowcount
    recruitment = conn.execute(
        """
        UPDATE sources
        SET verification_status = 'verified_recruitment',
            trust_level = CASE WHEN trust_level < 78 THEN 78 ELSE trust_level END,
            enabled = 1,
            updated_at = CURRENT_TIMESTAMP
        WHERE verification_status = 'candidate'
          AND source_type = 'official_recruitment'
        """
    ).rowcount
    conn.commit()
    return AutoConfirmResult(
        government=government,
        platform=platform,
        recruitment=recruitment,
        total=government + platform + recruitment,
    )

