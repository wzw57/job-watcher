from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pytest

from job_watcher.importers.seed_data import COMPANY_FIELDS, SOURCE_FIELDS, validate_seed_data


def write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed_dir(tmp_path: Path) -> Path:
    company = {field: "" for field in COMPANY_FIELDS}
    company.update(company_key="c1", source_row="2", group_name="集团", company_name="企业", normalized_name="企业", priority="P0", enabled="true")
    source = {field: "" for field in SOURCE_FIELDS}
    source.update(company_key="c1", company_name="企业", priority="P0", enabled="true", source_index="1", url="https://example.com", source_type="official_or_unknown")
    cp, sp = tmp_path / "companies_seed.csv", tmp_path / "company_sources_seed.csv"
    write_csv(cp, COMPANY_FIELDS, [company]); write_csv(sp, SOURCE_FIELDS, [source])
    manifest = {"bundle_version":"test-v1","counts":{"companies":1,"sources":1},"files":{"companies_seed.csv":{"sha256":digest(cp)},"company_sources_seed.csv":{"sha256":digest(sp)}}}
    (tmp_path / "seed_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return tmp_path


def test_manifest_backed_seed_validation(tmp_path: Path) -> None:
    result = validate_seed_data(seed_dir(tmp_path))
    assert (result.company_count, result.source_count, result.manifest_version) == (1, 1, "test-v1")


def test_seed_validation_rejects_sha_mismatch(tmp_path: Path) -> None:
    directory = seed_dir(tmp_path)
    with (directory / "companies_seed.csv").open("a", encoding="utf-8") as f: f.write("\n")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        validate_seed_data(directory)


def test_seed_validation_rejects_unknown_company_key(tmp_path: Path) -> None:
    directory = seed_dir(tmp_path)
    rows = list(csv.DictReader((directory / "company_sources_seed.csv").open(encoding="utf-8-sig")))
    rows[0]["company_key"] = "missing"
    write_csv(directory / "company_sources_seed.csv", SOURCE_FIELDS, rows)
    manifest = json.loads((directory / "seed_manifest.json").read_text())
    manifest["files"]["company_sources_seed.csv"]["sha256"] = digest(directory / "company_sources_seed.csv")
    (directory / "seed_manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="unknown company_key"):
        validate_seed_data(directory)
