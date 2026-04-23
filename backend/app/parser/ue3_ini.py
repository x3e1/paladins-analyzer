"""UE3-aware .ini parser.

Differences from stdlib ``configparser``:
- Duplicate keys are legal; every occurrence is retained with line provenance.
- Array operators ``+Key=``, ``-Key=``, ``.Key=``, ``!Key``.
- Sections may repeat within a file.
- Values may contain ``=``, quoted strings, and parenthesised struct literals.
- Comments start with ``;`` or ``//`` at the line start (optionally indented).
- BOM + CRLF tolerant.

Typed-value inference is intentionally conservative: we coerce ``True``/``False``
and numeric literals, but leave everything else as the raw string. Rules can
always consult ``raw_value`` for exact-string matching.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

from .tokens import (
    ArrayOp,
    BlankToken,
    CommentToken,
    EntryToken,
    SectionToken,
    Token,
    UnknownToken,
    classify_line,
)

TypedValue = Union[bool, int, float, str]


@dataclass(frozen=True)
class Entry:
    line_no: int
    op: ArrayOp
    key: str
    raw_value: str
    typed_value: TypedValue


@dataclass
class ParsedDoc:
    filename_hint: str
    raw_lines: list[str]
    # Section name -> list of entries in source order.
    sections: dict[str, list[Entry]] = field(default_factory=dict)
    # Tokens that could not be parsed; surfaced in the report.
    warnings: list[UnknownToken] = field(default_factory=list)


def _strip_bom(text: str) -> str:
    if text.startswith("\ufeff"):
        return text[1:]
    return text


def _infer_typed_value(raw: str) -> TypedValue:
    lower = raw.strip().lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    s = raw.strip()
    # Integer?
    try:
        if s and (s[0] in "+-" and s[1:].isdigit()) or s.isdigit():
            return int(s)
    except (ValueError, IndexError):
        pass
    # Float?
    try:
        if any(c in s for c in ".eE"):
            return float(s)
    except ValueError:
        pass
    return raw


def parse_text(text: str, filename_hint: str = "<pasted>") -> ParsedDoc:
    """Parse a full .ini text buffer into a ParsedDoc."""
    text = _strip_bom(text)
    # ``splitlines`` handles CRLF, LF, and CR uniformly.
    raw_lines = text.splitlines()
    doc = ParsedDoc(filename_hint=filename_hint, raw_lines=raw_lines)
    current_section: str | None = None

    for idx, raw in enumerate(raw_lines, start=1):
        token: Token = classify_line(raw, idx)
        if isinstance(token, BlankToken) or isinstance(token, CommentToken):
            continue
        if isinstance(token, SectionToken):
            current_section = token.name
            # Ensure the section exists even if it has no entries.
            doc.sections.setdefault(current_section, [])
            continue
        if isinstance(token, EntryToken):
            if current_section is None:
                # UE3 tolerates preamble keys above any header only rarely;
                # treat them as warnings rather than silently dropping.
                doc.warnings.append(
                    UnknownToken(line_no=token.line_no, text=raw, reason="entry_before_section")
                )
                continue
            entry = Entry(
                line_no=token.line_no,
                op=token.op,
                key=token.key,
                raw_value=token.raw_value,
                typed_value=_infer_typed_value(token.raw_value),
            )
            doc.sections[current_section].append(entry)
            continue
        if isinstance(token, UnknownToken):
            doc.warnings.append(token)
            continue

    return doc


def parse_bytes(data: bytes, filename_hint: str = "<pasted>") -> ParsedDoc:
    """Parse bytes. Accepts UTF-8 and UTF-16 (LE/BE) with BOM."""
    if data.startswith(b"\xff\xfe"):
        text = data.decode("utf-16-le")[1:]  # strip BOM char after decode
    elif data.startswith(b"\xfe\xff"):
        text = data.decode("utf-16-be")[1:]
    else:
        text = data.decode("utf-8-sig", errors="replace")
    return parse_text(text, filename_hint=filename_hint)


# Convenience: resolve array-op composition for a single key.
def compose_array(entries: list[Entry], key: str) -> list[str]:
    """Apply UE3 array-op semantics for a given key across a list of entries.

    Semantics:
      - ``!Key`` clears the accumulated list.
      - ``+Key=X`` appends X if not already present (case-sensitive).
      - ``-Key=X`` removes all occurrences of X.
      - ``.Key=X`` appends X always (duplicates allowed).
      - ``set`` (plain ``Key=X``) is treated as a plain append for arrays;
        callers dealing with scalars should filter for op=="set" before
        calling this function.

    Returns the composed list in application order.
    """
    result: list[str] = []
    for e in entries:
        if e.key != key:
            continue
        if e.op == "!":
            result.clear()
        elif e.op == "+":
            if e.raw_value not in result:
                result.append(e.raw_value)
        elif e.op == "-":
            result = [x for x in result if x != e.raw_value]
        elif e.op == ".":
            result.append(e.raw_value)
        else:  # 'set'
            result.append(e.raw_value)
    return result
