"""Upload hardening for the /analyze endpoint.

Enforces hard limits at the API boundary so the parser path is never
exposed to pathological or binary inputs.

  - Per-file size cap:      MAX_FILE_BYTES (default 1 MiB)
  - Per-request file count: MAX_FILES (default 10)
  - Per-request total:      MAX_TOTAL_BYTES (default 6 MiB)
  - Text-only sniff:        reject NUL bytes; reject >1% non-printable
                            in first 4 KiB (excluding CR/LF/TAB).
  - Encoding:               UTF-8 (with/without BOM) or UTF-16 LE/BE with
                            BOM. Everything else rejected as
                            unsupported_encoding.
  - Archive sniff:          reject ZIP/GZIP/7Z/TAR/RAR magic bytes.
  - Parser timeout:         hard 5s per file; enforced at the caller.

No bytes ever touch disk — everything is in-memory for the request.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

MAX_FILE_BYTES = int(os.environ.get("PALADINS_ANALYZER_MAX_FILE_BYTES", 1 * 1024 * 1024))
MAX_FILES = int(os.environ.get("PALADINS_ANALYZER_MAX_FILES", 10))
MAX_TOTAL_BYTES = int(os.environ.get("PALADINS_ANALYZER_MAX_TOTAL_BYTES", 6 * 1024 * 1024))
PARSE_TIMEOUT_SECONDS = float(os.environ.get("PALADINS_ANALYZER_PARSE_TIMEOUT", 5.0))

# Binary sniff: proportion of non-printable bytes (excluding CR/LF/TAB) in
# the first SNIFF_BYTES allowed before we call it not-text.
SNIFF_BYTES = 4096
BINARY_RATIO_THRESHOLD = 0.01  # >1% non-printable -> not_text


class UploadRejection(ValueError):
    """Raised when a single upload is rejected.

    ``reason`` is a short machine-readable code (e.g. ``file_too_large``)
    that the caller surfaces in ``skipped_files``.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


class RequestRejection(ValueError):
    """Raised when the whole request is rejected (count/aggregate caps).

    The API caller should translate to HTTP 400/413.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class AcceptedEncoding:
    name: str  # "utf-8", "utf-8-sig", "utf-16-le", "utf-16-be"
    bom_bytes: int  # number of BOM bytes to strip before decode


_ARCHIVE_MAGICS: tuple[tuple[bytes, str], ...] = (
    (b"PK\x03\x04", "zip"),
    (b"PK\x05\x06", "zip"),
    (b"PK\x07\x08", "zip"),
    (b"\x1f\x8b", "gzip"),
    (b"7z\xbc\xaf\x27\x1c", "7z"),
    (b"Rar!\x1a\x07\x00", "rar"),
    (b"Rar!\x1a\x07\x01\x00", "rar5"),
    # POSIX tar has "ustar" at offset 257; handled below.
)


def sniff_archive(data: bytes) -> str | None:
    for magic, name in _ARCHIVE_MAGICS:
        if data.startswith(magic):
            return name
    if len(data) >= 265 and data[257:262] == b"ustar":
        return "tar"
    return None


def sniff_encoding(data: bytes) -> AcceptedEncoding | None:
    """Return the encoding to use, or None if unsupported."""
    if data.startswith(b"\xef\xbb\xbf"):
        return AcceptedEncoding(name="utf-8-sig", bom_bytes=3)
    if data.startswith(b"\xff\xfe"):
        return AcceptedEncoding(name="utf-16-le", bom_bytes=2)
    if data.startswith(b"\xfe\xff"):
        return AcceptedEncoding(name="utf-16-be", bom_bytes=2)
    # No BOM: accept only if the bytes decode as UTF-8 (ASCII is a subset).
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return None
    return AcceptedEncoding(name="utf-8", bom_bytes=0)


def is_text(data: bytes) -> bool:
    """Heuristic for byte-level text detection (used for UTF-8/ASCII).

    NUL bytes are a hard reject; otherwise require the first SNIFF_BYTES
    to be >= (1 - BINARY_RATIO_THRESHOLD) printable/whitespace. Callers
    handling UTF-16 should decode first and check the decoded string
    via :func:`is_text_decoded` instead, because raw UTF-16 bytes contain
    interleaved NULs that trip the byte-level heuristic.
    """
    if b"\x00" in data[:SNIFF_BYTES]:
        return False
    sample = data[:SNIFF_BYTES]
    if not sample:
        return True
    bad = 0
    for b in sample:
        if b in (0x09, 0x0A, 0x0D):  # tab, lf, cr
            continue
        if 0x20 <= b <= 0x7E:
            continue
        if b >= 0x80:
            # Multi-byte UTF-8 continuation or high bytes — treat as OK;
            # real multi-byte validation is done by the encoding sniff.
            continue
        bad += 1
    return (bad / len(sample)) <= BINARY_RATIO_THRESHOLD


def is_text_decoded(text: str) -> bool:
    """Post-decode text check: reject control chars other than TAB/CR/LF."""
    sample = text[:SNIFF_BYTES]
    if not sample:
        return True
    bad = 0
    for ch in sample:
        c = ord(ch)
        if c in (0x09, 0x0A, 0x0D):
            continue
        if c < 0x20:
            bad += 1
            continue
        # All non-control code points are acceptable (includes every
        # printable ASCII and all non-ASCII Unicode).
    return (bad / len(sample)) <= BINARY_RATIO_THRESHOLD


def enforce_request_limits(n_files: int, total_bytes: int) -> None:
    """Raise RequestRejection if aggregate limits are exceeded."""
    if n_files > MAX_FILES:
        raise RequestRejection(
            "too_many_files",
            f"uploaded {n_files} files; maximum is {MAX_FILES}.",
        )
    if total_bytes > MAX_TOTAL_BYTES:
        raise RequestRejection(
            "request_too_large",
            f"aggregate {total_bytes} bytes exceeds {MAX_TOTAL_BYTES}.",
        )


def validate_upload(filename_hint: str, data: bytes) -> AcceptedEncoding:
    """Validate a single upload's size, type, and encoding.

    Returns the detected :class:`AcceptedEncoding`. Raises
    :class:`UploadRejection` if the file should be skipped.
    """
    if len(data) > MAX_FILE_BYTES:
        raise UploadRejection(
            "file_too_large",
            f"{filename_hint}: {len(data)} bytes exceeds {MAX_FILE_BYTES}.",
        )
    archive = sniff_archive(data)
    if archive is not None:
        raise UploadRejection(
            "archives_out_of_scope",
            f"{filename_hint}: detected {archive} archive; upload individual .ini files.",
        )
    enc = sniff_encoding(data)
    if enc is None:
        raise UploadRejection(
            "unsupported_encoding",
            f"{filename_hint}: only UTF-8 and UTF-16 (LE/BE with BOM) are accepted.",
        )
    # Text-ness check depends on encoding: UTF-8 checked on raw bytes
    # (fast, catches NULs); UTF-16 checked on the decoded string
    # (raw UTF-16 has interleaved NUL bytes that would trip is_text).
    if enc.name in ("utf-8", "utf-8-sig"):
        if not is_text(data[enc.bom_bytes:]):
            raise UploadRejection(
                "not_text",
                f"{filename_hint}: content appears to be binary (NUL byte or >1% non-printable).",
            )
    else:
        try:
            decoded = data[enc.bom_bytes:].decode(enc.name)
        except UnicodeDecodeError:
            raise UploadRejection("unsupported_encoding", f"{filename_hint}: decode failed.")
        if not is_text_decoded(decoded):
            raise UploadRejection(
                "not_text",
                f"{filename_hint}: decoded content contains too many control characters.",
            )
    return enc
