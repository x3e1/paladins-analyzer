"""Unknown-key classification: length-aware typo detection + placebo boundary.

Default outcome for a key not in the registry and not matched by any rule
is ``unknown_key``. We only promote to ``typoed_key`` / ``placebo`` /
``dead_entry`` / ``no_effect`` when rule-backed evidence exists.

Thresholds are bucketed by unknown-key length; DL <= 2 on a 5-char key
would be a near-random match and is explicitly ruled out.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .registry import KnownKeyRegistry, RegistryEntry


@dataclass(frozen=True)
class TypoCandidate:
    target: RegistryEntry
    distance: int
    same_section: bool
    shared_prefix_len: int
    hungarian_match: bool


def damerau_levenshtein(a: str, b: str) -> int:
    """Damerau-Levenshtein distance with transpositions."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    # Classic OSA-style algorithm with transposition.
    la, lb = len(a), len(b)
    # d[i][j] for i in 0..la, j in 0..lb
    d = [[0] * (lb + 1) for _ in range(la + 1)]
    for i in range(la + 1):
        d[i][0] = i
    for j in range(lb + 1):
        d[0][j] = j
    for i in range(1, la + 1):
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            d[i][j] = min(
                d[i - 1][j] + 1,      # deletion
                d[i][j - 1] + 1,      # insertion
                d[i - 1][j - 1] + cost,  # substitution
            )
            if (
                i > 1
                and j > 1
                and a[i - 1] == b[j - 2]
                and a[i - 2] == b[j - 1]
            ):
                d[i][j] = min(d[i][j], d[i - 2][j - 2] + 1)
    return d[la][lb]


def distance_threshold_for(unknown_key: str) -> int:
    n = len(unknown_key)
    if n <= 6:
        return 1
    if n <= 12:
        return 2
    return min(3, n // 5)


_HUNGARIAN_PREFIXES = ("b", "Max", "Min", "Num", "f", "i", "n", "s")


def _hungarian_match(a: str, b: str) -> bool:
    """Share a Hungarian-style prefix and have a matching camel-case core."""
    for p in _HUNGARIAN_PREFIXES:
        if a.startswith(p) and b.startswith(p):
            core_a = a[len(p):]
            core_b = b[len(p):]
            # Both cores start with uppercase camel or both don't, and their
            # first capitalised word matches.
            if not core_a or not core_b:
                continue
            if core_a[0].isupper() and core_b[0].isupper():
                first_a = _first_camel_word(core_a)
                first_b = _first_camel_word(core_b)
                if first_a == first_b and first_a:
                    return True
    return False


def _first_camel_word(s: str) -> str:
    out = [s[0]]
    for ch in s[1:]:
        if ch.isupper():
            break
        out.append(ch)
    return "".join(out)


def _shared_prefix_len(a: str, b: str) -> int:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n


@dataclass(frozen=True)
class TypoVerdict:
    """Result of typo analysis against a registry."""

    candidates: tuple[TypoCandidate, ...]  # best matches, ordered by distance asc
    ambiguous: bool                         # 2+ candidates tied on best score


def find_typo_candidates(
    unknown_key: str,
    unknown_section: str | None,
    file_type: str,
    registry: KnownKeyRegistry,
) -> TypoVerdict:
    """Return typo candidates from the registry for ``unknown_key``.

    A candidate must satisfy all of:
      - Damerau-Levenshtein distance within the length-bucketed threshold.
      - At least one of: same section, shared 3-char prefix, Hungarian match.
    """
    threshold = distance_threshold_for(unknown_key)
    out: list[TypoCandidate] = []
    for entry in registry.all_known_keys_for(file_type):
        dist = damerau_levenshtein(unknown_key, entry.key)
        if dist == 0:
            continue  # exact match: not a typo — caller should have resolved earlier.
        if dist > threshold:
            continue
        same_section = unknown_section is not None and entry.section == unknown_section
        prefix_len = _shared_prefix_len(unknown_key, entry.key)
        hungarian = _hungarian_match(unknown_key, entry.key)
        if not (same_section or prefix_len >= 3 or hungarian):
            continue
        out.append(
            TypoCandidate(
                target=entry,
                distance=dist,
                same_section=same_section,
                shared_prefix_len=prefix_len,
                hungarian_match=hungarian,
            )
        )
    if not out:
        return TypoVerdict(candidates=(), ambiguous=False)
    out.sort(key=lambda c: (c.distance, -c.shared_prefix_len, 0 if c.same_section else 1))
    best_dist = out[0].distance
    best_group = [c for c in out if c.distance == best_dist]
    return TypoVerdict(candidates=tuple(out), ambiguous=len(best_group) > 1)


def is_dead_array_op(
    entry_op: str,
    key: str,
    section_entries: Iterable,
) -> bool:
    """True if an array-op entry has no base array definition.

    ``section_entries`` are the entries in the same (section, file). The
    base array is any entry for the same key with op in {"set", "+", "."}.
    If there is no such entry AND the current op is "-", "!", or (an append
    before a clear that never gets base content), we flag dead.
    """
    if entry_op in {"set", "+", "."}:
        return False
    for e in section_entries:
        if e.key != key:
            continue
        if e.op in {"set", "+", "."}:
            return False
    return True
