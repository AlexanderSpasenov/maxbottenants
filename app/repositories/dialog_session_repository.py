import uuid

from sqlalchemy.orm import Session

from app.models.dialog_session import DialogSession


class DialogSessionRepository:
    def __init__(self, db: Session):
        self.db = db

    def get(self, chat_id: int) -> DialogSession | None:
        return self.db.get(DialogSession, chat_id)

    def upsert_current_tenant(
        self, *, chat_id: int, max_user_id: int, tenant_id: uuid.UUID
    ) -> DialogSession:
        session = self.get(chat_id)
        if session is None:
            session = DialogSession(
                chat_id=chat_id,
                max_user_id=max_user_id,
                current_tenant_id=tenant_id,
                current_step="menu",
                context={},
            )
            self.db.add(session)
        else:
            session.max_user_id = max_user_id
            session.current_tenant_id = tenant_id
        self.db.flush()
        return session

    def get_current_tenant_id(self, chat_id: int) -> uuid.UUID | None:
        session = self.get(chat_id)
        return session.current_tenant_id if session else None
