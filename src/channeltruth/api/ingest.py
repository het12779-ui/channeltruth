"""Ingest endpoints.

Ad platforms deliver events at-least-once, so every write here is idempotent:

* touchpoints / conversions dedupe on ``(account_id, event_uid)``;
* channel spend **upserts** on ``(account_id, channel, day)`` because platforms
  routinely restate yesterday's spend, and the corrected number must win.

Batches use a SAVEPOINT per row, so one bad event does not discard the other 499.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from channeltruth.db import get_session
from channeltruth.metrics import METRICS
from channeltruth.models import Account, ChannelSpend, Conversion, Touchpoint
from channeltruth.schemas import (
    ConversionBatchIn,
    ConversionIn,
    IngestResult,
    SpendBatchIn,
    SpendIn,
    TouchBatchIn,
    TouchpointIn,
)
from channeltruth.tenant import get_tenant

router = APIRouter(tags=["ingest"])


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _insert(
    session: Session,
    model,
    values: dict,
    result: IngestResult,
    metric: str,
    **metric_labels: str,
) -> None:
    savepoint = session.begin_nested()
    try:
        session.add(model(**values))
        savepoint.commit()
        result.accepted += 1
        METRICS.inc(metric, **metric_labels)
    except IntegrityError:
        # A concurrent writer won the race; the row still exists exactly once.
        savepoint.rollback()
        result.duplicates += 1
        METRICS.inc(f"{metric}_duplicate")


def ingest_touchpoint(
    session: Session, account: Account, payload: TouchpointIn, result: IngestResult
) -> None:
    exists = session.scalar(
        select(Touchpoint.id).where(
            Touchpoint.account_id == account.id, Touchpoint.event_uid == payload.event_uid
        )
    )
    if exists is not None:
        result.duplicates += 1
        return

    _insert(
        session,
        Touchpoint,
        {
            "account_id": account.id,
            "event_uid": payload.event_uid,
            "visitor_id": payload.visitor_id,
            "channel": payload.channel.lower(),
            "campaign": payload.campaign,
            "kind": payload.kind,
            "occurred_at": _naive_utc(payload.occurred_at),
        },
        result,
        "touchpoints_ingested_total",
    )


def ingest_conversion(
    session: Session, account: Account, payload: ConversionIn, result: IngestResult
) -> None:
    exists = session.scalar(
        select(Conversion.id).where(
            Conversion.account_id == account.id, Conversion.event_uid == payload.event_uid
        )
    )
    if exists is not None:
        result.duplicates += 1
        return

    _insert(
        session,
        Conversion,
        {
            "account_id": account.id,
            "event_uid": payload.event_uid,
            "visitor_id": payload.visitor_id,
            "revenue_cents": payload.revenue_cents,
            "occurred_at": _naive_utc(payload.occurred_at),
        },
        result,
        "conversions_ingested_total",
    )


def ingest_spend(
    session: Session, account: Account, payload: SpendIn, result: IngestResult
) -> None:
    existing = session.scalar(
        select(ChannelSpend).where(
            ChannelSpend.account_id == account.id,
            ChannelSpend.channel == payload.channel.lower(),
            ChannelSpend.day == payload.day,
        )
    )

    if existing is not None:
        if existing.spend_cents == payload.spend_cents:
            result.duplicates += 1
            return
        existing.spend_cents = payload.spend_cents
        result.updated += 1
        METRICS.inc("spend_restatements_total")
        return

    _insert(
        session,
        ChannelSpend,
        {
            "account_id": account.id,
            "channel": payload.channel.lower(),
            "day": payload.day,
            "spend_cents": payload.spend_cents,
        },
        result,
        "spend_rows_ingested_total",
    )


@router.post("/touchpoints", response_model=IngestResult, status_code=201)
def post_touchpoint(
    payload: TouchpointIn,
    account: Account = Depends(get_tenant),
    session: Session = Depends(get_session),
) -> IngestResult:
    result = IngestResult()
    ingest_touchpoint(session, account, payload, result)
    session.commit()
    return result


@router.post("/touchpoints/batch", response_model=IngestResult, status_code=201)
def post_touchpoints(
    payload: TouchBatchIn,
    account: Account = Depends(get_tenant),
    session: Session = Depends(get_session),
) -> IngestResult:
    result = IngestResult()
    for touchpoint in payload.touchpoints:
        ingest_touchpoint(session, account, touchpoint, result)
    session.commit()
    return result


@router.post("/conversions", response_model=IngestResult, status_code=201)
def post_conversion(
    payload: ConversionIn,
    account: Account = Depends(get_tenant),
    session: Session = Depends(get_session),
) -> IngestResult:
    result = IngestResult()
    ingest_conversion(session, account, payload, result)
    session.commit()
    return result


@router.post("/conversions/batch", response_model=IngestResult, status_code=201)
def post_conversions(
    payload: ConversionBatchIn,
    account: Account = Depends(get_tenant),
    session: Session = Depends(get_session),
) -> IngestResult:
    result = IngestResult()
    for conversion in payload.conversions:
        ingest_conversion(session, account, conversion, result)
    session.commit()
    return result


@router.post("/spend", response_model=IngestResult, status_code=201)
def post_spend(
    payload: SpendIn,
    account: Account = Depends(get_tenant),
    session: Session = Depends(get_session),
) -> IngestResult:
    result = IngestResult()
    ingest_spend(session, account, payload, result)
    session.commit()
    return result


@router.post("/spend/batch", response_model=IngestResult, status_code=201)
def post_spend_batch(
    payload: SpendBatchIn,
    account: Account = Depends(get_tenant),
    session: Session = Depends(get_session),
) -> IngestResult:
    result = IngestResult()
    for row in payload.spend:
        ingest_spend(session, account, row, result)
    session.commit()
    return result
