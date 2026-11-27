import pytest

from app.repositories.outbox_repository import OutboxRepository

pytestmark = pytest.mark.integration


def test_outbox_dead_after_max_attempts(db_session):
    repo = OutboxRepository(db_session)
    msg = repo.enqueue(tenant_id=None, chat_id=123, payload={"text": "hi"}, dedupe_key="k1")
    db_session.commit()

    # simulate attempts
    for i in range(3):
        claimed = repo.claim_pending(limit=10, max_attempts=3)
        assert len(claimed) == 1
        m = claimed[0]
        repo.mark_failed(m, f"err{i+1}", max_attempts=3)
        db_session.refresh(msg)
        # force due for test determinism (production uses backoff)
        if msg.status != "dead":
            msg.next_attempt_at = msg.scheduled_at
            db_session.add(msg)
            db_session.commit()

    assert msg.status == "dead"
    assert msg.attempts == 3
    assert "err3" in (msg.last_error or "")
