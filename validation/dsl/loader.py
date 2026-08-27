from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from catalog.loader import known_fields, load_category_mappings
from validation.dsl.validate import RuleValidationError, validate_rule
from validation.models import Rule

RULES_DIR = Path(__file__).resolve().parents[2] / "rules"


def _resolve_mapping_refs(node: Any) -> Any:
    """Replaces a params value like "$crop_to_photo_category" with the
    matching entry from catalog/category_mappings.yaml, so rule YAML files
    reference the mapping by name instead of duplicating it inline."""
    if isinstance(node, dict):
        resolved = {}
        for key, value in node.items():
            if key == "params" and isinstance(value, dict):
                mappings = load_category_mappings()
                resolved[key] = {
                    k: (mappings[v[1:]] if isinstance(v, str) and v.startswith("$") else v)
                    for k, v in value.items()
                }
            else:
                resolved[key] = _resolve_mapping_refs(value)
        return resolved
    if isinstance(node, list):
        return [_resolve_mapping_refs(item) for item in node]
    return node


def load_rule_file(path: Path, validate: bool = True) -> Rule:
    raw = yaml.safe_load(path.read_text())
    raw = _resolve_mapping_refs(raw)
    rule = Rule.model_validate(raw)
    if validate:
        errors = validate_rule(rule, known_fields())
        if errors:
            raise RuleValidationError(errors)
    return rule


def load_all_rules(rules_dir: Path = RULES_DIR, validate: bool = True) -> list[Rule]:
    return [load_rule_file(p, validate=validate) for p in sorted(rules_dir.glob("*.yaml"))]


def delete_rule_file(rule_id: str, rules_dir: Path = RULES_DIR) -> None:
    """Permanently deletes a static rule's YAML file (e.g. rules/C3.yaml).
    Unlike custom rules (stored in DuckDB, see persistence.duckdb_store),
    this mutates the version-controlled rule pack on disk - callers should
    get explicit confirmation first, especially outside a git repo where
    there's no easy way to recover the file afterward."""
    path = rules_dir / f"{rule_id}.yaml"
    if path.exists():
        path.unlink()


def save_rule_file(rule: Rule, rules_dir: Path = RULES_DIR) -> Path:
    """Writes `rule` out as rules/<rule_id>.yaml, in the same shape as the
    hand-authored base rule pack files - "promotes" a custom (DuckDB-only)
    rule into the permanent rule pack that ships with the app, so it
    survives a redeploy even where the DuckDB store's local file wouldn't
    (see README's persistence caveat). Callers should validate the rule
    first (see validation.dsl.validate.validate_rule) - this never
    overwrites the check, it just writes whatever it's given."""
    data: dict[str, Any] = {
        "rule_id": rule.rule_id,
        "name": rule.name,
        "version": rule.version,
        "description": rule.description,
        "scope": rule.scope,
        "status": rule.status.value,
        "required_inputs": rule.required_inputs,
        "missing_data": rule.missing_data.value,
        "expression": rule.expression.model_dump(mode="json", exclude_none=True),
    }
    if rule.parameters:
        data["parameters"] = rule.parameters
    path = rules_dir / f"{rule.rule_id}.yaml"
    path.write_text(yaml.safe_dump(data, sort_keys=False, default_flow_style=False))
    return path
