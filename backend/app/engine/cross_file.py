"""Adapter between the resolver and the Finding stream.

``resolver.resolve`` produces structured override / uncertain_override /
array_composition records. This module converts each into ``FindingData``
so the rest of the pipeline can treat them uniformly.
"""

from __future__ import annotations

from .evaluator import FindingData
from .resolver import CrossFileResult


def to_findings(result: CrossFileResult) -> list[FindingData]:
    out: list[FindingData] = []

    for ov in result.overrides:
        loser_locs = ", ".join(
            f"{ref.file_type} ({ref.filename_hint}):{ref.line_no}" for ref in ov.losers
        )
        rationale = (
            f"Verified Paladins precedence: {ov.winner.file_type} wins over "
            f"{loser_locs}. Precedence source: {ov.precedence_source}."
        )
        out.append(
            FindingData(
                id=f"override.{ov.section}.{ov.key}",
                file_type=ov.winner.file_type,
                filename_hint=ov.winner.filename_hint,
                section=ov.section,
                key=ov.key,
                value=ov.winner.value,
                severity="info",
                issue_type="override",
                effect=("nothing",),
                location=f"{ov.winner.file_type} ({ov.winner.filename_hint}):{ov.winner.line_no}",
                fix=None,
                confidence="high",
                key_status="confirmed",
                rationale=rationale,
            )
        )

    for uc in result.uncertain_overrides:
        locs = ", ".join(
            f"{ref.file_type} ({ref.filename_hint}):{ref.line_no}" for ref in uc.candidates
        )
        rationale = (
            f"Conflicting values across files at {locs}, but precedence is not "
            "yet verified for this specific key in Paladins; cannot determine winner."
        )
        # Represent as a single finding anchored at the first candidate.
        first = uc.candidates[0]
        out.append(
            FindingData(
                id=f"uncertain_override.{uc.section}.{uc.key}",
                file_type=first.file_type,
                filename_hint=first.filename_hint,
                section=uc.section,
                key=uc.key,
                value=first.value,
                severity="info",
                issue_type="uncertain_override",
                effect=("nothing",),
                location=f"{first.file_type} ({first.filename_hint}):{first.line_no}",
                fix=None,
                confidence="low",
                key_status="unknown",
                rationale=rationale,
            )
        )

    for ac in result.array_compositions:
        locs = ", ".join(
            f"{ref.file_type} ({ref.filename_hint}):{ref.line_no}" for ref in ac.sources
        )
        rationale = (
            f"Array key composed across files (sources: {locs}). "
            f"Merged result: {list(ac.merged)}."
        )
        first = ac.sources[0]
        out.append(
            FindingData(
                id=f"array_composition.{ac.section}.{ac.key}",
                file_type=first.file_type,
                filename_hint=first.filename_hint,
                section=ac.section,
                key=ac.key,
                value=str(list(ac.merged)),
                severity="info",
                issue_type="array_composition",
                effect=("nothing",),
                location=f"{first.file_type} ({first.filename_hint}):{first.line_no}",
                fix=None,
                confidence="medium",
                key_status="confirmed",
                rationale=rationale,
            )
        )

    return out
