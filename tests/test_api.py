from __future__ import annotations

from tests.conftest import add_conversion, add_touch

DAY = "2026-10-09"


def seed_journey(client, visitor="v1", revenue=100_000, channels=None, when=DAY):
    channels = channels or [
        ("display", "2026-10-01T10:00:00Z"),
        ("meta", "2026-10-05T10:00:00Z"),
        ("google", f"{when}T10:00:00Z"),
    ]
    for index, (channel, timestamp) in enumerate(channels):
        response = add_touch(client, visitor, channel, timestamp, uid=f"{visitor}-t{index}")
        assert response.status_code == 201, response.text

    response = add_conversion(client, visitor, revenue, f"{when}T12:00:00Z")
    assert response.status_code == 201, response.text
    return visitor


def report(client, model="linear", **params):
    query = {"model": model, "from": DAY, "to": DAY, **params}
    response = client.get("/api/v1/attribution", params=query)
    assert response.status_code == 200, response.text
    return response.json()


def test_touchpoint_ingest_is_idempotent(meridian_client):
    first = add_touch(meridian_client, "v1", "display", "2026-10-01T10:00:00Z", uid="t-1")
    assert first.json() == {
        "accepted": 1,
        "updated": 0,
        "duplicates": 0,
        "rejected": 0,
        "errors": [],
    }

    second = add_touch(meridian_client, "v1", "display", "2026-10-01T10:00:00Z", uid="t-1")
    assert second.json()["duplicates"] == 1
    assert second.json()["accepted"] == 0


def test_conversion_ingest_is_idempotent(meridian_client):
    add_conversion(meridian_client, "v1", 50_000, "2026-10-09T12:00:00Z", uid="c-1")
    again = add_conversion(meridian_client, "v1", 50_000, "2026-10-09T12:00:00Z", uid="c-1")
    assert again.json()["duplicates"] == 1


def test_spend_restatement_updates_the_row(meridian_client):
    payload = {"channel": "google", "day": DAY, "spend_cents": 50_000}

    created = meridian_client.post("/api/v1/spend", json=payload).json()
    assert created["accepted"] == 1

    same = meridian_client.post("/api/v1/spend", json=payload).json()
    assert same["duplicates"] == 1

    corrected = meridian_client.post(
        "/api/v1/spend", json={**payload, "spend_cents": 62_500}
    ).json()
    assert corrected["updated"] == 1

    body = report(meridian_client)
    google = next(row for row in body["channels"] if row["channel"] == "google")
    assert google["spend_cents"] == 62_500


def test_linear_report_splits_exactly_and_computes_roas(meridian_client):
    seed_journey(meridian_client)
    meridian_client.post(
        "/api/v1/spend", json={"channel": "google", "day": DAY, "spend_cents": 50_000}
    )

    body = report(meridian_client, "linear")

    assert body["totals"]["revenue_cents"] == 100_000
    assert body["totals"]["journeys"] == 1
    assert body["totals"]["roas"] == 2.0

    by_channel = {row["channel"]: row for row in body["channels"]}
    assert by_channel["display"]["revenue_cents"] == 33_334
    assert by_channel["meta"]["revenue_cents"] == 33_333
    assert by_channel["google"]["revenue_cents"] == 33_333
    assert by_channel["google"]["roas"] == 0.667

    # A channel with spend but no attributed revenue still appears, otherwise
    # the ROAS view hides the worst-performing line item.
    assert by_channel["google"]["spend_cents"] == 50_000


def test_first_and_last_touch_reports(meridian_client):
    seed_journey(meridian_client)

    first = {row["channel"]: row for row in report(meridian_client, "first_touch")["channels"]}
    assert first["display"]["revenue_cents"] == 100_000
    assert first["google"]["revenue_cents"] == 0

    last = {row["channel"]: row for row in report(meridian_client, "last_touch")["channels"]}
    assert last["google"]["revenue_cents"] == 100_000
    assert last["display"]["revenue_cents"] == 0


def test_model_comparison_runs_on_one_dataset(meridian_client):
    seed_journey(meridian_client)

    body = meridian_client.get(
        "/api/v1/attribution/compare", params={"from": DAY, "to": DAY}
    ).json()

    assert body["journeys"] == 1
    assert set(body["models"]) == {
        "first_touch",
        "last_touch",
        "linear",
        "time_decay",
        "position_based",
    }
    # Conservation: every model distributes the same money.
    assert set(body["total_by_model"].values()) == {100_000}

    google = next(row for row in body["channels"] if row["channel"] == "google")
    assert google["revenue_by_model"]["last_touch"] == 100_000
    assert google["revenue_by_model"]["first_touch"] == 0
    assert google["share_by_model"]["last_touch"] == 1.0


def test_journey_detail_credits_sum_to_revenue_per_model(meridian_client):
    seed_journey(meridian_client)

    body = meridian_client.get("/api/v1/attribution/journeys/v1-conv").json()
    assert body["revenue_cents"] == 100_000
    assert len(body["touches"]) == 3

    for model in body["models"]:
        credits = [touch["credits_by_model"][model] for touch in body["touches"]]
        assert sum(credits) == 100_000
        assert body["totals_by_model"][model] == 100_000


def test_journey_detail_is_404_for_unknown_conversion(meridian_client):
    assert meridian_client.get("/api/v1/attribution/journeys/nope").status_code == 404


def test_touches_outside_the_lookback_are_excluded(meridian_client):
    add_touch(meridian_client, "old", "display", "2026-08-01T10:00:00Z", uid="old-t")
    add_conversion(meridian_client, "old", 40_000, "2026-10-09T12:00:00Z", uid="old-conv")

    body = report(meridian_client, "linear")
    assert body["totals"]["revenue_cents"] == 0
    assert body["totals"]["unattributed_revenue_cents"] == 40_000
    assert body["totals"]["unattributed_conversions"] == 1


def test_journey_without_touches_is_still_attributable_to_no_channel(meridian_client):
    add_conversion(meridian_client, "ghost", 15_000, "2026-10-09T12:00:00Z", uid="ghost-conv")
    body = meridian_client.get("/api/v1/attribution/journeys/ghost-conv").json()
    assert body["touches"] == []
    assert body["totals_by_model"]["linear"] == 0


def test_invalid_model_is_rejected(meridian_client):
    response = meridian_client.get(
        "/api/v1/attribution", params={"model": "last_click", "from": DAY, "to": DAY}
    )
    assert response.status_code == 422


def test_invalid_ranges_are_rejected(meridian_client):
    reversed_range = meridian_client.get(
        "/api/v1/attribution", params={"from": DAY, "to": "2026-10-01"}
    )
    assert reversed_range.status_code == 422

    too_long = meridian_client.get(
        "/api/v1/attribution", params={"from": "2024-01-01", "to": DAY}
    )
    assert too_long.status_code == 422


def test_lookback_is_configurable_per_request(meridian_client):
    add_touch(meridian_client, "old", "display", "2026-08-15T10:00:00Z", uid="old-t2")
    add_conversion(meridian_client, "old", 10_000, "2026-10-09T12:00:00Z", uid="old-conv2")

    default = report(meridian_client, "linear")
    assert default["totals"]["revenue_cents"] == 0

    wide = report(meridian_client, "linear", lookback_days=90)
    assert wide["totals"]["revenue_cents"] == 10_000


def test_recent_conversions_feed(meridian_client):
    seed_journey(meridian_client)
    rows = meridian_client.get("/api/v1/attribution/journeys/recent").json()
    assert rows[0]["conversion_uid"] == "v1-conv"
    # Naive-UTC storage is re-emitted with an explicit offset (Pydantic uses Z).
    assert rows[0]["occurred_at"].endswith(("Z", "+00:00"))


def test_health_metrics_and_demo_accounts(meridian_client):
    assert meridian_client.get("/healthz").json() == {"status": "ok"}
    assert meridian_client.get("/readyz").status_code == 200

    metrics = meridian_client.get("/metrics").text
    assert "http_requests_total" in metrics

    accounts = meridian_client.get("/api/v1/demo/accounts").json()
    assert len(accounts) == 2
