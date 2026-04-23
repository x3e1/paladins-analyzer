"""Paladins known-key registry loader.

Every entry carries explicit provenance. Entries without the required
provenance fields are rejected at load time so the runtime never sees a
partially documented key.
"""

from __future__ import annotations

import datetime
import pathlib
from dataclasses import dataclass
from typing import Literal

import yaml

KeyStatus = Literal["confirmed", "observed"]
KeySource = Literal["clean_install", "wild_config", "dev_cross_reference"]
ValueKind = Literal["scalar", "array", "struct"]


class RegistryError(ValueError):
    pass


@dataclass(frozen=True)
class RegistryEntry:
    file_type: str
    section: str
    key: str
    status: KeyStatus
    source: KeySource
    game_build: str
    first_seen: datetime.date
    value_kind: ValueKind
    last_verified: datetime.date | None = None
    notes: str = ""


_VALID_FILE_TYPES = {
    "ChaosEngine",
    "ChaosGame",
    "ChaosInput",
    "ChaosLightmass",
    "ChaosSystemSettings",
    "ChaosUI",
}
_VALID_STATUS = {"confirmed", "observed"}
_VALID_SOURCE = {"clean_install", "wild_config", "dev_cross_reference"}
_VALID_VALUE_KIND = {"scalar", "array", "struct"}


def _parse_date(raw: object, context: str) -> datetime.date:
    if isinstance(raw, datetime.date):
        return raw
    if isinstance(raw, str):
        try:
            return datetime.date.fromisoformat(raw)
        except ValueError as e:
            raise RegistryError(f"{context}: invalid ISO date '{raw}'") from e
    raise RegistryError(f"{context}: expected date, got {type(raw).__name__}")


def _parse_entry(raw: dict, context: str) -> RegistryEntry:
    if not isinstance(raw, dict):
        raise RegistryError(f"{context}: entry must be a mapping")
    for required in ("file_type", "section", "key", "status", "source", "game_build", "first_seen", "value_kind"):
        if required not in raw:
            raise RegistryError(f"{context}: missing required field '{required}'")

    ft = raw["file_type"]
    if ft not in _VALID_FILE_TYPES:
        raise RegistryError(f"{context}: invalid file_type '{ft}'")
    status = raw["status"]
    if status not in _VALID_STATUS:
        raise RegistryError(f"{context}: invalid status '{status}'")
    source = raw["source"]
    if source not in _VALID_SOURCE:
        raise RegistryError(f"{context}: invalid source '{source}'")
    value_kind = raw["value_kind"]
    if value_kind not in _VALID_VALUE_KIND:
        raise RegistryError(f"{context}: invalid value_kind '{value_kind}'")

    first_seen = _parse_date(raw["first_seen"], f"{context}.first_seen")

    last_verified = None
    if "last_verified" in raw and raw["last_verified"] is not None:
        last_verified = _parse_date(raw["last_verified"], f"{context}.last_verified")
    if status == "confirmed" and last_verified is None:
        raise RegistryError(f"{context}: status=confirmed requires last_verified")

    return RegistryEntry(
        file_type=ft,
        section=str(raw["section"]),
        key=str(raw["key"]),
        status=status,
        source=source,
        game_build=str(raw["game_build"]),
        first_seen=first_seen,
        value_kind=value_kind,
        last_verified=last_verified,
        notes=str(raw.get("notes", "")).strip(),
    )


@dataclass
class KnownKeyRegistry:
    entries: tuple[RegistryEntry, ...]
    # Fast lookup: (file_type, section, key) -> entry
    _by_location: dict[tuple[str, str, str], RegistryEntry]
    # (file_type, section) -> set of known keys
    _keys_by_section: dict[tuple[str, str], frozenset[str]]

    @classmethod
    def from_entries(cls, entries: tuple[RegistryEntry, ...]) -> "KnownKeyRegistry":
        by_location: dict[tuple[str, str, str], RegistryEntry] = {}
        keys_by_section: dict[tuple[str, str], set[str]] = {}
        for e in entries:
            loc = (e.file_type, e.section, e.key)
            if loc in by_location:
                raise RegistryError(f"duplicate registry entry for {loc}")
            by_location[loc] = e
            keys_by_section.setdefault((e.file_type, e.section), set()).add(e.key)
        frozen = {k: frozenset(v) for k, v in keys_by_section.items()}
        return cls(entries=entries, _by_location=by_location, _keys_by_section=frozen)

    def lookup(self, file_type: str, section: str, key: str) -> RegistryEntry | None:
        return self._by_location.get((file_type, section, key))

    def known_keys_in(self, file_type: str, section: str) -> frozenset[str]:
        return self._keys_by_section.get((file_type, section), frozenset())

    def all_known_keys_for(self, file_type: str) -> list[RegistryEntry]:
        return [e for e in self.entries if e.file_type == file_type]


def load_registry(path: pathlib.Path) -> KnownKeyRegistry:
    if not path.exists():
        raise RegistryError(f"registry file does not exist: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or []
    if not isinstance(raw, list):
        raise RegistryError(f"{path}: registry must be a YAML list")
    entries = tuple(_parse_entry(item, f"{path.name}[{i}]") for i, item in enumerate(raw))
    return KnownKeyRegistry.from_entries(entries)
