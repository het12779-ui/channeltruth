"""Attribution reports and journey explainability."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from channeltruth.config import Settings, get_settings
from channeltruth.db import get_session
from channeltruth.models import Account, ChannelSpend
from channeltruth.schemas import (
    ChannelRow,
    CompareChannel,
    CompareOut,
    JourneyOut,
    JourneyTouchOut,
    RecentConversion,
    ReportOut,
    ReportTotals,
)
from channeltruth.services.attribution import (
    MODELS,
    attribute,
    credit_journey,
    validate_model,
)
from channeltruth.services.journeys import load_journey, load_journeys, recent_conversions
from channeltruth.tenant import get_tenant

router = APIRouter(prefix="/attribution", tags=["attribution"])

MAX_RANGE_DAYS = 366


def _resolve_range(date_from: date | None, date_to: date | None) -> tuple[date, date]:
    today = datetime.now(timezone.utc).date()
    end = date_to or today
    start = date_from or end - timedelta(days=29)

    if start > end:
        raise HTTPException(status_code=422, detail="'from' must be on or before 'to'")
    if (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(
            status_code=422, detail=f"date range is limited to {MAX_RANGE_DAYS} days"
        )
    return start, end


def _spend_by_channel(
    session: Session, account_id: int, start: date, end: date
) -> dict[str, int]:
    rows = session.execute(
        select(ChannelSpend.channel, func.coalesce(func.sum(ChannelSpend.spend_cents), 0))
        .where(
            ChannelSpend.account_id == account_id,
            ChannelSpend.day >= start,
            ChannelSpend.day <= end,
        )
        .group_by(ChannelSpend.channel)
    ).all()
    return {channel: int(cents) for channel, cents in rows}


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 3)


@router.get("", response_model=ReportOut)
def attribution_report(
    account: Account = Depends(get_tenant),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    model: str = Query(default="linear"),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    lookback_days: int | None = Query(default=None, ge=1, le=90),
    half_life_days: float | None = Query(default=None, gt=0, le=90),
) -> ReportOut:
    try:
        validate_model(model)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    start, end = _resolve_range(date_from, date_to)
    lookback = lookback_days or settings.lookback_days
    half_life = half_life_days or settings.half_life_days

    journeys = load_journeys(session, account.id, start, end, lookback)
    report = attribute(journeys, model, half_life)
    spend = _spend_by_channel(session, account.id, start, end)

    channels = sorted(
        set(report.channels) | set(spend),
        key=lambda channel: (
            -(report.channels[channel].revenue_cents if channel in report.channels else 0),
            channel,
        ),
    )

    rows: list[ChannelRow] = []
    for channel in channels:
        credit = report.channels.get(channel)
        revenue = credit.revenue_cents if credit else 0
        channel_spend = spend.get(channel, 0)
        rows.append(
            ChannelRow(
                channel=channel,
                revenue_cents=revenue,
                share=round(revenue / report.revenue_cents, 4) if report.revenue_cents else 0.0,
                conversions=credit.conversions if credit else 0.0,
                touchpoints=credit.touchpoints if credit else 0,
                spend_cents=channel_spend,
                roas=_ratio(revenue, channel_spend),
            )
        )

    total_spend = sum(spend.values())
    return ReportOut(
        model=model,
        from_day=start,
        to_day=end,
        lookback_days=lookback,
        half_life_days=half_life,
        totals=ReportTotals(
            journeys=report.journeys,
            revenue_cents=report.revenue_cents,
            conversions=round(report.conversion_credit, 4),
            touchpoints=sum(row.touchpoints for row in rows),
            spend_cents=total_spend,
            roas=_ratio(report.revenue_cents, total_spend),
            unattributed_revenue_cents=report.unattributed_revenue_cents,
            unattributed_conversions=report.unattributed_conversions,
        ),
        channels=rows,
    )


@router.get("/compare", response_model=CompareOut)
def compare_models(
    account: Account = Depends(get_tenant),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    lookback_days: int | None = Query(default=None, ge=1, le=90),
    half_life_days: float | None = Query(default=None, gt=0, le=90),
) -> CompareOut:
    """Run every model over the *same* journeys.

    Comparing models against differently-built datasets is the classic way to
    produce a meaningless attribution deck, so the journeys are loaded once.
    """

    start, end = _resolve_range(date_from, date_to)
    lookback = lookback_days or settings.lookback_days
    half_life = half_life_days or settings.half_life_days

    journeys = load_journeys(session, account.id, start, end, lookback)
    reports = {model: attribute(journeys, model, half_life) for model in MODELS}
    spend = _spend_by_channel(session, account.id, start, end)

    channels = sorted(
        set(spend).union(*(set(report.channels) for report in reports.values())),
        key=lambda channel: (
            -max(report.channels[channel].revenue_cents if channel in report.channels else 0
                 for report in reports.values()),
            channel,
        ),
    )

    rows = []
    for channel in channels:
        revenue_by_model = {
            model: reports[model].channels[channel].revenue_cents
            if channel in reports[model].channels
            else 0
            for model in MODELS
        }
        share_by_model = {
            model: round(revenue_by_model[model] / reports[model].revenue_cents, 4)
            if reports[model].revenue_cents
            else 0.0
            for model in MODELS
        }
        rows.append(
            CompareChannel(
                channel=channel,
                spend_cents=spend.get(channel, 0),
                revenue_by_model=revenue_by_model,
                share_by_model=share_by_model,
            )
        )

    return CompareOut(
        from_day=start,
        to_day=end,
        lookback_days=lookback,
        half_life_days=half_life,
        models=list(MODELS),
        journeys=len(journeys),
        unattributed_revenue_cents=reports["linear"].unattributed_revenue_cents,
        channels=rows,
        total_by_model={model: reports[model].revenue_cents for model in MODELS},
    )


@router.get("/journeys/recent", response_model=list[RecentConversion])
def recent(
    account: Account = Depends(get_tenant),
    session: Session = Depends(get_session),
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict]:
    return recent_conversions(session, account.id, limit)


@router.get("/journeys/{conversion_uid}", response_model=JourneyOut)
def journey_detail(
    conversion_uid: str,
    account: Account = Depends(get_tenant),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    lookback_days: int | None = Query(default=None, ge=1, le=90),
    half_life_days: float | None = Query(default=None, gt=0, le=90),
) -> JourneyOut:
    lookback = lookback_days or settings.lookback_days
    half_life = half_life_days or settings.half_life_days

    journey = load_journey(session, account.id, conversion_uid, lookback)
    if journey is None:
        raise HTTPException(status_code=404, detail="Conversion not found")

    per_model = {model: credit_journey(journey, model, half_life) for model in MODELS}

    touches: list[JourneyTouchOut] = []
    for index, touch in enumerate(journey.touches):
        touches.append(
            JourneyTouchOut(
                touchpoint_id=touch.id,
                channel=touch.channel,
                kind=touch.kind,
                occurred_at=touch.occurred_at,
                credits_by_model={
                    model: per_model[model][index].credit_cents for model in MODELS
                },
                weight_by_model={
                    model: round(per_model[model][index].weight, 6) for model in MODELS
                },
            )
        )

    return JourneyOut(
        conversion_uid=journey.conversion_uid,
        visitor_id=journey.visitor_id,
        revenue_cents=journey.revenue_cents,
        occurred_at=journey.occurred_at,
        lookback_days=lookback,
        half_life_days=half_life,
        models=list(MODELS),
        touches=touches,
        totals_by_model={
            model: sum(credit.credit_cents for credit in per_model[model])
            for model in MODELS
        },
    )
