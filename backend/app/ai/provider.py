"""LLM provider protocol.

The provider is a narrow interface: given a list of deterministic findings,
return a list of ``ai_note`` strings (same length) to attach. No provider
may create, remove, or mutate any other field on the finding.

Concrete providers live under ``ai/providers/``. Phase 1 ships with no
concrete provider wired into production; a stub implementation lives in
tests to prove the abstraction.
"""

from __future__ import annotations

from typing import Protocol

from ..engine.evaluator import FindingData


class LLMProvider(Protocol):
    """Protocol any AI provider must implement."""

    name: str

    def explain(self, findings: list[FindingData]) -> list[str]:
        """Return one ``ai_note`` per finding, same order."""
        ...
