"""Rule data model.

Rules are pure data loaded from YAML. They carry:
  - metadata (id, title, file_type, severity, issue_type, effects, confidence)
  - a single top-level ``match`` clause that picks the entry the rule fires on
  - zero-or-more ``require`` clauses (additional conditions on other keys)
  - an optional ``fix`` describing a patch op
  - red+green fixtures used by tests to verify the rule's boundary
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Severity = Literal["info", "warning", "critical"]
Confidence = Literal["high", "medium", "low"]
Effect = Literal["latency", "fps", "frame_pacing", "stability", "visuals", "nothing"]
MatchOp = Literal["equals", "regex", "gt", "lt", "ge", "le", "ne", "one_of", "exists", "missing"]
KeyStatus = Literal["confirmed", "observed", "unknown"]

IssueType = Literal[
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
]


@dataclass(frozen=True)
class MatchClause:
    section: str | None
    key: str
    op: MatchOp
    value: Any | None = None


@dataclass(frozen=True)
class FixOp:
    op: Literal["set", "remove"]
    section: str
    key: str
    value: str | None = None


@dataclass(frozen=True)
class Fixtures:
    red: str
    green: str


@dataclass(frozen=True)
class Rule:
    id: str
    title: str
    file_type: str
    match: MatchClause
    require: tuple[MatchClause, ...] = ()
    severity: Severity = "info"
    issue_type: IssueType = "unsupported_setting"
    effect: tuple[Effect, ...] = ()
    confidence: Confidence = "medium"
    key_status_required: tuple[KeyStatus, ...] = ("confirmed", "observed")
    rationale: str = ""
    fix: FixOp | None = None
    fixtures: Fixtures | None = None
