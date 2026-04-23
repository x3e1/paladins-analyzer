"""Upload-boundary hardening tests.

Exercises the validators in :mod:`app.parser.upload_policy` directly plus
one end-to-end call through the FastAPI TestClient to confirm the wiring.
"""

from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.parser.upload_policy import (
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    RequestRejection,
    UploadRejection,
    enforce_request_limits,
    is_text,
    sniff_archive,
    sniff_encoding,
    validate_upload,
)


def test_file_too_large_rejected():
    data = b"A" * (MAX_FILE_BYTES + 1)
    with pytest.raises(UploadRejection) as exc:
        validate_upload("big.ini", data)
    assert exc.value.reason == "file_too_large"


def test_nul_byte_rejected_as_not_text():
    data = b"[Section]\nKey=value\x00\n"
    assert not is_text(data)
    with pytest.raises(UploadRejection) as exc:
        validate_upload("binary.ini", data)
    assert exc.value.reason == "not_text"


def test_high_nonprintable_ratio_rejected():
    # >1% non-printable in first 4 KiB: populate 100 non-printable bytes
    # in 4000 bytes of otherwise-printable content.
    printable = b"A" * 4000
    non_printable = bytes([0x01] * 100)
    data = printable[:3900] + non_printable + printable[:100]
    assert not is_text(data)


def test_zip_archive_rejected():
    zip_head = b"PK\x03\x04" + b"\x00" * 100
    assert sniff_archive(zip_head) == "zip"
    with pytest.raises(UploadRejection) as exc:
        validate_upload("archive.zip", zip_head)
    assert exc.value.reason == "archives_out_of_scope"


def test_gzip_archive_rejected():
    gz = b"\x1f\x8b\x08\x00" + b"\x00" * 64
    assert sniff_archive(gz) == "gzip"
    with pytest.raises(UploadRejection):
        validate_upload("a.gz", gz)


def test_tar_archive_rejected():
    tar = b"\x00" * 257 + b"ustar" + b"\x00" * 100
    assert sniff_archive(tar) == "tar"
    with pytest.raises(UploadRejection):
        validate_upload("a.tar", tar)


def test_unsupported_encoding_rejected():
    # Shift-JIS content that isn't valid UTF-8 and has no recognised BOM.
    data = "[S]\nK=テスト\n".encode("shift-jis")
    assert sniff_encoding(data) is None
    with pytest.raises(UploadRejection) as exc:
        validate_upload("sjis.ini", data)
    assert exc.value.reason == "unsupported_encoding"


def test_utf8_with_bom_accepted():
    data = "\ufeff[S]\nK=1\n".encode("utf-8")
    enc = sniff_encoding(data)
    assert enc is not None and enc.name == "utf-8-sig"
    validate_upload("bom.ini", data)  # does not raise


def test_utf16_le_with_bom_accepted():
    data = b"\xff\xfe" + "[S]\nK=1\n".encode("utf-16-le")
    enc = sniff_encoding(data)
    assert enc is not None and enc.name == "utf-16-le"
    validate_upload("utf16.ini", data)


def test_request_too_many_files():
    with pytest.raises(RequestRejection) as exc:
        enforce_request_limits(MAX_FILES + 1, 1024)
    assert exc.value.reason == "too_many_files"


def test_request_aggregate_too_large():
    with pytest.raises(RequestRejection) as exc:
        enforce_request_limits(2, MAX_TOTAL_BYTES + 1)
    assert exc.value.reason == "request_too_large"


def test_analyze_endpoint_skips_binary_file():
    with TestClient(app) as client:
    # Valid UTF-8 .ini alongside a binary file; the .ini should be
    # classified, the binary file should be skipped with reason=not_text.
        good = b"[Engine.Engine]\nbSmoothFrameRate=TRUE\nMaxSmoothedFrameRate=45\n"
        bad = b"\x00\x01\x02\x03" * 64
        resp = client.post(
            "/analyze",
            files=[
                ("files", ("good.ini", good, "text/plain")),
                ("files", ("evil.bin", bad, "application/octet-stream")),
            ],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        reasons = {s["filename_hint"]: s["reason"] for s in body["skipped_files"]}
        assert reasons.get("evil.bin") == "not_text"
        # good.ini still processed:
        assert any(c["filename_hint"] == "good.ini" for c in body["classification"])


def test_analyze_endpoint_rejects_too_many_files():
    with TestClient(app) as client:
        payload = [
            ("files", (f"f{i}.ini", b"[S]\nK=1\n", "text/plain"))
            for i in range(MAX_FILES + 1)
        ]
        resp = client.post("/analyze", files=payload)
        assert resp.status_code == 400
        body = resp.json()
        assert body["detail"]["reason"] == "too_many_files"


def test_analyze_endpoint_rejects_oversized_request():
    with TestClient(app) as client:
        # A single 1 MiB file < per-file cap but paired with a second
        # file big enough to push aggregate past MAX_TOTAL_BYTES.
        one = b"A" * (MAX_FILE_BYTES)
        resp = client.post(
            "/analyze",
            files=[
                ("files", (f"f{i}.ini", one, "text/plain"))
                for i in range(MAX_FILES)
            ],
        )
        # MAX_FILES copies of MAX_FILE_BYTES exceeds MAX_TOTAL_BYTES.
        assert resp.status_code == 413
        body = resp.json()
        assert body["detail"]["reason"] == "request_too_large"
