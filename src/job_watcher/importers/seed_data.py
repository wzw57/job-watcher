from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


COMPANIES_FILE = "companies_seed.csv"
SOURCES_FILE = "company_sources_seed.csv"
MANIFEST_FILE = "seed_manifest.json"
COMPANY_FIELDS = ("company_key", "source_row", "group_name", "company_name", "normalized_name", "entity_type", "region", "priority_raw", "priority", "difficulty", "education_barrier", "recommended_directions", "action_status", "source_urls", "url_count", "url_notes", "enabled")
SOURCE_FIELDS = ("company_key", "company_name", "priority", "enabled", "source_index", "url", "source_type", "url_notes")


@dataclass(frozen=True)
class SeedCheck:
    seed_dir: Path
    company_count: int
    source_count: int
    manifest_version: str
    sha256: dict[str, str]


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read(path: Path, required: tuple[str, ...]) -> list[dict[str, str]]:
    if not path.exists():
        raise ValueError(f"Missing seed file: {path}")
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [x for x in required if x not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"Missing required fields in {path.name}: {', '.join(missing)}")
        rows = list(reader)
    if not rows:
        raise ValueError(f"Seed file is empty: {path}")
    return rows


def validate_seed_data(seed_dir: Path) -> SeedCheck:
    companies_path, sources_path, manifest_path = (seed_dir / COMPANIES_FILE, seed_dir / SOURCES_FILE, seed_dir / MANIFEST_FILE)
    companies = _read(companies_path, COMPANY_FIELDS)
    sources = _read(sources_path, SOURCE_FIELDS)
    if not manifest_path.exists():
        raise ValueError(f"Missing seed manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    keys = [r["company_key"] for r in companies]
    if len(keys) != len(set(keys)):
        raise ValueError("Duplicate company_key in companies_seed.csv")
    unknown = sorted({r["company_key"] for r in sources} - set(keys))
    if unknown:
        raise ValueError(f"Source rows reference unknown company_key: {unknown[:5]}")
    counts = manifest.get("counts", {})
    if counts.get("companies") != len(companies) or counts.get("sources") != len(sources):
        raise ValueError(f"Manifest counts do not match CSV rows: manifest={counts}, actual={len(companies)}/{len(sources)}")
    actual = {COMPANIES_FILE: file_sha256(companies_path), SOURCES_FILE: file_sha256(sources_path)}
    for name, digest in actual.items():
        expected = manifest.get("files", {}).get(name, {}).get("sha256")
        if expected != digest:
            raise ValueError(f"SHA-256 mismatch for {name}: expected {expected}, got {digest}")
    return SeedCheck(seed_dir, len(companies), len(sources), str(manifest.get("bundle_version", "")), actual)


def recovery_hint(seed_dir: Path) -> str:
    return f"Run seed-data-doctor after restoring {COMPANIES_FILE}, {SOURCES_FILE}, and {MANIFEST_FILE} under {seed_dir}."
