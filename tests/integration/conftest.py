import os

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app import models  # noqa: F401
from app.db.base import Base


def _integration_database_url() -> str | None:
    url = (
        os.getenv("TEST_DATABASE_URL")
        or os.getenv("DATABASE_URL_SYNC")
        or os.getenv("DATABASE_URL")
    )
    if not url:
        return None
    # Avoid accidentally running against production DB.
    if "maxbottenants_test" not in url and os.getenv("ALLOW_INTEGRATION_DB") != "1":
        return None
    return url


@pytest.fixture(scope="session")
def integration_engine():
    url = _integration_database_url()
    if not url:
        pytest.skip("Integration DB not configured; set TEST_DATABASE_URL to a *_test database")
    engine = create_engine(url, pool_pre_ping=True)
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture()
def db_session(integration_engine) -> Session:
    connection = integration_engine.connect()
    transaction = connection.begin()
    session = sessionmaker(bind=connection, expire_on_commit=False, autoflush=False)()
    try:
        yield session
    finally:
        session.close()
        if transaction.is_active:
            transaction.rollback()
        connection.close()
