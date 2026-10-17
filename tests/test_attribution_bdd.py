"""Step definitions for ``features/attribution.feature``."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from pytest_bdd import given, parsers, scenarios, then, when

from channeltruth.services.attribution import Journey, Touch, attribute

scenarios("features/attribution.feature")

BASE = datetime(2026, 10, 10, 12, 0)


@pytest.fixture
def ctx() -> dict:
    return {}


@given(
    parsers.parse(
        'a two-step journey from "{first}" to "{second}" worth {revenue:d} cents'
    )
)
def two_touch_journey(ctx, first: str, second: str, revenue: int):
    ctx["journey"] = _journey([first, second], revenue)


@given(
    parsers.parse(
        'a three-step journey from "{first}" to "{second}" to "{third}" worth {revenue:d} cents'
    )
)
def three_touch_journey(ctx, first: str, second: str, third: str, revenue: int):
    ctx["journey"] = _journey([first, second, third], revenue)


def _journey(channels: list[str], revenue: int) -> Journey:
    touches = tuple(
        Touch(
            id=index + 1,
            channel=channel,
            occurred_at=BASE - timedelta(hours=(len(channels) - index) * 6),
        )
        for index, channel in enumerate(channels)
    )
    return Journey(
        conversion_uid="bdd-conv",
        visitor_id="bdd-visitor",
        revenue_cents=revenue,
        occurred_at=BASE,
        touches=touches,
    )


@when(parsers.parse('I attribute it with the "{model}" model'))
def run_model(ctx, model: str):
    ctx["report"] = attribute([ctx["journey"]], model)


@then(parsers.parse('"{channel}" is credited {cents:d} cents'))
def channel_credit(ctx, channel: str, cents: int):
    credit = ctx["report"].channels.get(channel)
    assert credit is not None, f"{channel} received no credit at all"
    assert credit.revenue_cents == cents


@then(parsers.parse("the credited total is {cents:d} cents"))
def credited_total(ctx, cents: int):
    assert sum(row.revenue_cents for row in ctx["report"].channels.values()) == cents
