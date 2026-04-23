"""Report-mode filtering tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.engine.evaluator import FindingData
from app.engine.report_mode import (
    ACTIONABLE_INFO_ISSUE_TYPES,
    highest_severity,
    is_actionable,
    partition,
)
from app.main import app


def _fd(issue_type: str, severity: str = "info", confidence: str = "medium") -> FindingData:
    return FindingData(
        id=f"r.{issue_type}",
        file_type="ChaosEngine",
        filename_hint="x.ini",
        section="S",
        key="K",
        value="v",
        severity=severity,
        issue_type=issue_type,
        effect=(),
        location="ChaosEngine (x.ini):1",
        fix=None,
        confidence=confidence,
        key_status="observed",
        rationale="r",
    )


# ---------- actionable_only ----------


def test_warning_always_shown_in_actionable():
    assert is_actionable(_fd("stutter_risk", "warning", "medium"), "actionable_only")


def test_critical_always_shown_in_actionable():
    assert is_actionable(_fd("dangerous_streaming", "critical", "high"), "actionable_only")


def test_unknown_key_hidden_in_actionable():
    assert not is_actionable(_fd("unknown_key", "info", "low"), "actionable_only")


def test_uncertain_override_hidden_in_actionable():
    assert not is_actionable(_fd("uncertain_override", "info", "low"), "actionable_only")


def test_array_composition_hidden_in_actionable():
    assert not is_actionable(_fd("array_composition", "info", "medium"), "actionable_only")


def test_info_actionable_medium_shown():
    for t in ACTIONABLE_INFO_ISSUE_TYPES:
        if t == "typoed_key":
            continue  # special cased
        assert is_actionable(_fd(t, "info", "medium"), "actionable_only"), t


def test_info_actionable_low_confidence_hidden():
    # Low confidence info-severity findings of actionable types are hidden.
    for t in ACTIONABLE_INFO_ISSUE_TYPES:
        assert not is_actionable(_fd(t, "info", "low"), "actionable_only"), t


def test_typoed_key_low_confidence_hidden():
    assert not is_actionable(_fd("typoed_key", "info", "low"), "actionable_only")


def test_typoed_key_medium_shown():
    assert is_actionable(_fd("typoed_key", "info", "medium"), "actionable_only")


# ---------- verbose ----------


def test_verbose_shows_most_but_suppresses_inventory():
    assert is_actionable(_fd("unknown_key", "info", "low"), "verbose") is False
    assert is_actionable(_fd("array_composition", "info", "medium"), "verbose") is False
    assert is_actionable(_fd("typoed_key", "info", "low"), "verbose") is True
    assert is_actionable(_fd("stutter_risk", "warning", "medium"), "verbose") is True


# ---------- raw ----------


def test_raw_shows_everything():
    assert is_actionable(_fd("unknown_key", "info", "low"), "raw")
    assert is_actionable(_fd("uncertain_override", "info", "low"), "raw")
    assert is_actionable(_fd("array_composition", "info", "low"), "raw")


# ---------- partition ----------


def test_partition_counts_correctly():
    findings = [
        _fd("stutter_risk", "warning"),
        _fd("unknown_key", "info", "low"),
        _fd("unknown_key", "info", "low"),
        _fd("uncertain_override", "info", "low"),
        _fd("array_composition", "info", "medium"),
        _fd("typoed_key", "info", "low"),
        _fd("no_effect", "info", "medium"),
    ]
    kept, counts = partition(findings, "actionable_only")
    kept_ids = [f.id for f in kept]
    assert "r.stutter_risk" in kept_ids
    assert "r.no_effect" in kept_ids
    assert "r.unknown_key" not in kept_ids
    assert counts["unknown_keys"] == 2
    assert counts["uncertain_overrides"] == 1
    assert counts["array_compositions"] == 1
    assert counts["weak_typoed_keys"] == 1


def test_highest_severity():
    assert highest_severity([_fd("x", "info"), _fd("y", "warning")]) == "warning"
    assert highest_severity([_fd("x", "info"), _fd("y", "critical"), _fd("z", "warning")]) == "critical"
    assert highest_severity([]) is None


# ---------- end-to-end: default mode is actionable_only ----------


def test_default_mode_is_actionable_only_and_filters_unknown_keys():
    """Upload a ChaosEngine fragment with mostly unknown keys; verify that
    the default response suppresses them into the summary rather than
    dumping them into ranked_findings."""
    # One legitimate warning trigger (bSmoothFrameRate=TRUE + Max<60)
    # surrounded by twenty fabricated unknown keys.
    body = ["[Engine.Engine]", "bSmoothFrameRate=TRUE", "MaxSmoothedFrameRate=45"]
    for i in range(20):
        body.append(f"TotallyFakeKey{i}=1")
    content = ("\n".join(body) + "\n").encode("utf-8")

    with TestClient(app) as client:
        resp = client.post(
            "/analyze",
            files=[("files", ("ce.ini", content, "text/plain"))],
        )
    assert resp.status_code == 200, resp.text
    r = resp.json()
    assert r["mode"] == "actionable_only"
    # At most a small handful of actionable findings (the one rule fires).
    assert len(r["ranked_findings"]) <= 3
    # The 20 fabricated unknown keys are counted as suppressed.
    assert r["suppressed"]["unknown_keys"] >= 18
    # Summary fields present.
    assert r["summary"]["actionable_findings"] == len(r["ranked_findings"])
    assert r["summary"]["suppressed_findings"] >= 18


def test_raw_mode_includes_unknown_keys():
    body = ["[Engine.Engine]", "TotallyFake=1", "AnotherFake=2"]
    content = ("\n".join(body) + "\n").encode("utf-8")
    with TestClient(app) as client:
        resp = client.post(
            "/analyze?mode=raw",
            files=[("files", ("ce.ini", content, "text/plain"))],
        )
    r = resp.json()
    assert r["mode"] == "raw"
    unknown_in_list = [f for f in r["ranked_findings"] if f["issue_type"] == "unknown_key"]
    assert len(unknown_in_list) >= 2
