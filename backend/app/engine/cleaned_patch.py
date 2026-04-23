"""Patch-only cleaned output.

v1 emits a minimal diff of rule-backed edits. It never synthesises a full
config file. The returned shape is a dict keyed by classified file type,
each value a list of patch ops annotated by the rule that proposed them.

Structural guarantees enforced by tests:
  - Return value is ``dict[str, list[dict]]``.
  - Each list entry is a dict with keys: op, section, key, value, rule_id, rationale.
  - No string value in the returned structure is a full file synthesis.
"""

from __future__ import annotations

from typing import Any

from .evaluator import FindingData


def build_cleaned_patch(findings: list[FindingData]) -> dict[str, list[dict[str, Any]]]:
    """Produce a patch-only cleaned config output grouped by file type.

    Only findings with a non-null fix contribute a patch op. Unknown keys,
    uncertain overrides, and array compositions never produce patch ops.
    """
    patch: dict[str, list[dict[str, Any]]] = {}
    for f in findings:
        if f.fix is None:
            continue
        # Defensive: reject any fix whose value is a multi-line blob (a
        # synthesised file would look like that). Rule loader already
        # prevents this at load time, but the patch builder enforces it too.
        value = f.fix.get("value")
        if isinstance(value, str) and "\n" in value:
            raise RuntimeError(
                f"rule {f.id} attempted to emit a multi-line patch value; "
                "cleaned output is patch-only and must not contain synthesised files."
            )
        patch.setdefault(f.file_type, []).append(
            {
                "op": f.fix["op"],
                "section": f.fix["section"],
                "key": f.fix["key"],
                "value": value,
                "rule_id": f.id,
                "rationale": f.rationale,
            }
        )
    return patch
