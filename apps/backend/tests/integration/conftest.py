import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from test_support.database import TestDatabaseConfigurationError, resolve_test_database_url


@pytest.fixture(scope="session")
def postgres_engine() -> Engine:
    """Connect only to an explicitly named PostgreSQL test database."""
    try:
        database_url = resolve_test_database_url()
    except TestDatabaseConfigurationError as error:
        raise pytest.UsageError(str(error)) from None
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("SELECT 1")).scalar_one() == 1
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def db_session(postgres_engine: Engine) -> Session:
    """Rollback each test instead of dropping or truncating a database."""
    connection = postgres_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, autoflush=False, expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
