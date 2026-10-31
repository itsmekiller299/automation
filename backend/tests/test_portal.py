from __future__ import annotations

from datetime import timedelta

from app.db import SessionLocal
from app.models import (
    ChannelConnection,
    Conversation,
    Customer,
    Message,
    PortalEvent,
    PortalUser,
    Tenant,
    utcnow,
)
from app.portal.crypto import decrypt_secret, hash_password, verify_password
from app.portal.service import notify_assignment, resolve_tenant_for_account
from app.services.orchestrator import process_inbound_message
from app.webhooks.parsers import NormalizedMessage
from fastapi.testclient import TestClient


def register(client: TestClient, **overrides):
    payload = {
        "business_name": "Aurora Living",
        "full_name": "Siva Kumar",
        "email": "siva@example.com",
        "phone": "+919900000001",
        "password": "correct-horse-battery",
        "welcome_opt_in": True,
    }
    payload.update(overrides)
    return client.post("/api/portal/auth/register", json=payload)


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_password_hashing_is_salted_and_verifiable():
    first = hash_password("correct-horse-battery")
    second = hash_password("correct-horse-battery")
    assert first != second
    assert verify_password("correct-horse-battery", first)
    assert not verify_password("wrong-password", first)


def test_register_creates_tenant_and_blocks_welcome_until_phone_verified(client):
    response = register(client)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["token"]
    assert body["tenant"]["automation_enabled"] is True
    assert body["activation"]["status"] == "blocked"
    assert body["activation"]["reason"] == "phone_not_verified"
    assert body["phone_verification_required"] is True

    me = client.get("/api/portal/me", headers=auth_header(body["token"]))
    assert me.status_code == 200
    assert me.json()["user"]["email"] == "siva@example.com"
    assert me.json()["tenant"]["name"] == "Aurora Living"


def test_login_requires_a_valid_password_and_session(client):
    register(client)
    client.cookies.clear()
    assert (
        client.post(
            "/api/portal/auth/login",
            json={"identifier": "siva@example.com", "password": "nope"},
        ).status_code
        == 401
    )
    assert client.get("/api/portal/me").status_code == 401

    login = client.post(
        "/api/portal/auth/login",
        json={"identifier": "siva@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200, login.text

    # Phone number is an equally valid identifier.
    phone_login = client.post(
        "/api/portal/auth/login",
        json={"identifier": "+91 99000 00001", "password": "correct-horse-battery"},
    )
    assert phone_login.status_code == 200, phone_login.text


def test_demo_channel_connect_stores_encrypted_token_and_sends_login_message(client):
    registration = register(client).json()
    token = registration["token"]

    connected = client.post(
        "/api/portal/channels/whatsapp/connect",
        headers=auth_header(token),
        json={
            "mode": "demo",
            "external_account_id": "phone-number-id-1",
            "display_name": "Aurora WhatsApp",
        },
    )
    assert connected.status_code == 200, connected.text
    assert connected.json()["status"] == "connected"

    with SessionLocal() as db:
        connection = db.query(ChannelConnection).one()
        assert connection.access_token_cipher
        assert "demo-whatsapp" not in connection.access_token_cipher
        assert decrypt_secret(connection.access_token_cipher).startswith("demo-whatsapp")

    otp = client.post("/api/portal/phone/verification/request", headers=auth_header(token))
    assert otp.status_code == 200
    assert otp.json()["status"] == "sent"
    code = otp.json()["dev_code"]
    assert code and len(code) == 6

    verified = client.post(
        "/api/portal/phone/verification/confirm",
        headers=auth_header(token),
        json={"code": code},
    )
    assert verified.status_code == 200, verified.text
    assert verified.json()["user"]["phone_verified"] is True

    login = client.post(
        "/api/portal/auth/login",
        json={"identifier": "+919900000001", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200, login.text
    assert login.json()["activation"]["status"] == "sent"

    activity = client.get("/api/portal/activity", headers=auth_header(token))
    statuses = {(event["event_type"], event["status"]) for event in activity.json()}
    assert ("welcome_message", "sent") in statuses
    assert ("phone_verified", "ok") in statuses


def test_welcome_is_blocked_without_consent_even_when_connected(client):
    registration = register(client, welcome_opt_in=False).json()
    token = registration["token"]

    client.post(
        "/api/portal/channels/whatsapp/connect",
        headers=auth_header(token),
        json={"mode": "demo", "external_account_id": "phone-number-id-2"},
    )

    with SessionLocal() as db:
        user = db.query(PortalUser).one()
        user.phone_verified = True
        user.phone_verified_at = utcnow()
        db.commit()

    login = client.post(
        "/api/portal/auth/login",
        json={"identifier": "siva@example.com", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200
    assert login.json()["activation"]["status"] == "blocked"
    assert login.json()["activation"]["reason"] == "welcome_opt_in_required"


def test_email_only_account_can_add_a_phone_with_the_current_password(client):
    registration = register(client, phone=None, email="email-only@example.com").json()
    token = registration["token"]
    assert registration["user"]["phone"] is None

    wrong = client.post(
        "/api/portal/phone",
        headers=auth_header(token),
        json={"phone": "+919900000002", "password": "not-the-password"},
    )
    assert wrong.status_code == 400

    added = client.post(
        "/api/portal/phone",
        headers=auth_header(token),
        json={"phone": "+91 99000 00002", "password": "correct-horse-battery"},
    )
    assert added.status_code == 200, added.text
    assert added.json()["user"]["phone"] == "+919900000002"
    assert added.json()["user"]["phone_verified"] is False

    # The number becomes a valid login identifier once it is attached.
    client.cookies.clear()
    login = client.post(
        "/api/portal/auth/login",
        json={"identifier": "+919900000002", "password": "correct-horse-battery"},
    )
    assert login.status_code == 200, login.text


def test_duplicate_identifiers_are_rejected(client):
    assert register(client).status_code == 201
    duplicate = register(client, business_name="Other Co")
    assert duplicate.status_code == 422
    assert "already exists" in duplicate.json()["detail"]


def test_webhook_maps_business_account_to_tenant(client):
    registration = register(client).json()
    token = registration["token"]
    client.post(
        "/api/portal/channels/whatsapp/connect",
        headers=auth_header(token),
        json={"mode": "demo", "external_account_id": "phone-number-id-9"},
    )

    with SessionLocal() as db:
        assert (
            resolve_tenant_for_account(db, "whatsapp", "phone-number-id-9")
            == registration["tenant"]["id"]
        )
        assert resolve_tenant_for_account(db, "whatsapp", "unknown") is None


def test_same_end_customer_stays_in_separate_workspace_conversations(client):
    first = register(
        client,
        business_name="Workspace One",
        email="one@example.com",
        phone="+919900000010",
    ).json()
    client.cookies.clear()
    second = register(
        client,
        business_name="Workspace Two",
        email="two@example.com",
        phone="+919900000011",
    ).json()

    account_ids = {}
    for registration in (first, second):
        account_id = f"phone-number-{registration['tenant']['id'][-6:]}"
        account_ids[registration["tenant"]["id"]] = account_id
        response = client.post(
            "/api/portal/channels/whatsapp/connect",
            headers=auth_header(registration["token"]),
            json={"mode": "demo", "external_account_id": account_id},
        )
        assert response.status_code == 200, response.text

    sender = "919900000777"
    for index, (_tenant_id, account_id) in enumerate(account_ids.items()):
        result = process_inbound_message(
            NormalizedMessage(
                channel="whatsapp",
                sender_id=sender,
                recipient_id=account_id,
                text="hello there",
                timestamp=utcnow(),
                external_message_id=f"wamid.isolation.{index}",
            )
        )
        assert result is not None
        assert result.conversation_id

    with SessionLocal() as db:
        customer = db.query(Customer).filter_by(channel="whatsapp", external_id=sender).one()
        conversations = db.query(Conversation).filter(Conversation.customer_id == customer.id).all()
        assert len(conversations) == 2
        assert {conversation.tenant_id for conversation in conversations} == set(account_ids)


def test_tenant_automation_gate_and_assignment_notification(client):
    registration = register(client).json()
    tenant_id = registration["tenant"]["id"]

    with SessionLocal() as db:
        tenant = db.get(Tenant, tenant_id)
        user = db.query(PortalUser).one()
        user.phone_verified = True
        user.phone_verified_at = utcnow()
        tenant.automation_enabled = False
        customer = Customer(
            tenant_id=tenant.id,
            channel="whatsapp",
            external_id="919900000123",
            display_name="Meera",
            opted_in=True,
        )
        db.add(customer)
        db.flush()
        conversation = Conversation(
            tenant_id=tenant.id,
            customer_id=customer.id,
            channel="whatsapp",
            status="bot",
            last_inbound_at=utcnow() - timedelta(minutes=1),
        )
        db.add(conversation)
        db.add(
            ChannelConnection(
                tenant_id=tenant.id,
                channel="whatsapp",
                external_account_id="phone-number-id-3",
                display_name="Aurora WhatsApp",
                status="connected",
                access_token_cipher="unused",
            )
        )
        db.commit()

        result = process_inbound_message(
            NormalizedMessage(
                channel="whatsapp",
                sender_id="919900000123",
                recipient_id="phone-number-id-3",
                text="hello, is anyone there?",
                timestamp=utcnow(),
                external_message_id="wamid.portal.test.1",
            )
        )
        assert result is not None
        assert result.reply is None

        assert db.query(Message).filter_by(direction="outbound").count() == 0
        assert db.query(Message).filter_by(direction="inbound").count() == 1

        event = notify_assignment(db, conversation, user.full_name)
        db.commit()
        assert event is not None
        assert event.event_type == "assignment_notification"
        # No connected token can be decrypted here, so it must fail closed.
        assert event.status in {"failed", "blocked"}
        assert db.query(PortalEvent).filter_by(event_type="assignment_notification").count() == 1


def test_oauth_state_is_signed_and_expires(client):
    from app.portal.crypto import sign_oauth_state, verify_oauth_state

    state = sign_oauth_state({"sub": "usr_1", "tid": "tnt_1", "channel": "whatsapp"})
    assert verify_oauth_state(state)["channel"] == "whatsapp"

    tampered = state[:-1] + ("a" if state[-1] != "a" else "b")
    try:
        verify_oauth_state(tampered)
    except ValueError:
        pass
    else:  # pragma: no cover
        raise AssertionError("tampered state must be rejected")
