"""Report presentation modes.

The deterministic analyzer computes every finding it can justify. At the
presentation boundary we filter what the user actually sees, because
dumping every unknown_key / uncertain_override / array_composition buries
real risks under inventory noise.

Three modes:
  - actionable_only (default): critical, warning, and the subset of info
      findings whose issue_type is a real risk/ineffective-line signal
      AND whose confidence is high or medium. No unknown_key, no
      uncertain_override, no array_composition. typoed_key is shown
      ONLY when the evaluator promoted it to warning severity.
  - verbose: every computed finding, no filtering. Same content as raw
      for ranked_findings; exists as the user-facing "show me everything"
      mode.
  - raw: full dump. Equivalent to verbose today; reserved for any future
      debug-only internals.
"""

from __future__ import annotations

from typing import Literal

from .evaluator import FindingData

ReportMode = Literal["actionable_only", "verbose", "raw"]


# Info-severity issue types that are actionable when a rule emits them.
# These describe real risks or clearly ineffective lines. Unknown/uncertain
# types are explicitly NOT in this set.
ACTIONABLE_INFO_ISSUE_TYPES: frozenset[str] = frozenset(
    {
        "stutter_risk",
        "latency_risk",
        "frame_pacing_risk",
        "dangerous_streaming",
        "dangerous_visual",
        "dangerous_stability",
        "dead_entry",
        "no_effect",
        "override",
        "conflict",
        "typoed_key",  # kept only when confidence is high/medium — see below
        "resource_waste",
    }
)

# Always-suppressed in actionable_only regardless of severity/confidence.
_ALWAYS_SUPPRESSED_IN_ACTIONABLE: frozenset[str] = frozenset(
    {
        "unknown_key",
        "uncertain_override",
        "array_composition",
    }
)


def is_actionable(finding: FindingData, mode: ReportMode) -> bool:
    """Return True if this finding should be shown in the requested mode."""
    if mode == "raw":
        return True
    if mode == "verbose":
        # verbose still hides pure-inventory types; they live in the
        # suppressed summary. Everything else is shown.
        return finding.issue_type not in _ALWAYS_SUPPRESSED_IN_ACTIONABLE
    # actionable_only
    if finding.issue_type in _ALWAYS_SUPPRESSED_IN_ACTIONABLE:
        return False
    if finding.severity in ("critical", "warning"):
        return True
    # severity == "info": only include if it's an actionable type with
    # medium+ confidence. This is where we keep real risks without
    # inheriting unknown/uncertain noise.
    if finding.issue_type in ACTIONABLE_INFO_ISSUE_TYPES:
        if finding.issue_type == "typoed_key" and finding.confidence == "low":
            return False  # ambiguous typo — suppress
        return finding.confidence in ("high", "medium")
    return False


def partition(
    findings: list[FindingData], mode: ReportMode
) -> tuple[list[FindingData], dict[str, int]]:
    """Split findings into (kept, suppressed_counts).

    ``suppressed_counts`` buckets each suppressed finding by the broad
    reason it was hidden so the summary can show one compact line per
    bucket.
    """
    kept: list[FindingData] = []
    counts: dict[str, int] = {
        "unknown_keys": 0,
        "uncertain_overrides": 0,
        "array_compositions": 0,
        "weak_typoed_keys": 0,
        "info_noise": 0,
    }
    for f in findings:
        if is_actionable(f, mode):
            kept.append(f)
            continue
        if f.issue_type == "unknown_key":
            counts["unknown_keys"] += 1
        elif f.issue_type == "uncertain_override":
            counts["uncertain_overrides"] += 1
        elif f.issue_type == "array_composition":
            counts["array_compositions"] += 1
        elif f.issue_type == "typoed_key":
            counts["weak_typoed_keys"] += 1
        else:
            counts["info_noise"] += 1
    return kept, counts


def highest_severity(findings: list[FindingData]) -> str | None:
    """Return 'critical' | 'warning' | 'info' | None."""
    order = {"critical": 0, "warning": 1, "info": 2}
    best: str | None = None
    best_rank = 99
    for f in findings:
        r = order.get(f.severity, 99)
        if r < best_rank:
            best = f.severity
            best_rank = r
    return best
