"""Line classifier for UE3-style .ini files.

Each source line is classified into exactly one Token:
  - BlankToken
  - CommentToken  (line starting with ; or //, optionally indented)
  - SectionToken  ([Section.Name])
  - EntryToken    (Key=Value, with optional +/-/./! prefix)
  - UnknownToken  (unparseable — surfaced as a parse warning)

The parser consumes Tokens; keeping the classifier separate makes the
grammar testable in isolation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Union

ArrayOp = Literal["set", "+", "-", ".", "!"]


@dataclass(frozen=True)
class BlankToken:
    line_no: int


@dataclass(frozen=True)
class CommentToken:
    line_no: int
    text: str


@dataclass(frozen=True)
class SectionToken:
    line_no: int
    name: str


@dataclass(frozen=True)
class EntryToken:
    line_no: int
    op: ArrayOp
    key: str
    raw_value: str


@dataclass(frozen=True)
class UnknownToken:
    line_no: int
    text: str
    reason: str


Token = Union[BlankToken, CommentToken, SectionToken, EntryToken, UnknownToken]


_OP_PREFIXES: dict[str, ArrayOp] = {"+": "+", "-": "-", ".": ".", "!": "!"}


def classify_line(raw: str, line_no: int) -> Token:
    """Classify a single raw line (without the trailing newline)."""
    stripped = raw.strip()
    if not stripped:
        return BlankToken(line_no=line_no)

    if stripped.startswith(";") or stripped.startswith("//"):
        return CommentToken(line_no=line_no, text=stripped)

    if stripped.startswith("[") and stripped.endswith("]") and len(stripped) >= 2:
        name = stripped[1:-1].strip()
        if not name:
            return UnknownToken(line_no=line_no, text=raw, reason="empty_section_header")
        return SectionToken(line_no=line_no, name=name)

    # Entry: optional prefix op, then key[=value]
    first = stripped[0]
    if first in _OP_PREFIXES:
        op: ArrayOp = _OP_PREFIXES[first]
        remainder = stripped[1:].lstrip()
    else:
        op = "set"
        remainder = stripped

    # '!Key' with no '=' is a valid clear-array op.
    if op == "!" and "=" not in remainder:
        key = remainder.strip()
        if not key:
            return UnknownToken(line_no=line_no, text=raw, reason="bang_without_key")
        return EntryToken(line_no=line_no, op=op, key=key, raw_value="")

    if "=" not in remainder:
        return UnknownToken(line_no=line_no, text=raw, reason="no_equals")

    key, _, value = remainder.partition("=")
    key = key.strip()
    if not key:
        return UnknownToken(line_no=line_no, text=raw, reason="empty_key")

    # Values may legitimately contain further '=' characters (e.g. struct
    # literals: `(A=1,B=2)`). partition() already gave us everything after
    # the first '=' as `value`, so we keep it verbatim minus surrounding
    # whitespace.
    return EntryToken(line_no=line_no, op=op, key=key, raw_value=value.strip())
