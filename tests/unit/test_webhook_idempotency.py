from app.services.webhooks.idempotency import build_event_key, detect_event_type


def test_build_event_key_prefers_message_mid():
    payload = {
        "update_type": "message_created",
        "message": {"mid": "mid-123", "chat_id": 1},
    }
    assert build_event_key(payload) == "max:message_created:mid-123"


def test_build_event_key_uses_callback_id():
    payload = {
        "update_type": "message_callback",
        "callback": {"callback_id": "cb-1"},
    }
    assert build_event_key(payload) == "max:message_callback:cb-1"


def test_build_event_key_falls_back_to_hash_and_is_stable():
    payload = {
        "update_type": "message_created",
        "timestamp": 100,
        "message": {
            "chat_id": 10,
            "sender": {"user_id": 20},
            "body": {"text": "hi"},
        },
    }
    k1 = build_event_key(payload)
    k2 = build_event_key(dict(payload))
    assert k1 == k2
    assert k1.startswith("max:message_created:hash:")


def test_detect_event_type_defaults_unknown():
    assert detect_event_type({}) == "unknown"
    assert detect_event_type({"update_type": "bot_started"}) == "bot_started"
