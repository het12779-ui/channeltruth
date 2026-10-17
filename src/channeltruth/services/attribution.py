"""Attribution mathematics - pure functions, no I/O.

Five models are supported. Each returns a weight per touchpoint; the weights are
then normalised and used to split the conversion's revenue.

Why integer allocation instead of floats
-----------------------------------------
If a ₹999.99 conversion is split three ways, each channel must still sum back to
₹999.99. Naive rounding loses or invents paise, and finance teams notice. Every
split here uses the **largest remainder method**, so:

    sum(allocate_cents(total, weights)) == total   for all inputs

That invariant is property-tested across awkward totals and touch counts.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

MODELS: tuple[str, ...] = (
    "first_touch",
    "last_touch",
    "linear",
    "time_decay",
    "position_based",
)

MODEL_LABELS = {
    "first_touch": "First touch",
    "last_touch": "Last touch",
    "linear": "Linear",
    "time_decay": "Time decay",
    "position_based": "Position based",
}


@dataclass(frozen=True, slots=True)
class Touch:
    id: int
    channel: str
    occurred_at: datetime
    kind: str = "click"


@dataclass(frozen=True, slots=True)
class Journey:
    conversion_uid: str
    visitor_id: str
    revenue_cents: int
    occurred_at: datetime
    touches: tuple[Touch, ...]


def validate_model(model: str) -> str:
    if model not in MODELS:
        raise ValueError(f"unknown attribution model '{model}'; expected one of {', '.join(MODELS)}")
    return model


def touch_weights(
    touches: list[Touch] | tuple[Touch, ...],
    model: str,
    half_life_days: float = 7.0,
    occurred_at: datetime | None = None,
) -> list[float]:
    """Weights for one journey. Not normalised; ``allocate_cents`` handles that."""

    validate_model(model)
    count = len(touches)
    if count == 0:
        return []

    if model == "first_touch":
        return [1.0] + [0.0] * (count - 1)

    if model == "last_touch":
        return [0.0] * (count - 1) + [1.0]

    if model == "linear":
        return [1.0] * count

    if model == "position_based":
        if count == 1:
            return [1.0]
        if count == 2:
            return [0.5, 0.5]
        middle = 0.2 / (count - 2)
        return [0.4] + [middle] * (count - 2) + [0.4]

    # time_decay: half-life decay measured back from the conversion, so the
    # conversion timestamp must be supplied or the decay has no anchor.
    if half_life_days <= 0:
        raise ValueError("half_life_days must be positive")
    if occurred_at is None:
        occurred_at = max(touch.occurred_at for touch in touches)

    weights = []
    for touch in touches:
        age_days = max(0.0, (occurred_at - touch.occurred_at).total_seconds() / 86_400)
        weights.append(0.5 ** (age_days / half_life_days))
    return weights


def allocate_cents(total_cents: int, weights: list[float]) -> list[int]:
    """Split ``total_cents`` by weight using the largest remainder method.

    Guarantees:
      * the parts sum exactly to ``total_cents``;
      * ties break by index, so results are deterministic (reproducible reports);
      * zero/negative weights get nothing unless every weight is zero, in which
        case the split is even.
    """

    count = len(weights)
    if count == 0 or total_cents <= 0:
        return [0] * count

    cleaned = [max(0.0, weight) for weight in weights]
    total_weight = sum(cleaned)
    if total_weight <= 0:
        cleaned = [1.0] * count
        total_weight = float(count)

    exact = [total_cents * weight / total_weight for weight in cleaned]
    floors = [int(math.floor(value)) for value in exact]
    remainder = total_cents - sum(floors)

    if remainder > 0:
        order = sorted(
            range(count), key=lambda index: (-(exact[index] - floors[index]), index)
        )
        for index in order[:remainder]:
            floors[index] += 1

    return floors


@dataclass
class ChannelCredit:
    channel: str
    revenue_cents: int = 0
    conversion_credit: float = 0.0
    touchpoints: int = 0

    @property
    def conversions(self) -> float:
        return round(self.conversion_credit, 4)


@dataclass
class AttributionReport:
    model: str
    revenue_cents: int = 0
    conversion_credit: float = 0.0
    journeys: int = 0
    unattributed_revenue_cents: int = 0
    unattributed_conversions: int = 0
    channels: dict[str, ChannelCredit] = field(default_factory=dict)

    def channel_rows(self) -> list[ChannelCredit]:
        return sorted(
            self.channels.values(), key=lambda row: (-row.revenue_cents, row.channel)
        )


@dataclass(frozen=True)
class TouchCredit:
    touch: Touch
    weight: float
    credit_cents: int


def credit_journey(
    journey: Journey, model: str, half_life_days: float = 7.0
) -> list[TouchCredit]:
    """Per-touch credits for one conversion - the explainability primitive."""

    weights = touch_weights(journey.touches, model, half_life_days, journey.occurred_at)
    if not weights:
        return []

    total_weight = sum(weights) or 1.0
    credits = allocate_cents(journey.revenue_cents, weights)
    return [
        TouchCredit(touch=touch, weight=weight / total_weight, credit_cents=cents)
        for touch, weight, cents in zip(journey.touches, weights, credits)
    ]


def attribute(
    journeys: list[Journey], model: str, half_life_days: float = 7.0
) -> AttributionReport:
    """Attribute every journey to channels under one model."""

    validate_model(model)
    report = AttributionReport(model=model)

    for journey in journeys:
        report.journeys += 1

        if not journey.touches:
            # A conversion with no touch inside the lookback window is not
            # inventing credit for a channel; it is reported as unattributed.
            report.unattributed_revenue_cents += journey.revenue_cents
            report.unattributed_conversions += 1
            continue

        weights = touch_weights(journey.touches, model, half_life_days, journey.occurred_at)
        total_weight = sum(weights) or 1.0

        for touch in journey.touches:
            row = report.channels.setdefault(
                touch.channel, ChannelCredit(channel=touch.channel)
            )
            row.touchpoints += 1

        credits = allocate_cents(journey.revenue_cents, weights)
        for touch, weight, cents in zip(journey.touches, weights, credits):
            row = report.channels[touch.channel]
            row.revenue_cents += cents
            row.conversion_credit += weight / total_weight

        report.revenue_cents += journey.revenue_cents
        report.conversion_credit += 1.0

    return report
