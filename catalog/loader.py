from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CATALOG_DIR = Path(__file__).resolve().parent


@lru_cache(maxsize=1)
def load_schema() -> dict[str, Any]:
    return yaml.safe_load((CATALOG_DIR / "schema.yaml").read_text())


@lru_cache(maxsize=1)
def load_category_mappings() -> dict[str, Any]:
    return yaml.safe_load((CATALOG_DIR / "category_mappings.yaml").read_text())


@lru_cache(maxsize=1)
def load_season_bounds_raw() -> dict[str, Any]:
    return yaml.safe_load((CATALOG_DIR / "season_bounds.yaml").read_text())


def season_labels() -> dict[str, str]:
    """season_id -> human-readable label (e.g. "3" -> "Dry Crop 2025"), the
    single source of truth for how a season is shown anywhere in the UI -
    raw season_id values (3, 4) are an internal join key, never surfaced
    directly to a user. See catalog/season_bounds.yaml."""
    return {season_id: cfg["label"] for season_id, cfg in load_season_bounds_raw().items()}


def known_fields() -> set[str]:
    """All valid `table.field` references, plus bare table names (for
    whole-collection refs like `photos`), across every documented table -
    available or not. Availability (whether a table has real data loaded)
    is a runtime concern handled by validation.engine.AVAILABLE_TABLES, not
    a DSL-validity concern.
    """
    schema = load_schema()
    fields: set[str] = set()
    for table, spec in schema.items():
        fields.add(table)
        for field_name in spec.get("fields", {}):
            fields.add(f"{table}.{field_name}")
    fields.add("item")  # predicate-scope placeholder, resolved per collection item
    return fields
