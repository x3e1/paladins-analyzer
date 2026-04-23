"""Structural guarantee: cleaned output is patch-only.

The builder returns dict[str, list[dict]], each op dict has the expected
keys, and no value is a multi-line 'full file' blob.
"""

from app.engine.cleaned_patch import build_cleaned_patch
from app.engine.evaluator import FindingData


def _fd(fix=None):
    return FindingData(
        id="rule.x",
        file_type="ChaosEngine",
        filename_hint="x.ini",
        section="Engine.Engine",
        key="bSmoothFrameRate",
        value="TRUE",
        severity="warning",
        issue_type="frame_pacing_risk",
        effect=("latency",),
        location="ChaosEngine (x.ini):1",
        fix=fix,
        confidence="high",
        key_status="observed",
        rationale="because.",
    )


def test_patch_shape_is_dict_of_lists_of_dicts():
    fix = {"op": "set", "section": "Engine.Engine", "key": "bSmoothFrameRate", "value": "FALSE"}
    patch = build_cleaned_patch([_fd(fix=fix)])
    assert isinstance(patch, dict)
    assert "ChaosEngine" in patch
    assert isinstance(patch["ChaosEngine"], list)
    op = patch["ChaosEngine"][0]
    assert set(op.keys()) == {"op", "section", "key", "value", "rule_id", "rationale"}


def test_multiline_fix_value_raises():
    import pytest

    fix = {"op": "set", "section": "Engine.Engine", "key": "X", "value": "line1\nline2"}
    with pytest.raises(RuntimeError):
        build_cleaned_patch([_fd(fix=fix)])


def test_findings_without_fix_do_not_create_patch_ops():
    patch = build_cleaned_patch([_fd(fix=None)])
    assert patch == {}
