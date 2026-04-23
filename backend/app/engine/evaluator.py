"""Rule evaluator.

Given a parsed+classified doc and the loaded rules/registry, produce a
list of Findings. The evaluator handles:

  - Rule matching (equals/regex/numeric comparisons/exists/missing/one_of).
  - ``require`` clauses referencing other keys in the doc.
  - Unknown-key classification:
      * If a key isn't in the registry and no rule matched it -> unknown_key.
      * If it looks like a typo of a known key (per placebo_detector) ->
        typoed_key (never promoted to placebo without an extra rule).
  - Lightmass-file runtime-key detection (rule-backed no_effect).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from ..parser.content_classifier import ClassificationResult
from ..parser.ue3_ini import Entry, ParsedDoc
from .placebo_detector import find_typo_candidates, is_dead_array_op
from .registry import KnownKeyRegistry
from .rule_model import MatchClause, Rule


@dataclass(frozen=True)
class FindingData:
    """Internal finding shape; main.py wraps these into the Pydantic model."""

    id: str
    file_type: str
    filename_hint: str
    section: str
    key: str
    value: str
    severity: str
    issue_type: str
    effect: tuple[str, ...]
    location: str
    fix: dict | None
    confidence: str
    key_status: str
    rationale: str


def _norm_bool(value: Any) -> str | None:
    """Normalise a value to the string 'true'/'false' if it's clearly boolean."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        s = value.strip().lower()
        if s in ("true", "false"):
            return s
    return None


def _value_equals(entry_value: Any, rule_value: Any) -> bool:
    # Normalise true/false case-insensitively since UE3 uses TRUE/FALSE.
    a = _norm_bool(entry_value)
    b = _norm_bool(rule_value)
    if a is not None and b is not None:
        return a == b
    # Numeric equality when both sides coerce.
    try:
        return float(entry_value) == float(rule_value)
    except (TypeError, ValueError):
        pass
    return str(entry_value) == str(rule_value)


def _value_numeric(entry_value: Any) -> float | None:
    if isinstance(entry_value, bool):
        return None  # treat booleans as non-numeric for comparisons
    try:
        return float(entry_value)
    except (TypeError, ValueError):
        return None


def _entries_in(doc: ParsedDoc, section: str | None) -> list[Entry]:
    if section is None:
        out: list[Entry] = []
        for _, entries in doc.sections.items():
            out.extend(entries)
        return out
    return doc.sections.get(section, [])


def _entry_matches(entry: Entry, clause: MatchClause) -> bool:
    if entry.key != clause.key:
        return False
    op = clause.op
    if op == "exists":
        return True
    if op == "missing":
        return False
    if op == "equals":
        return _value_equals(entry.typed_value, clause.value)
    if op == "ne":
        return not _value_equals(entry.typed_value, clause.value)
    if op == "regex":
        pattern = re.compile(str(clause.value))
        return bool(pattern.search(str(entry.raw_value)))
    if op == "one_of":
        values = clause.value or []
        return any(_value_equals(entry.typed_value, v) for v in values)
    n = _value_numeric(entry.typed_value)
    if n is None:
        return False
    target = _value_numeric(clause.value)
    if target is None:
        return False
    if op == "gt":
        return n > target
    if op == "lt":
        return n < target
    if op == "ge":
        return n >= target
    if op == "le":
        return n <= target
    return False


def _clause_satisfied(doc: ParsedDoc, clause: MatchClause) -> bool:
    entries = _entries_in(doc, clause.section)
    if clause.op == "missing":
        return not any(e.key == clause.key for e in entries)
    return any(_entry_matches(e, clause) for e in entries)


def evaluate(
    doc: ParsedDoc,
    classification: ClassificationResult,
    rules: Iterable[Rule],
    registry: KnownKeyRegistry,
) -> list[FindingData]:
    """Run rules and unknown-key/typo classification on a single doc."""
    classified_type = classification.classified_type
    findings: list[FindingData] = []

    # Track which (section, key, line) pairs were matched by any rule so we
    # don't emit duplicate unknown_key findings for them afterwards.
    matched_locations: set[tuple[str, str, int]] = set()

    if classified_type in {"Fragment", "Mixed", "Unsupported"}:
        # For Fragment we still run per-file rules (the user asked for
        # analysis); Mixed/Unsupported skip evaluation per the v1 policy.
        if classified_type != "Fragment":
            return findings

    file_type_for_rules = (
        classified_type
        if classified_type not in {"Fragment", "Mixed", "Unsupported"}
        else (classification.mixed_types[0] if classification.mixed_types else None)
    )

    if file_type_for_rules is not None:
        for rule in rules:
            if rule.file_type != file_type_for_rules:
                continue
            # Find entries matching the rule's primary match clause.
            for entry in _entries_in(doc, rule.match.section):
                if not _entry_matches(entry, rule.match):
                    continue
                # key_status_required gate.
                reg_entry = registry.lookup(
                    file_type_for_rules, rule.match.section or "", entry.key
                )
                key_status = reg_entry.status if reg_entry else "unknown"
                if key_status not in rule.key_status_required:
                    continue
                # Require clauses.
                if not all(_clause_satisfied(doc, c) for c in rule.require):
                    continue

                location = f"{classified_type} ({doc.filename_hint}):{entry.line_no}"
                fix = None
                if rule.fix is not None:
                    fix = {
                        "op": rule.fix.op,
                        "section": rule.fix.section,
                        "key": rule.fix.key,
                        "value": rule.fix.value,
                    }
                findings.append(
                    FindingData(
                        id=rule.id,
                        file_type=classified_type,
                        filename_hint=doc.filename_hint,
                        section=rule.match.section or "",
                        key=entry.key,
                        value=str(entry.raw_value),
                        severity=rule.severity,
                        issue_type=rule.issue_type,
                        effect=rule.effect,
                        location=location,
                        fix=fix,
                        confidence=rule.confidence,
                        key_status=key_status,
                        rationale=rule.rationale,
                    )
                )
                matched_locations.add(
                    (rule.match.section or "", entry.key, entry.line_no)
                )

    # Unknown-key + typo pass. Only for non-Fragment/Mixed/Unsupported docs.
    if classified_type in {"ChaosEngine", "ChaosGame", "ChaosInput", "ChaosLightmass", "ChaosSystemSettings", "ChaosUI"}:
        findings.extend(
            _unknown_key_pass(
                doc=doc,
                classified_type=classified_type,
                registry=registry,
                already_matched=matched_locations,
            )
        )
        # Dead array ops.
        findings.extend(
            _dead_array_op_pass(
                doc=doc,
                classified_type=classified_type,
            )
        )

    return findings


def _unknown_key_pass(
    *,
    doc: ParsedDoc,
    classified_type: str,
    registry: KnownKeyRegistry,
    already_matched: set[tuple[str, str, int]],
) -> list[FindingData]:
    out: list[FindingData] = []
    for section, entries in doc.sections.items():
        for entry in entries:
            if (section, entry.key, entry.line_no) in already_matched:
                continue
            reg = registry.lookup(classified_type, section, entry.key)
            if reg is not None:
                continue  # known — no finding.
            # Is it a typo?
            verdict = find_typo_candidates(entry.key, section, classified_type, registry)
            if verdict.candidates:
                best = verdict.candidates[0]
                conf = "low" if verdict.ambiguous else "medium"
                rationale = (
                    f"Key '{entry.key}' is not in the Paladins known-key registry; "
                    f"closest known key is '{best.target.key}' "
                    f"(distance {best.distance}, section match: {best.same_section}). "
                )
                if verdict.ambiguous:
                    rationale += "Multiple candidates tie; suggestion is ambiguous."
                fix = None
                out.append(
                    FindingData(
                        id="placebo.typoed_key",
                        file_type=classified_type,
                        filename_hint=doc.filename_hint,
                        section=section,
                        key=entry.key,
                        value=str(entry.raw_value),
                        severity="info",
                        issue_type="typoed_key",
                        effect=("nothing",),
                        location=f"{classified_type} ({doc.filename_hint}):{entry.line_no}",
                        fix=fix,
                        confidence=conf,
                        key_status="unknown",
                        rationale=rationale,
                    )
                )
                continue
            # Default: unknown_key.
            out.append(
                FindingData(
                    id="placebo.unknown_key",
                    file_type=classified_type,
                    filename_hint=doc.filename_hint,
                    section=section,
                    key=entry.key,
                    value=str(entry.raw_value),
                    severity="info",
                    issue_type="unknown_key",
                    effect=("nothing",),
                    location=f"{classified_type} ({doc.filename_hint}):{entry.line_no}",
                    fix=None,
                    confidence="low",
                    key_status="unknown",
                    rationale="Key not found in Paladins known-key registry. Cannot determine effect.",
                )
            )
    return out


def _dead_array_op_pass(
    *,
    doc: ParsedDoc,
    classified_type: str,
) -> list[FindingData]:
    out: list[FindingData] = []
    for section, entries in doc.sections.items():
        for entry in entries:
            if entry.op in {"set", "+", "."}:
                continue
            # "-" or "!"
            if not is_dead_array_op(entry.op, entry.key, entries):
                continue
            out.append(
                FindingData(
                    id="placebo.dead_array_op",
                    file_type=classified_type,
                    filename_hint=doc.filename_hint,
                    section=section,
                    key=entry.key,
                    value=str(entry.raw_value),
                    severity="info",
                    issue_type="dead_entry",
                    effect=("nothing",),
                    location=f"{classified_type} ({doc.filename_hint}):{entry.line_no}",
                    fix=None,
                    confidence="medium",
                    key_status="unknown",
                    rationale=(
                        f"Array op '{entry.op}{entry.key}' has no base array "
                        "definition in this file; it resolves to a no-op."
                    ),
                )
            )
    return out
