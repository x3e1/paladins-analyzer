import pathlib

from app.engine.registry import load_registry


def test_registry_has_required_provenance_fields():
    path = pathlib.Path(__file__).parent.parent / "app" / "data" / "paladins_known_keys.yaml"
    registry = load_registry(path)
    assert registry.entries, "registry must not be empty"
    for e in registry.entries:
        assert e.status in ("confirmed", "observed")
        assert e.source in ("clean_install", "wild_config", "dev_cross_reference")
        assert e.game_build  # non-empty string ('unknown' allowed)
        assert e.first_seen is not None
        assert e.value_kind in ("scalar", "array", "struct")
        if e.status == "confirmed":
            assert e.last_verified is not None, (
                f"confirmed entry {e.file_type}/{e.section}/{e.key} missing last_verified"
            )


def test_registry_rejects_confirmed_without_last_verified(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        """
- file_type: ChaosEngine
  section: Engine.Engine
  key: bSmoothFrameRate
  status: confirmed
  source: clean_install
  game_build: "OB66"
  first_seen: 2026-04-20
  value_kind: scalar
"""
    )
    import pytest
    from app.engine.registry import RegistryError

    with pytest.raises(RegistryError):
        load_registry(bad)
