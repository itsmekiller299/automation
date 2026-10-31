from __future__ import annotations

import json

from app.security import compute_signature, verify_meta_signature


def test_compute_and_verify_signature():
    body = b'{"hello":"world"}'
    signature = compute_signature(body, "secret")
    ok, reason = verify_meta_signature(body, signature, app_secret="secret")
    assert ok is True
    assert reason == "ok"


def test_signature_mismatch_and_missing_header():
    body = b'{"hello":"world"}'
    ok, reason = verify_meta_signature(body, "sha256=deadbeef", app_secret="secret")
    assert ok is False
    assert reason == "signature_mismatch"

    ok, reason = verify_meta_signature(body, None, app_secret="secret")
    assert ok is False
    assert reason == "missing_signature"


def test_missing_secret_fails_closed_unless_explicitly_allowed():
    body = b"payload"
    ok, reason = verify_meta_signature(body, None, app_secret="", allow_unsigned=False)
    assert ok is False
    assert reason == "app_secret_not_configured"

    ok, reason = verify_meta_signature(body, None, app_secret="", allow_unsigned=True)
    assert ok is True
    assert reason == "unsigned_allowed"


def test_get_handshake(client):
    response = client.get(
        "/webhook/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "test-verify-token",
            "hub.challenge": "challenge-123",
        },
    )
    assert response.status_code == 200
    assert response.text == "challenge-123"

    rejected = client.get(
        "/webhook/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "challenge-123",
        },
    )
    assert rejected.status_code == 403


def test_post_rejects_bad_signature(client):
    payload = {"entry": []}
    response = client.post(
        "/webhook/instagram",
        content=json.dumps(payload),
        headers={"X-Hub-Signature-256": "sha256=bad"},
    )
    assert response.status_code == 401
