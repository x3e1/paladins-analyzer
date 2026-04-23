"""Every rule ships with red+green fixtures. This test asserts the rule
fires exactly on its red fixture and does not fire on its green fixture.
"""

import pathlib

import pytest

from app.engine.evaluator import evaluate
from app.engine.registry import load_registry
from app.engine.rules_loader import load_rules
from app.parser.content_classifier import classify
from app.parser.ue3_ini import parse_text

RULES_DIR = pathlib.Path(__file__).parent.parent / "app" / "data" / "rules"
REGISTRY_PATH = pathlib.Path(__file__).parent.parent / "app" / "data" / "paladins_known_keys.yaml"


def _all_rules():
    return load_rules(RULES_DIR)


def _registry():
    return load_registry(REGISTRY_PATH)


@pytest.mark.parametrize("rule", [r for r in _all_rules() if r.fixtures is not None], ids=lambda r: r.id)
def test_rule_red_fires_and_green_passes(rule):
    registry = _registry()
    rules = _all_rules()

    red_doc = parse_text(rule.fixtures.red, filename_hint=f"<{rule.id}.red>")
    green_doc = parse_text(rule.fixtures.green, filename_hint=f"<{rule.id}.green>")
    red_cls = classify(red_doc)
    green_cls = classify(green_doc)

    red_findings = evaluate(red_doc, red_cls, rules, registry)
    green_findings = evaluate(green_doc, green_cls, rules, registry)

    red_fires = any(f.id == rule.id for f in red_findings)
    green_fires = any(f.id == rule.id for f in green_findings)

    assert red_fires, f"rule {rule.id} did not fire on its red fixture"
    assert not green_fires, f"rule {rule.id} fired on its green fixture"
