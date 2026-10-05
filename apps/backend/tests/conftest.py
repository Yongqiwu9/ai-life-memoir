import os

os.environ.setdefault("JWT_SECRET_KEY", "pytest-test-secret-key-at-least-32-bytes-long")
os.environ.setdefault("JWT_ALGORITHM", "HS256")
os.environ.setdefault("ACCESS_TOKEN_EXPIRE_MINUTES", "30")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import models_import  # noqa: F401
from app.database.base import Base
from app.database.session import get_db
from app.main import app


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Keep the default suite fast while making explicit integration runs safe."""
    integration_items = [item for item in items if item.get_closest_marker("integration")]
    if not integration_items:
        return

    marker_expression = config.option.markexpr.replace(" ", "")
    if marker_expression == "integration":
        return

    skip = pytest.mark.skip(
        reason="PostgreSQL integration tests require `pytest -m integration` and TEST_DATABASE_URL"
    )
    for item in integration_items:
        item.add_marker(skip)


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture()
def client(db_session):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
