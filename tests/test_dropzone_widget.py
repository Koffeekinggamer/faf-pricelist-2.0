"""HTML5 dropzone payload → DropUpload."""

from __future__ import annotations

import base64

from backend.dropzone_widget import drop_upload_from_payload


def test_drop_upload_from_payload_decodes_xlsx():
    data = b"PK\x03\x04-fake-xlsx"
    payload = {
        "name": "HopeWood_2026.xlsx",
        "size": len(data),
        "data_b64": base64.b64encode(data).decode("ascii"),
        "ts": 1,
    }
    got = drop_upload_from_payload(payload)
    assert got is not None
    assert got.filename == "HopeWood_2026.xlsx"
    assert got.data == data
    assert got.size == len(data)


def test_drop_upload_from_payload_rejects_junk():
    assert drop_upload_from_payload(None) is None
    assert drop_upload_from_payload({"name": "notes.txt", "data_b64": "YQ=="}) is None
    assert drop_upload_from_payload({"name": "x.xlsx", "data_b64": ""}) is None
