"""Deterministic demo dataset.

The journeys are shaped so the attribution models genuinely disagree:

* prospects *discover* a brand on display/meta and *convert* through branded
  search, so last-touch over-credits search and first-touch over-credits display;
* some journeys end in a direct visit, which is exactly the traffic every
  platform tries to claim;
* a few conversions arrive with no touch inside the lookback window, so the
  "unattributed" bucket is visible instead of silently dropped.

Fixed RNG seed, relative to today, UUID5 event ids: re-seeding is idempotent.
"""

from __future__ import annotations

import random
import uuid
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from channeltruth.models import Account, ChannelSpend, Conversion, Touchpoint
from channeltruth.tenant import hash_api_key

DEMO_ACCOUNTS = [
    ("meridian-home", "Meridian Home", "ct_demo_meridian_key", "growth"),
    ("trailhead-outdoors", "Trailhead Outdoors", "ct_demo_trailhead_key", "scale"),
]

#: Daily spend in paise. `direct` is organic, so it has no media cost - which is
#: why its ROAS is undefined rather than infinite.
CHANNEL_SPEND = {
    "google": 900_000,
    "meta": 620_000,
    "display": 300_000,
    "email": 55_000,
    "direct": 0,
}

#: (path of channels, conversion probability)
PATH_TEMPLATES = [
    (["display", "google"], 0.62),
    (["meta", "google", "google"], 0.58),
    (["display", "meta", "google"], 0.55),
    (["google"], 0.66),
    (["email", "direct"], 0.48),
    (["meta", "display", "google"], 0.52),
    (["direct"], 0.30),
    (["meta", "meta", "google"], 0.57),
    (["display", "email", "direct", "google"], 0.44),
    ([], 0.10),  # conversion with no in-window touch -> unattributed
]

_EVENT_NAMESPACE = uuid.UUID("2b8f7c11-9e42-4d1a-8f33-6a0c5d7e9b24")

VISITORS_PER_DAY = 9
HISTORY_DAYS = 30


def _event_uid(*parts: str) -> str:
    return str(uuid.uuid5(_EVENT_NAMESPACE, ":".join(parts)))


def _seed_account(
    session: Session, account: Account, today: date, rng: random.Random
) -> None:
    # --- daily channel spend ------------------------------------------------
    for offset in range(HISTORY_DAYS, -1, -1):
        day = today - timedelta(days=offset)
        for channel, base in CHANNEL_SPEND.items():
            jitter = rng.uniform(0.88, 1.12)
            session.add(
                ChannelSpend(
                    account_id=account.id,
                    channel=channel,
                    day=day,
                    spend_cents=int(base * jitter),
                )
            )

    # --- journeys -----------------------------------------------------------
    for offset in range(HISTORY_DAYS, -1, -1):
        day = today - timedelta(days=offset)

        for visitor_index in range(VISITORS_PER_DAY):
            path, conversion_probability = rng.choice(PATH_TEMPLATES)
            visitor_id = f"{account.slug}-v{offset}-{visitor_index}"

            conversion_day = day
            conversion_time = datetime.combine(conversion_day, time(hour=12)) + timedelta(
                minutes=rng.randint(0, 600)
            )

            # Discovery touches land before the conversion; the last touch is
            # within a few hours of it, which is what time-decay rewards.
            for position, channel in enumerate(path):
                hours_before = (len(path) - position) * rng.uniform(2, 26)
                touch_time = conversion_time - timedelta(hours=hours_before)
                session.add(
                    Touchpoint(
                        account_id=account.id,
                        event_uid=_event_uid(account.slug, visitor_id, str(position), channel),
                        visitor_id=visitor_id,
                        channel=channel,
                        campaign=f"{channel}-{conversion_day:%b}-always-on".lower(),
                        kind="click" if channel != "display" else "impression",
                        occurred_at=touch_time,
                    )
                )

            if rng.random() <= conversion_probability:
                revenue = rng.randint(150_000, 1_200_000)
                session.add(
                    Conversion(
                        account_id=account.id,
                        event_uid=_event_uid(account.slug, visitor_id, "conv"),
                        visitor_id=visitor_id,
                        revenue_cents=revenue,
                        occurred_at=conversion_time,
                    )
                )


def seed_demo(session: Session, today: date | None = None, force: bool = False) -> bool:
    if not force and session.scalar(select(func.count(Account.id))) > 0:
        return False

    today = today or date.today()
    rng = random.Random(20261017)

    for slug, name, api_key, plan in DEMO_ACCOUNTS:
        account = Account(
            name=name, slug=slug, api_key_hash=hash_api_key(api_key), plan=plan
        )
        session.add(account)
        session.flush()
        _seed_account(session, account, today, rng)

    session.commit()
    return True


def ensure_seeded(session: Session) -> bool:
    return seed_demo(session)
