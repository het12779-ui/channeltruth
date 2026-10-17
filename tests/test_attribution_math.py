from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from channeltruth.services.attribution import (
    MODELS,
    Journey,
    Touch,
    allocate_cents,
    attribute,
    credit_journey,
    touch_weights,
    validate_model,
)

BASE = datetime(2026, 10, 10, 12, 0)


def touch(touch_id: int, channel: str, hours_before: float = 0.0) -> Touch:
    return Touch(
        id=touch_id,
        channel=channel,
        occurred_at=BASE - timedelta(hours=hours_before),
    )


def journey(channels: list[str], revenue: int = 1_000) -> Journey:
    touches = tuple(
        touch(index + 1, channel, hours_before=(len(channels) - index) * 6)
        for index, channel in enumerate(channels)
    )
    return Journey(
        conversion_uid="conv-1",
        visitor_id="v-1",
        revenue_cents=revenue,
        occurred_at=BASE,
        touches=touches,
    )


def test_unknown_model_is_rejected():
    with pytest.raises(ValueError, match="unknown attribution model"):
        validate_model("last_click")


def test_all_documented_models_are_implemented():
    assert set(MODELS) == {
        "first_touch",
        "last_touch",
        "linear",
        "time_decay",
        "position_based",
    }


def test_first_and_last_touch_weights():
    touches = [touch(1, "display", 30), touch(2, "google", 2)]
    assert touch_weights(touches, "first_touch") == [1.0, 0.0]
    assert touch_weights(touches, "last_touch") == [0.0, 1.0]


def test_linear_weights_are_equal():
    touches = [touch(index, "google", index) for index in range(4)]
    assert touch_weights(touches, "linear") == [1.0, 1.0, 1.0, 1.0]


def test_position_based_weights_favour_the_ends():
    touches = [touch(index, "google", index) for index in range(3)]
    weights = touch_weights(touches, "position_based")
    assert weights == pytest.approx([0.4, 0.2, 0.4])


def test_position_based_handles_one_and_two_touches():
    assert touch_weights([touch(1, "google")], "position_based") == [1.0]
    assert touch_weights(
        [touch(1, "display", 5), touch(2, "google")], "position_based"
    ) == [0.5, 0.5]


def test_time_decay_halves_a_week_old_touch():
    touches = [touch(1, "display", hours_before=7 * 24), touch(2, "google", hours_before=0)]
    weights = touch_weights(touches, "time_decay", half_life_days=7, occurred_at=BASE)
    assert weights[1] == pytest.approx(1.0)
    assert weights[0] == pytest.approx(0.5, abs=1e-9)


def test_time_decay_rejects_a_non_positive_half_life():
    with pytest.raises(ValueError):
        touch_weights([touch(1, "google")], "time_decay", half_life_days=0)


def test_no_touches_means_no_weights():
    assert touch_weights([], "linear") == []


# --- allocation: the invariant that matters --------------------------------


@pytest.mark.parametrize("total", [1, 3, 7, 99, 100, 101, 999, 12_345, 1_000_001])
@pytest.mark.parametrize("count", [1, 2, 3, 4, 5, 7])
def test_allocation_never_loses_or_invents_a_cent(total: int, count: int):
    weights = [0.4] + [0.2] * max(0, count - 2) + [0.4] if count >= 3 else [1.0] * count
    parts = allocate_cents(total, weights)
    assert len(parts) == count
    assert sum(parts) == total
    assert all(part >= 0 for part in parts)


def test_largest_remainder_breaks_ties_by_index():
    # 10 cents across 3 equal weights: 3.33 each -> the extra cent goes to index 0.
    assert allocate_cents(10, [1, 1, 1]) == [4, 3, 3]
    assert allocate_cents(1, [1, 1, 1]) == [1, 0, 0]


def test_all_zero_weights_fall_back_to_even_split():
    assert allocate_cents(9, [0, 0, 0]) == [3, 3, 3]


def test_negative_weights_are_treated_as_zero():
    assert allocate_cents(100, [-5, 1]) == [0, 100]


def test_zero_total_allocates_nothing():
    assert allocate_cents(0, [1, 1]) == [0, 0]


# --- whole journeys --------------------------------------------------------


def test_linear_split_is_exact_for_an_awkward_revenue():
    report = attribute([journey(["display", "meta", "google"], revenue=100_000)], "linear")
    assert report.channels["display"].revenue_cents == 33_334
    assert report.channels["meta"].revenue_cents == 33_333
    assert report.channels["google"].revenue_cents == 33_333
    assert sum(row.revenue_cents for row in report.channels.values()) == 100_000


def test_first_and_last_touch_on_the_same_journey():
    data = [journey(["display", "google"], revenue=50_000)]

    first = attribute(data, "first_touch")
    assert first.channels["display"].revenue_cents == 50_000
    assert first.channels["google"].revenue_cents == 0

    last = attribute(data, "last_touch")
    assert last.channels["google"].revenue_cents == 50_000
    assert last.channels["display"].revenue_cents == 0


def test_position_based_splits_three_touches_40_20_40():
    report = attribute([journey(["display", "meta", "google"], revenue=1_000)], "position_based")
    assert report.channels["display"].revenue_cents == 400
    assert report.channels["meta"].revenue_cents == 200
    assert report.channels["google"].revenue_cents == 400


def test_conversion_credit_sums_to_one_per_journey():
    report = attribute([journey(["display", "meta", "google"])], "time_decay")
    assert round(sum(row.conversion_credit for row in report.channels.values()), 9) == 1.0


def test_conversions_without_touches_are_unattributed():
    empty = Journey(
        conversion_uid="conv-2",
        visitor_id="v-2",
        revenue_cents=25_000,
        occurred_at=BASE,
        touches=(),
    )
    report = attribute([journey(["google"], revenue=10_000), empty], "linear")

    assert report.revenue_cents == 10_000
    assert report.unattributed_revenue_cents == 25_000
    assert report.unattributed_conversions == 1
    assert report.journeys == 2


def test_every_model_conserves_total_revenue():
    data = [
        journey(["display", "meta", "google"], revenue=99_999),
        journey(["email", "direct"], revenue=1),
        journey(["google"], revenue=1234),
    ]
    for model in MODELS:
        report = attribute(data, model)
        assert report.revenue_cents == 101_234
        assert sum(row.revenue_cents for row in report.channels.values()) == 101_234


def test_credit_journey_explains_each_touch():
    data = journey(["display", "meta", "google"], revenue=1_000)
    credits = credit_journey(data, "position_based", half_life_days=7)

    assert [credit.credit_cents for credit in credits] == [400, 200, 400]
    assert sum(credit.weight for credit in credits) == pytest.approx(1.0)
    assert credits[0].touch.channel == "display"


def test_time_decay_favours_the_recent_touch_end_to_end():
    # Two weeks old = exactly two half-lives, so the older touch keeps 25%.
    explicit = Journey(
        conversion_uid="conv-decay",
        visitor_id="v-decay",
        revenue_cents=10_000,
        occurred_at=BASE,
        touches=(
            Touch(id=1, channel="display", occurred_at=BASE - timedelta(days=14)),
            Touch(id=2, channel="google", occurred_at=BASE),
        ),
    )
    report = attribute([explicit], "time_decay", 7)
    assert report.channels["google"].revenue_cents == 8_000
    assert report.channels["display"].revenue_cents == 2_000
