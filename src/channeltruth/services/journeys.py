"""Build journeys (conversion + its in-window touches) from the fact tables.

Attribution is per journey, so this module's job is to assemble the right
history for each conversion without scanning the whole account.

Two details that matter at scale:

* **Chunked ``IN`` lookups.** SQL Server allows 2,100 parameters per statement.
  A batch of 5,000 converting visitors would otherwise fail with a confusing
  driver error. Chunking keeps the query portable.
* **Range predicates on timestamps**, not ``DATE(column)``, so the composite
  index on ``(account_id, visitor_id, occurred_at)`` is actually used.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Iterable, Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from channeltruth.models import Conversion, Touchpoint
from channeltruth.services.attribution import Journey, Touch

#: Comfortably below SQL Server's 2,100-parameter limit.
CHUNK_SIZE = 900


def day_start(day: date) -> datetime:
    return datetime.combine(day, time.min)


def day_end(day: date) -> datetime:
    return day_start(day) + timedelta(days=1)


def _chunks(values: Sequence[str], size: int = CHUNK_SIZE) -> Iterable[Sequence[str]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


def _load_touches(
    session: Session, account_id: int, visitor_ids: Sequence[str]
) -> dict[str, list[Touch]]:
    by_visitor: dict[str, list[Touch]] = {}

    for batch in _chunks(list(visitor_ids)):
        rows = session.execute(
            select(
                Touchpoint.id,
                Touchpoint.visitor_id,
                Touchpoint.channel,
                Touchpoint.occurred_at,
                Touchpoint.kind,
            ).where(
                Touchpoint.account_id == account_id,
                Touchpoint.visitor_id.in_(batch),
            )
        ).all()

        for touch_id, visitor_id, channel, occurred_at, kind in rows:
            by_visitor.setdefault(visitor_id, []).append(
                Touch(
                    id=touch_id,
                    channel=channel,
                    occurred_at=occurred_at,
                    kind=kind,
                )
            )

    for touches in by_visitor.values():
        # Deterministic ordering: ties on timestamp break by id, so two runs of
        # the same report cannot disagree about "first touch".
        touches.sort(key=lambda touch: (touch.occurred_at, touch.id))

    return by_visitor


def _eligible(
    touches: list[Touch], conversion_time: datetime, lookback_days: int
) -> tuple[Touch, ...]:
    window_start = conversion_time - timedelta(days=lookback_days)
    return tuple(
        touch
        for touch in touches
        if window_start <= touch.occurred_at <= conversion_time
    )


def load_journeys(
    session: Session,
    account_id: int,
    start_day: date,
    end_day: date,
    lookback_days: int,
) -> list[Journey]:
    """All conversions in ``[start_day, end_day]`` with their in-window touches."""

    conversions = session.execute(
        select(
            Conversion.event_uid,
            Conversion.visitor_id,
            Conversion.revenue_cents,
            Conversion.occurred_at,
        )
        .where(
            Conversion.account_id == account_id,
            Conversion.occurred_at >= day_start(start_day),
            Conversion.occurred_at < day_end(end_day),
        )
        .order_by(Conversion.occurred_at, Conversion.id)
    ).all()

    if not conversions:
        return []

    visitors = list({row[1] for row in conversions})
    touches_by_visitor = _load_touches(session, account_id, visitors)

    journeys: list[Journey] = []
    for event_uid, visitor_id, revenue_cents, occurred_at in conversions:
        journeys.append(
            Journey(
                conversion_uid=event_uid,
                visitor_id=visitor_id,
                revenue_cents=revenue_cents,
                occurred_at=occurred_at,
                touches=_eligible(
                    touches_by_visitor.get(visitor_id, []), occurred_at, lookback_days
                ),
            )
        )
    return journeys


def load_journey(
    session: Session, account_id: int, conversion_uid: str, lookback_days: int
) -> Journey | None:
    """One journey, for the explainability endpoint."""

    row = session.execute(
        select(
            Conversion.visitor_id,
            Conversion.revenue_cents,
            Conversion.occurred_at,
        ).where(
            Conversion.account_id == account_id,
            Conversion.event_uid == conversion_uid,
        )
    ).first()

    if row is None:
        return None

    visitor_id, revenue_cents, occurred_at = row
    touches = _load_touches(session, account_id, [visitor_id]).get(visitor_id, [])

    return Journey(
        conversion_uid=conversion_uid,
        visitor_id=visitor_id,
        revenue_cents=revenue_cents,
        occurred_at=occurred_at,
        touches=_eligible(touches, occurred_at, lookback_days),
    )


def recent_conversions(
    session: Session, account_id: int, limit: int = 25
) -> list[dict]:
    """Feed for the journey explorer in the dashboard."""

    rows = session.execute(
        select(
            Conversion.event_uid,
            Conversion.visitor_id,
            Conversion.revenue_cents,
            Conversion.occurred_at,
        )
        .where(Conversion.account_id == account_id)
        .order_by(Conversion.occurred_at.desc())
        .limit(limit)
    ).all()

    return [
        {
            "conversion_uid": event_uid,
            "visitor_id": visitor_id,
            "revenue_cents": revenue_cents,
            "occurred_at": occurred_at,
        }
        for event_uid, visitor_id, revenue_cents, occurred_at in rows
    ]
