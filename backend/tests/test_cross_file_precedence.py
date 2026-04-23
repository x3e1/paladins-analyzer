"""Narrow precedence + uncertain_override + array_composition tests.

Section-wide precedence is a Phase-2 feature and not exercised here.
"""

import pathlib
import datetime

from app.engine.precedence import (
    PrecedenceEntry,
    PrecedenceError,
    PrecedenceTable,
    load_precedence,
)
from app.engine.registry import KnownKeyRegistry, RegistryEntry, load_registry
from app.engine.resolver import resolve
from app.parser.content_classifier import classify
from app.parser.ue3_ini import parse_text


REGISTRY_PATH = pathlib.Path(__file__).parent.parent / "app" / "data" / "paladins_known_keys.yaml"


def _make_registry_with_array_key():
    # ChaosInput/Engine.PlayerInput/Bindings is already in the seeded
    # registry with value_kind=array, so we don't re-add it here. Tests
    # that need additional file-type coverage augment inside the test body.
    return load_registry(REGISTRY_PATH)


def test_narrow_entry_fires_override():
    entry = PrecedenceEntry(
        file_type_a="ChaosEngine",
        file_type_b="ChaosSystemSettings",
        section="SystemSettings",
        key="MaxAnisotropy",
        winner="ChaosSystemSettings",
        value_kind="scalar",
        verified_on_build="2025.xx",
        verified_by="test fixture",
        notes="",
    )
    prec = PrecedenceTable.from_entries((entry,))
    reg = load_registry(REGISTRY_PATH)

    doc_a = parse_text("[SystemSettings]\nMaxAnisotropy=4\n", filename_hint="eng.ini")
    doc_b = parse_text("[SystemSettings]\nMaxAnisotropy=16\n", filename_hint="sys.ini")

    result = resolve(
        [(doc_a, "ChaosEngine"), (doc_b, "ChaosSystemSettings")], reg, prec
    )
    assert len(result.overrides) == 1
    ov = result.overrides[0]
    assert ov.winner.file_type == "ChaosSystemSettings"
    assert ov.winner.value == "16"
    assert ov.verified is True
    assert ov.precedence_source == "narrow"


def test_unverified_conflict_is_uncertain_override():
    prec = PrecedenceTable.from_entries(())  # empty
    reg = load_registry(REGISTRY_PATH)
    doc_a = parse_text("[SystemSettings]\nMaxAnisotropy=4\n", filename_hint="eng.ini")
    doc_b = parse_text("[SystemSettings]\nMaxAnisotropy=16\n", filename_hint="sys.ini")
    result = resolve(
        [(doc_a, "ChaosEngine"), (doc_b, "ChaosSystemSettings")], reg, prec
    )
    assert not result.overrides
    assert len(result.uncertain_overrides) == 1
    uc = result.uncertain_overrides[0]
    assert uc.section == "SystemSettings"
    assert uc.key == "MaxAnisotropy"


def test_array_key_gives_composition_never_override():
    prec = PrecedenceTable.from_entries(())
    reg = _make_registry_with_array_key()
    # Two different ChaosInput files writing Bindings array-op entries.
    # We need 2 distinct file TYPES to get cross-file engagement; in v1 an
    # array key typically lives in one file only. Use ChaosInput + ChaosEngine
    # to force the 2-type condition (contrived but exercises the code path).
    doc_a = parse_text(
        "[Engine.PlayerInput]\n+Bindings=(Name=\"A\")\n",
        filename_hint="input.ini",
    )
    doc_b = parse_text(
        "[Engine.PlayerInput]\n+Bindings=(Name=\"B\")\n",
        filename_hint="engine.ini",
    )
    # Register Bindings under ChaosEngine too so the value_kind lookup wins.
    base = list(reg.entries)
    base.append(
        RegistryEntry(
            file_type="ChaosEngine",
            section="Engine.PlayerInput",
            key="Bindings",
            status="observed",
            source="dev_cross_reference",
            game_build="x",
            first_seen=datetime.date(2026, 1, 1),
            value_kind="array",
        )
    )
    reg = KnownKeyRegistry.from_entries(tuple(base))

    result = resolve(
        [(doc_a, "ChaosInput"), (doc_b, "ChaosEngine")], reg, prec
    )
    assert not result.overrides
    assert not result.uncertain_overrides
    assert len(result.array_compositions) == 1
    ac = result.array_compositions[0]
    # Both values appear in the merged list (alphabetical load order by file type).
    assert set(ac.merged) == {'(Name="A")', '(Name="B")'}


def test_section_wide_precedence_is_rejected_at_load_time(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
- file_type_a: ChaosEngine
  file_type_b: ChaosSystemSettings
  section: SystemSettings
  key: "*"
  winner: ChaosSystemSettings
  value_kind: scalar
  verified_on_build: "2025.xx"
  verified_by: "attempt"
"""
    )
    import pytest
    with pytest.raises(PrecedenceError):
        load_precedence(bad)
