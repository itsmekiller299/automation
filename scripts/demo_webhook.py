#!/usr/bin/env python3
"""Send a signed demo webhook and print the bot's reply.

Local default (.env.example) runs the inline queue, so the bot processes the
message before the HTTP response returns. With the Compose/Celery stack the
worker handles it asynchronously; this script waits briefly for the reply.

Examples:
    python scripts/demo_webhook.py
    python scripts/demo_webhook.py --channel instagram --text "What is the price of Orbit Mirror?"
    python scripts/demo_webhook.py --text "I want to talk to a human"
    python scripts/demo_webhook.py --secret "$APP_SECRET"

Environment fallbacks: APP_SECRET, ADMIN_API_KEY, DEMO_BASE_URL.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_local_env() -> None:
    """Fill unset variables from the project .env so `make demo` just works."""
    path = PROJECT_ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value


def build_whatsapp_payload(sender: str, text: str, name: str) -> dict:
    return {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "demo-waba",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "15550001111",
                                "phone_number_id": "demo-phone-number-id",
                            },
                            "contacts": [
                                {"profile": {"name": name}, "wa_id": sender}
                            ],
                            "messages": [
                                {
                                    "from": sender,
                                    "id": f"wamid.demo.{uuid.uuid4().hex}",
                                    "timestamp": str(int(time.time())),
                                    "type": "text",
                                    "text": {"body": text},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }


def build_instagram_payload(sender: str, text: str) -> dict:
    return {
        "object": "instagram",
        "entry": [
            {
                "id": "demo-ig-account",
                "time": int(time.time()),
                "messaging": [
                    {
                        "sender": {"id": sender},
                        "recipient": {"id": "demo-ig-account"},
                        "timestamp": int(time.time() * 1000),
                        "message": {
                            "mid": f"mid.demo.{uuid.uuid4().hex}",
                            "text": text,
                        },
                    }
                ],
            }
        ],
    }


def parse_args() -> argparse.Namespace:
    load_local_env()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.getenv("DEMO_BASE_URL", "http://localhost:8000"))
    parser.add_argument("--channel", choices=["whatsapp", "instagram"], default="whatsapp")
    parser.add_argument("--text", default="Where is my order ORD-1042?")
    parser.add_argument("--sender", default="919900000001")
    parser.add_argument("--name", default="Demo Customer")
    parser.add_argument(
        "--secret",
        default=os.getenv("APP_SECRET", ""),
        help="Meta app secret. Omit only when ALLOW_UNSIGNED_WEBHOOKS=true.",
    )
    parser.add_argument(
        "--api-key",
        default=os.getenv("ADMIN_API_KEY", ""),
        help="X-API-Key for dashboard routes when ADMIN_API_KEY is configured.",
    )
    parser.add_argument("--wait", type=float, default=4.0, help="Seconds to wait for async replies.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = (
        build_whatsapp_payload(args.sender, args.text, args.name)
        if args.channel == "whatsapp"
        else build_instagram_payload(args.sender, args.text)
    )
    body = json.dumps(payload, separators=(",", ":")).encode()
    headers = {"Content-Type": "application/json"}
    if args.secret:
        digest = hmac.new(args.secret.encode(), body, hashlib.sha256).hexdigest()
        headers["X-Hub-Signature-256"] = f"sha256={digest}"
        print("Signature: included")
    else:
        print("Signature: omitted (requires ALLOW_UNSIGNED_WEBHOOKS=true)")
    if args.api_key:
        headers["X-API-Key"] = args.api_key

    url = f"{args.base_url.rstrip('/')}/webhook/{args.channel}"
    try:
        response = httpx.post(url, content=body, headers=headers, timeout=20.0)
    except httpx.HTTPError as exc:
        print(f"Could not reach {url}: {exc}", file=sys.stderr)
        return 1

    print(f"POST {url} -> {response.status_code}")
    print(response.text)
    if response.status_code >= 400:
        return 1

    api_headers = {"X-API-Key": args.api_key} if args.api_key else {}
    deadline = time.time() + max(args.wait, 0)
    conversation = None
    while True:
        try:
            conversations = httpx.get(
                f"{args.base_url.rstrip('/')}/api/conversations",
                params={"channel": args.channel, "limit": 20},
                headers=api_headers,
                timeout=10.0,
            )
            conversations.raise_for_status()
            items = conversations.json()
        except httpx.HTTPError as exc:
            print(f"Could not read conversations: {exc}", file=sys.stderr)
            return 1
        match = next(
            (
                item
                for item in items
                if str((item.get("customer") or {}).get("external_id")) == args.sender
            ),
            None,
        )
        if match:
            conversation = httpx.get(
                f"{args.base_url.rstrip('/')}/api/conversations/{match['id']}",
                headers=api_headers,
                timeout=10.0,
            )
            conversation.raise_for_status()
            detail = conversation.json()
            if any(message["direction"] == "outbound" for message in detail["messages"]):
                break
        if time.time() >= deadline:
            break
        time.sleep(0.5)

    if conversation is None:
        print("No conversation found yet. Is the Celery worker running?")
        return 0

    detail = conversation.json()
    print(
        f"\nConversation {detail['id']}  status={detail['status']}  "
        f"intent={detail.get('last_intent')}  confidence={detail.get('last_confidence')}"
    )
    if detail.get("open_handoff"):
        handoff = detail["open_handoff"]
        print(f"Handoff: {handoff['reason']} ({handoff['priority']})")
    print("-" * 72)
    for message in detail["messages"][-6:]:
        who = "Customer" if message["direction"] == "inbound" else "Bot / agent"
        print(f"{who}: {message['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
