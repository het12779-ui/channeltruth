from __future__ import annotations

import os
import tempfile

# Environment must be set before channeltruth.config/db are imported.
_TEST_DIR = tempfile.mkdtemp(prefix="channeltruth-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DIR}/test.db"
os.environ["CHANNELTRUTH_SEED"] = "0"
os.environ["CHANNELTRUTH_DEMO"] = "1"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from channeltruth.config import Settings  # noqa: E402
from channeltruth.db import Base, SessionLocal, engine  # noqa: E402
from channeltruth.main import create_app  # noqa: E402
from channeltruth.models import Account  # noqa: E402
from channeltruth.tenant import hash_api_key  # noqa: E402

MERIDIAN_KEY = "test-meridian-key"
TRAILHEAD_KEY = "test-trailhead-key"


@pytest.fixture(autouse=True)
def clean_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def session() -> Session:
    with SessionLocal() as db:
        yield db


@pytest.fixture
def tenants(session: Session) -> tuple[Account, Account]:
    first = Account(
        name="Meridian Home", slug="meridian", api_key_hash=hash_api_key(MERIDIAN_KEY)
    )
    second = Account(
        name="Trailhead Outdoors", slug="trailhead", api_key_hash=hash_api_key(TRAILHEAD_KEY)
    )
    session.add_all([first, second])
    session.commit()
    session.refresh(first)
    session.refresh(second)
    return first, second


@pytest.fixture
def app():
    return create_app(Settings(demo_mode=True, seed_demo_data=False))


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def meridian_client(client, tenants):
    client.headers.update({"X-API-Key": MERIDIAN_KEY})
    return client


@pytest.fixture
def trailhead_client(app, tenants):
    with TestClient(app) as test_client:
        test_client.headers.update({"X-API-Key": TRAILHEAD_KEY})
        yield test_client


def add_touch(client, visitor, channel, when, uid=None, kind="click"):
    return client.post(
        "/api/v1/touchpoints",
        json={
            "event_uid": uid or f"{visitor}-{channel}-{when}",
            "visitor_id": visitor,
            "channel": channel,
            "kind": kind,
            "occurred_at": when,
        },
    )


def add_conversion(client, visitor, revenue_cents, when, uid=None):
    return client.post(
        "/api/v1/conversions",
        json={
            "event_uid": uid or f"{visitor}-conv",
            "visitor_id": visitor,
            "revenue_cents": revenue_cents,
            "occurred_at": when,
        },
    )
