import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from api.dependencies.dependencies import get_db
from api.models.models import Base
from main import app


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16") as container:
        yield container


@pytest.fixture(scope="session")
def engine(postgres_container):
    engine = create_engine(postgres_container.get_connection_url())
    with engine.connect() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        connection.commit()
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def db_connection(engine):
    connection = engine.connect()
    transaction = connection.begin()
    yield connection
    transaction.rollback()
    connection.close()


@pytest.fixture
def db_session(db_connection):
    session_factory = sessionmaker(bind=db_connection)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture(autouse=True)
def override_get_db(db_session):
    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    return TestClient(app)
