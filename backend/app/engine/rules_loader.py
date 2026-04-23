"""Load and validate YAML rule packs.

Validation fails loudly at startup: a malformed rule pack raises at import
time, surfacing in the ``/health`` endpoint and preventing the server from
serving bad rules.
"""

from __future__ import annotations

import pathlib
from dataclasses import replace
from typing import Any

import yaml

from .rule_model import Fixtures, FixOp, MatchClause, Rule

_VALID_MATCH_OPS = {"equals", "regex", "gt", "lt", "ge", "le", "ne", "one_of", "exists", "missing"}
_VALID_SEVERITY = {"info", "warning", "critical"}
_VALID_CONFIDENCE = {"high", "medium", "low"}
_VALID_EFFECT = {"latency", "fps", "frame_pacing", "stability", "visuals", "nothing"}
_VALID_KEY_STATUS = {"confirmed", "observed", "unknown"}
_VALID_FILE_TYPES = {
    "ChaosEngine",
    "ChaosGame",
    "ChaosInput",
    "ChaosLightmass",
    "ChaosSystemSettings",
    "ChaosUI",
}
_VALID_ISSUE_TYPES = {
    "dead_entry",
    "typoed_key",
    "unsupported_setting",
    "override",
    "uncertain_override",
    "array_composition",
    "conflict",
    "placebo",
    "unknown_key",
    "no_effect",
    "latency_risk",
    "frame_pacing_risk",
    "stutter_risk",
    "queue_depth",
    "resource_waste",
    "dangerous_streaming",
    "dangerous_visual",
    "dangerous_stability",
}


class RulePackError(ValueError):
    """Raised when a rule pack fails schema validation."""


def _parse_match(raw: dict[str, Any], context: str) -> MatchClause:
    if "key" not in raw:
        raise RulePackError(f"{context}: missing 'key'")
    op = raw.get("op", "equals")
    if op not in _VALID_MATCH_OPS:
        raise RulePackError(f"{context}: invalid op '{op}'")
    if op in {"exists", "missing"}:
        return MatchClause(section=raw.get("section"), key=raw["key"], op=op, value=None)
    if "value" not in raw:
        raise RulePackError(f"{context}: op '{op}' requires 'value'")
    return MatchClause(
        section=raw.get("section"),
        key=raw["key"],
        op=op,
        value=raw["value"],
    )


def _parse_fix(raw: dict[str, Any] | None, rule_id: str) -> FixOp | None:
    if raw is None:
        return None
    op = raw.get("op")
    if op not in {"set", "remove"}:
        raise RulePackError(f"rule {rule_id}: fix.op must be 'set' or 'remove'")
    section = raw.get("section")
    key = raw.get("key")
    if not section or not key:
        raise RulePackError(f"rule {rule_id}: fix requires 'section' and 'key'")
    value = raw.get("value")
    if op == "set" and value is None:
        raise RulePackError(f"rule {rule_id}: fix.op=set requires 'value'")
    return FixOp(op=op, section=section, key=key, value=value if value is None else str(value))


def _parse_fixtures(raw: dict[str, Any] | None, rule_id: str) -> Fixtures | None:
    if raw is None:
        return None
    if "red" not in raw or "green" not in raw:
        raise RulePackError(f"rule {rule_id}: fixtures must include both 'red' and 'green'")
    return Fixtures(red=str(raw["red"]), green=str(raw["green"]))


def _parse_rule(raw: dict[str, Any], context: str) -> Rule:
    if not isinstance(raw, dict):
        raise RulePackError(f"{context}: rule must be a mapping")
    rule_id = raw.get("id")
    if not rule_id:
        raise RulePackError(f"{context}: rule missing 'id'")
    context = f"rule {rule_id}"

    file_type = raw.get("file_type")
    if file_type not in _VALID_FILE_TYPES:
        raise RulePackError(f"{context}: invalid file_type '{file_type}'")

    severity = raw.get("severity", "info")
    if severity not in _VALID_SEVERITY:
        raise RulePackError(f"{context}: invalid severity '{severity}'")

    confidence = raw.get("confidence", "medium")
    if confidence not in _VALID_CONFIDENCE:
        raise RulePackError(f"{context}: invalid confidence '{confidence}'")

    issue_type = raw.get("issue_type")
    if issue_type not in _VALID_ISSUE_TYPES:
        raise RulePackError(f"{context}: invalid issue_type '{issue_type}'")

    effect_raw = raw.get("effect", []) or []
    if not isinstance(effect_raw, list):
        raise RulePackError(f"{context}: effect must be a list")
    for e in effect_raw:
        if e not in _VALID_EFFECT:
            raise RulePackError(f"{context}: invalid effect '{e}'")

    ksr = raw.get("key_status_required", ["confirmed", "observed"]) or []
    if not isinstance(ksr, list):
        raise RulePackError(f"{context}: key_status_required must be a list")
    for s in ksr:
        if s not in _VALID_KEY_STATUS:
            raise RulePackError(f"{context}: invalid key_status '{s}'")

    match_raw = raw.get("match")
    if not isinstance(match_raw, dict):
        raise RulePackError(f"{context}: match must be a mapping")
    match = _parse_match(match_raw, f"{context}.match")

    require_raw = raw.get("require", []) or []
    if not isinstance(require_raw, list):
        raise RulePackError(f"{context}: require must be a list")
    require = tuple(
        _parse_match(r, f"{context}.require[{i}]") for i, r in enumerate(require_raw)
    )

    fix = _parse_fix(raw.get("fix"), rule_id)
    fixtures = _parse_fixtures(raw.get("fixtures"), rule_id)

    # Linter: any fix value must be the one declared in this rule file.
    # We enforce by construction (the fix value lives inside the rule YAML).
    return Rule(
        id=rule_id,
        title=str(raw.get("title", rule_id)),
        file_type=file_type,
        match=match,
        require=require,
        severity=severity,
        issue_type=issue_type,
        effect=tuple(effect_raw),
        confidence=confidence,
        key_status_required=tuple(ksr),
        rationale=str(raw.get("rationale", "")).strip(),
        fix=fix,
        fixtures=fixtures,
    )


def load_rules(rules_dir: pathlib.Path) -> tuple[Rule, ...]:
    """Load every *.yaml file under ``rules_dir`` into a flat rule tuple."""
    rules: list[Rule] = []
    seen_ids: set[str] = set()
    if not rules_dir.exists():
        raise RulePackError(f"rules directory does not exist: {rules_dir}")
    for path in sorted(rules_dir.glob("*.yaml")):
        with path.open("r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or []
        if not isinstance(raw, list):
            raise RulePackError(f"{path}: rule pack must be a YAML list")
        for i, item in enumerate(raw):
            rule = _parse_rule(item, f"{path.name}[{i}]")
            if rule.id in seen_ids:
                raise RulePackError(f"{path}: duplicate rule id '{rule.id}'")
            seen_ids.add(rule.id)
            rules.append(rule)
    return tuple(rules)
