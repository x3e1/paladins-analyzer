"""The AI explainer abstracts over provider choice.

With no provider, annotate() returns None for every finding.
With a stub provider, annotate() returns its strings (length-validated).
A provider returning the wrong length raises.
"""

import pytest

from app.ai.explainer import AIExplainer
from app.engine.evaluator import FindingData


def _fd(i):
    return FindingData(
        id=f"r.{i}",
        file_type="ChaosEngine",
        filename_hint="x.ini",
        section="S",
        key="K",
        value="v",
        severity="info",
        issue_type="unknown_key",
        effect=(),
        location="ChaosEngine (x.ini):1",
        fix=None,
        confidence="low",
        key_status="unknown",
        rationale="r",
    )


def test_no_provider_is_disabled_and_returns_none_list():
    explainer = AIExplainer()
    assert not explainer.enabled
    out = explainer.annotate([_fd(1), _fd(2)])
    assert out == [None, None]


def test_stub_provider_runs():
    class Stub:
        name = "stub"

        def explain(self, findings):
            return [f"note-{f.id}" for f in findings]

    explainer = AIExplainer(provider=Stub())
    assert explainer.enabled
    out = explainer.annotate([_fd(1), _fd(2)])
    assert out == ["note-r.1", "note-r.2"]


def test_provider_returning_wrong_length_raises():
    class Bad:
        name = "bad"

        def explain(self, findings):
            return []

    explainer = AIExplainer(provider=Bad())
    with pytest.raises(RuntimeError):
        explainer.annotate([_fd(1), _fd(2)])
