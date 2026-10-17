"""Request/response contracts.

Money is integer minor units on the wire. Timestamps are stored naive UTC and
re-emitted with an explicit offset so a browser never has to guess.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

TouchKind = Literal["impression", "click", "visit"]


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc)


class TouchpointIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_uid: str = Field(min_length=1, max_length=90)
    visitor_id: str = Field(min_length=1, max_length=90)
    channel: str = Field(min_length=1, max_length=40)
    campaign: str | None = Field(default=None, max_length=120)
    kind: TouchKind = "click"
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at must include a timezone offset")
        return value


class ConversionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_uid: str = Field(min_length=1, max_length=90)
    visitor_id: str = Field(min_length=1, max_length=90)
    revenue_cents: int = Field(gt=0, le=100_000_000)
    occurred_at: datetime

    @field_validator("occurred_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("occurred_at must include a timezone offset")
        return value


class SpendIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: str = Field(min_length=1, max_length=40)
    day: date
    spend_cents: int = Field(ge=0, le=1_000_000_000)


class TouchBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    touchpoints: list[TouchpointIn] = Field(min_length=1, max_length=500)


class ConversionBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conversions: list[ConversionIn] = Field(min_length=1, max_length=500)


class SpendBatchIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    spend: list[SpendIn] = Field(min_length=1, max_length=500)


class IngestResult(BaseModel):
    accepted: int = 0
    updated: int = 0
    duplicates: int = 0
    rejected: int = 0
    errors: list[str] = Field(default_factory=list)


class ChannelRow(BaseModel):
    channel: str
    revenue_cents: int
    share: float
    conversions: float
    touchpoints: int
    spend_cents: int
    roas: float | None


class ReportTotals(BaseModel):
    journeys: int
    revenue_cents: int
    conversions: float
    touchpoints: int
    spend_cents: int
    roas: float | None
    unattributed_revenue_cents: int
    unattributed_conversions: int


class ReportOut(BaseModel):
    model: str
    from_day: date
    to_day: date
    lookback_days: int
    half_life_days: float
    totals: ReportTotals
    channels: list[ChannelRow]


class CompareChannel(BaseModel):
    channel: str
    spend_cents: int
    revenue_by_model: dict[str, int]
    share_by_model: dict[str, float]


class CompareOut(BaseModel):
    from_day: date
    to_day: date
    lookback_days: int
    half_life_days: float
    models: list[str]
    journeys: int
    unattributed_revenue_cents: int
    channels: list[CompareChannel]
    total_by_model: dict[str, int]


class JourneyTouchOut(BaseModel):
    touchpoint_id: int
    channel: str
    kind: str
    occurred_at: datetime
    credits_by_model: dict[str, int]
    weight_by_model: dict[str, float]

    @field_serializer("occurred_at")
    def serialize_time(self, value: datetime) -> datetime:
        return _utc(value)


class JourneyOut(BaseModel):
    conversion_uid: str
    visitor_id: str
    revenue_cents: int
    occurred_at: datetime
    lookback_days: int
    half_life_days: float
    models: list[str]
    touches: list[JourneyTouchOut]
    totals_by_model: dict[str, int]

    @field_serializer("occurred_at")
    def serialize_time(self, value: datetime) -> datetime:
        return _utc(value)


class RecentConversion(BaseModel):
    conversion_uid: str
    visitor_id: str
    revenue_cents: int
    occurred_at: datetime

    @field_serializer("occurred_at")
    def serialize_time(self, value: datetime) -> datetime:
        return _utc(value)


class AccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    plan: str
