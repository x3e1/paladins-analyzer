"""Unknown vs placebo boundary.

Covers the four length/prefix cases from the plan:
  - short unknown key with DL=2 to a known key -> still unknown_key
  - short unknown key with DL=1 and same section -> typoed_key
  - long unknown key with DL=3 and shared prefix -> typoed_key
  - two known-key candidates tied on best score -> typoed_key ambiguous (low confidence)
  - novel key with no similarity and no rule match -> unknown_key
"""

import pathlib

from app.engine.evaluator import evaluate
from app.engine.placebo_detector import (
    distance_threshold_for,
    find_typo_candidates,
)
from app.engine.registry import RegistryEntry, KnownKeyRegistry, load_registry
from app.engine.rules_loader import load_rules
from app.parser.content_classifier import classify
from app.parser.ue3_ini import parse_text
import datetime


REGISTRY_PATH = pathlib.Path(__file__).parent.parent / "app" / "data" / "paladins_known_keys.yaml"
RULES_DIR = pathlib.Path(__file__).parent.parent / "app" / "data" / "rules"


def _reg():
    return load_registry(REGISTRY_PATH)


def test_distance_thresholds_are_length_aware():
    assert distance_threshold_for("Abc") == 1
    assert distance_threshold_for("Abcdef") == 1  # length 6
    assert distance_threshold_for("Abcdefgh") == 2  # length 8
    assert distance_threshold_for("A" * 15) == 3  # length 15 -> min(3, 3) = 3
    assert distance_threshold_for("A" * 25) == 3  # length 25 -> min(3, 5) = 3


def test_short_unknown_with_dl2_stays_unknown_key():
    # Fabricate a tiny registry with a short known key so DL=2 is above
    # the threshold-for-length-<=6 (which is 1).
    entry = RegistryEntry(
        file_type="ChaosEngine",
        section="Engine.Engine",
        key="Abcd",  # length 4 -> threshold 1
        status="observed",
        source="dev_cross_reference",
        game_build="x",
        first_seen=datetime.date(2026, 1, 1),
        value_kind="scalar",
    )
    reg = KnownKeyRegistry.from_entries((entry,))
    # "Xycd" differs from "Abcd" by 2 substitutions — DL=2, threshold=1 -> no candidate.
    verdict = find_typo_candidates("Xycd", "Engine.Engine", "ChaosEngine", reg)
    assert verdict.candidates == ()


def test_short_unknown_dl1_same_section_is_typo():
    # Real registry has "bSmoothFrameRate" — too long for this bucket. Use
    # a fabricated 6-char key so the short-bucket logic applies.
    entry = RegistryEntry(
        file_type="ChaosEngine",
        section="Engine.Engine",
        key="Foobar",  # length 6 -> threshold 1
        status="observed",
        source="dev_cross_reference",
        game_build="x",
        first_seen=datetime.date(2026, 1, 1),
        value_kind="scalar",
    )
    reg = KnownKeyRegistry.from_entries((entry,))
    verdict = find_typo_candidates("Foobaz", "Engine.Engine", "ChaosEngine", reg)
    assert verdict.candidates
    assert verdict.candidates[0].target.key == "Foobar"


def test_long_unknown_dl3_shared_prefix_is_typo():
    entry = RegistryEntry(
        file_type="ChaosSystemSettings",
        section="SystemSettings",
        key="MaxShadowResolution",  # 19 chars -> threshold 3
        status="observed",
        source="dev_cross_reference",
        game_build="x",
        first_seen=datetime.date(2026, 1, 1),
        value_kind="scalar",
    )
    reg = KnownKeyRegistry.from_entries((entry,))
    # "MaxShadowResolutionZZZ" = 22 chars, three pure insertions past the end
    # of "MaxShadowResolution" -> DL=3. Length threshold for 22 is 3, and the
    # full 19-char prefix is shared, so this should match.
    verdict = find_typo_candidates(
        "MaxShadowResolutionZZZ", "SystemSettings", "ChaosSystemSettings", reg
    )
    assert verdict.candidates
    assert verdict.candidates[0].target.key == "MaxShadowResolution"
    assert verdict.candidates[0].distance == 3


def test_tied_candidates_are_ambiguous():
    a = RegistryEntry(
        file_type="ChaosEngine",
        section="S",
        key="Foo",
        status="observed",
        source="dev_cross_reference",
        game_build="x",
        first_seen=datetime.date(2026, 1, 1),
        value_kind="scalar",
    )
    b = RegistryEntry(
        file_type="ChaosEngine",
        section="S",
        key="Foa",  # both DL=1 from "Fob"
        status="observed",
        source="dev_cross_reference",
        game_build="x",
        first_seen=datetime.date(2026, 1, 1),
        value_kind="scalar",
    )
    reg = KnownKeyRegistry.from_entries((a, b))
    verdict = find_typo_candidates("Fob", "S", "ChaosEngine", reg)
    assert verdict.ambiguous
    assert len(verdict.candidates) == 2


def test_novel_key_is_unknown_key_not_placebo():
    registry = _reg()
    rules = load_rules(RULES_DIR)
    text = "[Engine.Engine]\nAbsolutelyNovelUnrelatedIdentifier=1\n"
    doc = parse_text(text, filename_hint="x.ini")
    cls = classify(doc)
    findings = evaluate(doc, cls, rules, registry)
    matching = [f for f in findings if f.key == "AbsolutelyNovelUnrelatedIdentifier"]
    assert len(matching) == 1
    assert matching[0].issue_type == "unknown_key"
    assert matching[0].id == "placebo.unknown_key"
