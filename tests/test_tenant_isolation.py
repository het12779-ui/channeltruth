"""Tenancy is a security property; it gets its own module.

Attribution is especially sensitive: one account's journeys reveal that
account's customers, channels and revenue. A missing tenant predicate here is a
data breach, not a rendering bug.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from channeltruth.config import Settings
from channeltruth.db import Base
from channeltruth.main import create_app
from tests.conftest import add_conversion, add_touch

DAY = "2026-10-09"


def test_reports_are_tenant_scoped(meridian_client, trailhead_client):
    add_touch(meridian_client, "v1", "google", f"{DAY}T10:00:00Z", uid="iso-t")
    add_conversion(meridian_client, "v1", 90_000, f"{DAY}T12:00:00Z", uid="iso-c")

    meridian = meridian_client.get(
        "/api/v1/attribution", params={"from": DAY, "to": DAY}
    ).json()
    assert meridian["totals"]["revenue_cents"] == 90_000

    trailhead = trailhead_client.get(
        "/api/v1/attribution", params={"from": DAY, "to": DAY}
    ).json()
    assert trailhead["totals"]["journeys"] == 0
    assert trailhead["totals"]["revenue_cents"] == 0


def test_cross_tenant_journey_is_a_404(meridian_client, trailhead_client):
    add_touch(meridian_client, "v1", "google", f"{DAY}T10:00:00Z", uid="iso-t2")
    add_conversion(meridian_client, "v1", 90_000, f"{DAY}T12:00:00Z", uid="iso-c2")

    assert meridian_client.get("/api/v1/attribution/journeys/iso-c2").status_code == 200
    # 404, not 403: never confirm that another tenant's conversion exists.
    assert trailhead_client.get("/api/v1/attribution/journeys/iso-c2").status_code == 404


def test_compare_is_tenant_scoped(meridian_client, trailhead_client):
    add_touch(meridian_client, "v1", "google", f"{DAY}T10:00:00Z", uid="iso-t3")
    add_conversion(meridian_client, "v1", 10_000, f"{DAY}T12:00:00Z", uid="iso-c3")

    body = trailhead_client.get(
        "/api/v1/attribution/compare", params={"from": DAY, "to": DAY}
    ).json()
    assert body["journeys"] == 0
    assert set(body["total_by_model"].values()) == {0}


def test_visitor_ids_are_not_global(meridian_client, trailhead_client):
    """The same visitor_id in two tenants must not share a journey."""
    add_touch(meridian_client, "shared-visitor", "display", "2026-10-01T10:00:00Z", uid="a-t")
    add_conversion(meridian_client, "shared-visitor", 50_000, f"{DAY}T12:00:00Z", uid="a-c")

    add_touch(trailhead_client, "shared-visitor", "display", "2026-10-01T11:00:00Z", uid="b-t")
    add_conversion(trailhead_client, "shared-visitor", 20_000, f"{DAY}T13:00:00Z", uid="b-c")

    meridian = meridian_client.get(
        "/api/v1/attribution", params={"from": DAY, "to": DAY}
    ).json()
    trailhead = trailhead_client.get(
        "/api/v1/attribution", params={"from": DAY, "to": DAY}
    ).json()

    assert meridian["totals"]["revenue_cents"] == 50_000
    assert trailhead["totals"]["revenue_cents"] == 20_000


def test_unknown_api_key_is_rejected(client):
    assert client.get("/api/v1/attribution", headers={"X-API-Key": "nope"}).status_code == 401


def test_missing_credentials_are_rejected(client):
    assert client.get("/api/v1/attribution").status_code == 401


def test_demo_header_fails_when_demo_mode_is_off(tenants):
    strict_app = create_app(Settings(demo_mode=False, seed_demo_data=False))
    with TestClient(strict_app) as strict_client:
        response = strict_client.get(
            "/api/v1/attribution", headers={"X-Account-Id": str(tenants[0].id)}
        )
    assert response.status_code == 401


def test_every_business_table_has_an_account_column():
    exempt = {"accounts"}
    missing = [
        table.name
        for table in Base.metadata.sorted_tables
        if table.name not in exempt and "account_id" not in table.c
    ]
    assert missing == [], f"tables missing account_id: {missing}"
