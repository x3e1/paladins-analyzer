"""AI explanation wrapper.

In Phase 1 this is a no-op by default: no real provider is wired. A
caller may pass a provider instance explicitly (e.g., the test suite's
stub) and the wrapper will invoke it, validating that it returns exactly
one ``ai_note`` per finding.
"""

from __future__ import annotations

from ..engine.evaluator import FindingData
from .provider import LLMProvider


class AIExplainer:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self._provider = provider

    @property
    def enabled(self) -> bool:
        return self._provider is not None

    def annotate(self, findings: list[FindingData]) -> list[str | None]:
        """Return a list of ``ai_note`` strings (or None) aligned with ``findings``.

        Disabled (no provider) -> list of None, same length as ``findings``.
        Enabled -> provider.explain() result, validated for length.
        """
        if self._provider is None:
            return [None] * len(findings)
        notes = self._provider.explain(findings)
        if len(notes) != len(findings):
            raise RuntimeError(
                f"provider {self._provider.name} returned {len(notes)} notes "
                f"for {len(findings)} findings"
            )
        return list(notes)
