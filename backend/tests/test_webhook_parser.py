from __future__ import annotations

from app.webhooks.parsers import parse_instagram, parse_whatsapp


def test_whatsapp_text_and_status_are_normalized():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "waba-1",
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "phone-1"},
                            "contacts": [
                                {"wa_id": "919900000001", "profile": {"name": "Siva"}}
                            ],
                            "messages": [
                                {
                                    "from": "919900000001",
                                    "id": "wamid.1",
                                    "timestamp": "1790000000",
                                    "type": "text",
                                    "text": {"body": "Where is my order ORD-1042?"},
                                }
                            ],
                        }
                    },
                    {
                        "value": {
                            "metadata": {"phone_number_id": "phone-1"},
                            "statuses": [{"id": "wamid.out", "status": "delivered"}],
                        }
                    },
                ],
            }
        ],
    }
    messages = parse_whatsapp(payload)
    assert len(messages) == 1
    message = messages[0]
    assert message.channel == "whatsapp"
    assert message.sender_id == "919900000001"
    assert message.recipient_id == "phone-1"
    assert message.text == "Where is my order ORD-1042?"
    assert message.message_type == "text"
    assert message.external_message_id == "wamid.1"
    assert message.customer_name == "Siva"


def test_whatsapp_media_with_caption_and_button():
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "metadata": {"phone_number_id": "phone-1"},
                            "messages": [
                                {
                                    "from": "123",
                                    "id": "wamid.media",
                                    "timestamp": "1790000000",
                                    "type": "image",
                                    "image": {"id": "media-1", "caption": "Is this the right lamp?"},
                                },
                                {
                                    "from": "123",
                                    "id": "wamid.button",
                                    "timestamp": "1790000001",
                                    "type": "button",
                                    "button": {"text": "Order status"},
                                },
                            ],
                        }
                    }
                ]
            }
        ]
    }
    messages = parse_whatsapp(payload)
    assert messages[0].message_type == "image"
    assert messages[0].text == "Is this the right lamp?"
    assert messages[0].metadata["media_id"] == "media-1"
    assert messages[1].message_type == "button"
    assert messages[1].text == "Order status"


def test_instagram_text_and_echo_handling():
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": "ig-account",
                "time": 1790000000000,
                "messaging": [
                    {
                        "sender": {"id": "customer-1"},
                        "recipient": {"id": "ig-account"},
                        "timestamp": 1790000000000,
                        "message": {"mid": "mid.1", "text": "hi, do you ship to Pune?"},
                    },
                    {
                        "sender": {"id": "ig-account"},
                        "recipient": {"id": "customer-1"},
                        "timestamp": 1790000001000,
                        "message": {"mid": "mid.echo", "text": "echo", "is_echo": True},
                    },
                    {
                        "sender": {"id": "customer-1"},
                        "recipient": {"id": "ig-account"},
                        "timestamp": 1790000002000,
                        "read": {"watermark": 1790000002000},
                    },
                ],
            }
        ],
    }
    messages = parse_instagram(payload)
    assert len(messages) == 1
    message = messages[0]
    assert message.channel == "instagram"
    assert message.sender_id == "customer-1"
    assert message.recipient_id == "ig-account"
    assert message.text == "hi, do you ship to Pune?"
    assert message.external_message_id == "mid.1"


def test_instagram_attachment_without_text_is_normalized():
    payload = {
        "entry": [
            {
                "id": "ig-account",
                "messaging": [
                    {
                        "sender": {"id": "customer-1"},
                        "recipient": {"id": "ig-account"},
                        "timestamp": 1790000000000,
                        "message": {
                            "mid": "mid.attach",
                            "attachments": [
                                {"type": "image", "payload": {"url": "https://example.com/a.jpg"}}
                            ],
                        },
                    }
                ],
            }
        ]
    }
    messages = parse_instagram(payload)
    assert len(messages) == 1
    assert messages[0].message_type == "image"
    assert messages[0].text == ""
