"""Value-level PII guard for the raw CSV exports that are committed to git.

adapters/pii_policy.py is a column allowlist, so it cannot stop a person's
name typed into an allowed free-text column (``unique_name``). This test scans
every committed fields export and fails on any ``unique_name`` that has no
digit (plot codes always do) unless it was reviewed and listed below. A new
export with a farmer's name in that column therefore fails loudly before push.
"""
import csv
import re
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1] / "data"
FIELDS_FILES = sorted(p for p in DATA.glob("*/csv/*.csv") if re.match(r"fields?-", p.name))

# Reviewed values that are not personal names.
REVIEWED_NON_NAMES = {"REDACTED", "UNIDENTIFIED LOT. NO. PA PO", "GUEBSAN-", "BNNM", "CPK-", "SRC-"}


@pytest.mark.parametrize("path", FIELDS_FILES, ids=lambda p: p.name)
def test_unique_name_holds_no_personal_names(path):
    csv.field_size_limit(10**9)
    with path.open(newline="", encoding="utf-8-sig") as fh:
        values = {(r.get("unique_name") or "").strip() for r in csv.DictReader(fh)}
    suspicious = sorted(v for v in values if v and not re.search(r"\d", v) and v not in REVIEWED_NON_NAMES)
    assert not suspicious, (
        f"{path.name}: possible personal names in unique_name {suspicious}. "
        "Replace with REDACTED (or add to REVIEWED_NON_NAMES if it is a plot label)."
    )


@pytest.mark.parametrize("path", FIELDS_FILES, ids=lambda p: p.name)
def test_no_pii_columns_in_raw_export(path):
    csv.field_size_limit(10**9)
    with path.open(newline="", encoding="utf-8-sig") as fh:
        cols = set(csv.DictReader(fh).fieldnames or [])
    assert not cols & {"owner_name", "rice_specialist"}
