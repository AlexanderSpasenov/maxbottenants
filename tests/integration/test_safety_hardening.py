from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.core.crypto import decrypt_value, encrypt_value, mask_phone
from app.models.tenant import Tenant
from app.models.tenant_link import TenantLink
from app.repositories.outbox_repository import OutboxRepository
from app.repositories.tenant_link_repository import hash_token
from app.repositories.tenant_member_repository import TenantMemberRepository
from app.services.dialogs.service import DialogService

pytestmark = pytest.mark.integration


def test_pii_encrypted_and_masked(db_session):
    enc = encrypt_value("+79990001122")
    assert enc is not None
    assert enc != "+79990001122"
    assert decrypt_value(enc) == "+79990001122"
    masked = mask_phone("+79990001122")
    assert masked is not None
    assert masked.endswith("1122")
    assert "+79990001122" not in masked


def test_owner_token_redemption_creates_member(db_session):
    tenant = Tenant(
        slug="salon-z",
        display_name="Salon Z",
        status="active",
        timezone="Europe/Moscow",
        booking_mode="request_only",
    )
    db_session.add(tenant)
    db_session.flush()
    db_session.add(
        TenantLink(
            tenant_id=tenant.id,
            token_hash=hash_token("owner-token"),
            link_type="owner",
        )
    )
    db_session.commit()

    svc = DialogService(db_session)
    payload = {
        "update_type": "message_created",
        "message": {
            "mid": "m1",
            "chat_id": 500,
            "sender": {"user_id": 700},
            "body": {"text": "/start owner-token"},
        },
    }
    out = svc.handle_event(payload)
    assert any("владелец" in (m.get("text", "").lower()) for m in out)
    member = TenantMemberRepository(db_session).get_by_tenant_user(tenant.id, 700)
    assert member is not None
    assert member.role == "owner"


def test_outbox_backoff_and_dead_letter(db_session):
    repo = OutboxRepository(db_session)
    msg = repo.enqueue(tenant_id=None, chat_id=1, payload={"text": "hi"}, dedupe_key="k1")
    db_session.commit()

    claimed = repo.claim_pending(limit=10, max_attempts=2)
    assert len(claimed) == 1
    repo.mark_failed(claimed[0], "err1", max_attempts=2)
    db_session.refresh(msg)
    assert msg.status == "failed"
    assert msg.next_attempt_at > datetime.now(UTC) - timedelta(seconds=1)

    msg.status = "pending"
    msg.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.add(msg)
    db_session.commit()
    claimed2 = repo.claim_pending(limit=10, max_attempts=2)
    assert len(claimed2) == 1
    repo.mark_failed(claimed2[0], "err2", max_attempts=2)
    db_session.refresh(msg)
    assert msg.status == "dead"