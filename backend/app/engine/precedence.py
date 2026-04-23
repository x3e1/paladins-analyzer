"""Verified precedence loader and query interface.

v1 accepts narrow entries only: (file_type_a, file_type_b, section, key).
Section-wide entries (key: "*") are a Phase-2 feature and rejected here.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass
from typing import Literal

import yaml

ValueKind = Literal["scalar", "array", "struct"]


class PrecedenceError(ValueError):
    pass


@dataclass(frozen=True)
class PrecedenceEntry:
    file_type_a: str
    file_type_b: str
    section: str
    key: str  # never "*" in v1
    winner: str  # one of file_type_a/file_type_b
    value_kind: ValueKind
    verified_on_build: str
    verified_by: str
    notes: str = ""


_VALID_FILE_TYPES = {
    "ChaosEngine",
    "ChaosGame",
    "ChaosInput",
    "ChaosLightmass",
    "ChaosSystemSettings",
    "ChaosUI",
}
_VALID_VALUE_KIND = {"scalar", "array", "struct"}


def _parse_entry(raw: dict, context: str) -> PrecedenceEntry:
    for required in (
        "file_type_a",
        "file_type_b",
        "section",
        "key",
        "winner",
        "value_kind",
        "verified_on_build",
        "verified_by",
    ):
        if required not in raw:
            raise PrecedenceError(f"{context}: missing required field '{required}'")
    if raw["file_type_a"] not in _VALID_FILE_TYPES:
        raise PrecedenceError(f"{context}: invalid file_type_a '{raw['file_type_a']}'")
    if raw["file_type_b"] not in _VALID_FILE_TYPES:
        raise PrecedenceError(f"{context}: invalid file_type_b '{raw['file_type_b']}'")
    if raw["file_type_a"] == raw["file_type_b"]:
        raise PrecedenceError(f"{context}: file_type_a and file_type_b must differ")
    if raw["winner"] not in (raw["file_type_a"], raw["file_type_b"]):
        raise PrecedenceError(f"{context}: winner must be one of the two file types")
    if raw["value_kind"] not in _VALID_VALUE_KIND:
        raise PrecedenceError(f"{context}: invalid value_kind")
    if raw["key"] == "*":
        raise PrecedenceError(
            f"{context}: section-wide entries (key='*') are a Phase-2 feature; "
            "provide a narrow per-key entry instead."
        )
    if "section_wide_verified" in raw:
        raise PrecedenceError(
            f"{context}: section_wide_verified is a Phase-2 feature."
        )
    return PrecedenceEntry(
        file_type_a=raw["file_type_a"],
        file_type_b=raw["file_type_b"],
        section=str(raw["section"]),
        key=str(raw["key"]),
        winner=raw["winner"],
        value_kind=raw["value_kind"],
        verified_on_build=str(raw["verified_on_build"]),
        verified_by=str(raw["verified_by"]),
        notes=str(raw.get("notes", "")).strip(),
    )


@dataclass
class PrecedenceTable:
    entries: tuple[PrecedenceEntry, ...]
    # Lookup keyed by unordered pair of file types + section + key.
    _by_key: dict[tuple[frozenset[str], str, str], PrecedenceEntry]

    @classmethod
    def from_entries(cls, entries: tuple[PrecedenceEntry, ...]) -> "PrecedenceTable":
        by_key: dict[tuple[frozenset[str], str, str], PrecedenceEntry] = {}
        for e in entries:
            k = (frozenset({e.file_type_a, e.file_type_b}), e.section, e.key)
            if k in by_key:
                raise PrecedenceError(
                    f"duplicate precedence entry for {sorted(k[0])} {e.section}/{e.key}"
                )
            by_key[k] = e
        return cls(entries=entries, _by_key=by_key)

    def narrow(
        self, file_type_a: str, file_type_b: str, section: str, key: str
    ) -> PrecedenceEntry | None:
        return self._by_key.get((frozenset({file_type_a, file_type_b}), section, key))


def load_precedence(path: pathlib.Path) -> PrecedenceTable:
    if not path.exists():
        raise PrecedenceError(f"precedence file does not exist: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        raise PrecedenceError(f"{path}: precedence must be a YAML list")
    entries = tuple(_parse_entry(item, f"{path.name}[{i}]") for i, item in enumerate(raw))
    return PrecedenceTable.from_entries(entries)
