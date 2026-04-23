"""Cross-file resolver.

Takes a list of (ParsedDoc, classified_type) pairs and the registry +
precedence table, and produces:

  - confident overrides (scalar keys covered by a narrow precedence entry)
  - uncertain overrides (scalar conflicts with no precedence entry)
  - array compositions (any array-kind key appearing in >1 file)

Skips Fragment/Mixed/Unsupported docs for cross-file work.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from ..parser.ue3_ini import Entry, ParsedDoc, compose_array
from .precedence import PrecedenceTable
from .registry import KnownKeyRegistry


@dataclass(frozen=True)
class EntryRef:
    file_type: str
    filename_hint: str
    line_no: int
    value: str


@dataclass(frozen=True)
class OverrideEntry:
    section: str
    key: str
    winner: EntryRef
    losers: tuple[EntryRef, ...]
    verified: bool
    precedence_source: Literal["narrow", "unverified"]


@dataclass(frozen=True)
class UncertainOverride:
    section: str
    key: str
    candidates: tuple[EntryRef, ...]


@dataclass(frozen=True)
class ArrayComposition:
    section: str
    key: str
    merged: tuple[str, ...]
    sources: tuple[EntryRef, ...]


@dataclass(frozen=True)
class CrossFileResult:
    overrides: tuple[OverrideEntry, ...]
    uncertain_overrides: tuple[UncertainOverride, ...]
    array_compositions: tuple[ArrayComposition, ...]


ClassifiedDoc = tuple[ParsedDoc, str]  # (doc, classified_type)


def _eligible_docs(docs: Iterable[ClassifiedDoc]) -> list[ClassifiedDoc]:
    return [
        (d, t)
        for d, t in docs
        if t in {"ChaosEngine", "ChaosGame", "ChaosInput", "ChaosLightmass", "ChaosSystemSettings", "ChaosUI"}
    ]


def resolve(
    docs: Iterable[ClassifiedDoc],
    registry: KnownKeyRegistry,
    precedence: PrecedenceTable,
) -> CrossFileResult:
    eligible = _eligible_docs(docs)

    # Group entries by (section, key) across files.
    # Map: (section, key) -> list of (file_type, ParsedDoc, Entry)
    bucket: dict[tuple[str, str], list[tuple[str, ParsedDoc, Entry]]] = {}
    for doc, file_type in eligible:
        for section, entries in doc.sections.items():
            for entry in entries:
                bucket.setdefault((section, entry.key), []).append((file_type, doc, entry))

    overrides: list[OverrideEntry] = []
    uncertain: list[UncertainOverride] = []
    compositions: list[ArrayComposition] = []

    for (section, key), occurrences in bucket.items():
        if len(occurrences) < 2:
            continue
        # Only interesting if occurrences span 2+ distinct file types.
        file_types = {ft for ft, _, _ in occurrences}
        if len(file_types) < 2:
            continue

        value_kind = _value_kind(section, key, file_types, registry)

        if value_kind == "array":
            compositions.append(_compose(section, key, occurrences))
            continue

        # Scalar: check precedence for each distinct pair of file types.
        # In v1 a conflict across more than two file types with distinct
        # values yields an uncertain_override (we don't try to chain
        # precedence across pairs).
        distinct_values = {str(e.raw_value) for _, _, e in occurrences}
        if len(distinct_values) <= 1:
            continue  # same value everywhere; not a conflict.

        # If exactly two file types are involved, look up narrow entry.
        if len(file_types) == 2:
            ft_a, ft_b = list(file_types)
            entry = precedence.narrow(ft_a, ft_b, section, key)
            if entry is not None:
                winner_ft = entry.winner
                # Pick the first occurrence from the winner file type as the
                # canonical winner, rest are losers.
                winner_occ = next(o for o in occurrences if o[0] == winner_ft)
                loser_occs = [o for o in occurrences if o is not winner_occ]
                overrides.append(
                    OverrideEntry(
                        section=section,
                        key=key,
                        winner=_to_ref(winner_occ),
                        losers=tuple(_to_ref(o) for o in loser_occs),
                        verified=True,
                        precedence_source="narrow",
                    )
                )
                continue

        uncertain.append(
            UncertainOverride(
                section=section,
                key=key,
                candidates=tuple(_to_ref(o) for o in occurrences),
            )
        )

    return CrossFileResult(
        overrides=tuple(overrides),
        uncertain_overrides=tuple(uncertain),
        array_compositions=tuple(compositions),
    )


def _value_kind(
    section: str,
    key: str,
    file_types: set[str],
    registry: KnownKeyRegistry,
) -> str:
    """Look up value_kind from the registry; default to 'scalar' if any
    occurrence is in the registry with value_kind=array."""
    for ft in file_types:
        entry = registry.lookup(ft, section, key)
        if entry is not None:
            return entry.value_kind
    return "scalar"


def _to_ref(occ: tuple[str, ParsedDoc, Entry]) -> EntryRef:
    ft, doc, entry = occ
    return EntryRef(
        file_type=ft,
        filename_hint=doc.filename_hint,
        line_no=entry.line_no,
        value=str(entry.raw_value),
    )


def _compose(
    section: str,
    key: str,
    occurrences: list[tuple[str, ParsedDoc, Entry]],
) -> ArrayComposition:
    # Concatenate per-file entries in canonical load order. Phase 1 uses
    # alphabetical-by-file-type as a deterministic placeholder; Phase 2
    # will honour a verified Paladins load order.
    ordered = sorted(occurrences, key=lambda o: o[0])
    all_entries = [e for _, _, e in ordered]
    composed = compose_array(all_entries, key)
    sources = [_to_ref(o) for o in ordered]
    return ArrayComposition(
        section=section,
        key=key,
        merged=tuple(composed),
        sources=tuple(sources),
    )
