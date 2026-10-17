"""Benchmark ``GET /api/v1/attribution/compare`` end to end.

Runs the real app against a temporary SQLite database, so the number includes
journey assembly, all five attribution models, Pydantic serialisation and JSON
encoding.

Usage:
    python scripts/bench_compare.py
    python scripts/bench_compare.py --sizes 100 1000 5000 --iterations 10
"""

from __future__ import annotations

import argparse
import os
import statistics
import tempfile
import time
import uuid
from datetime import date, datetime, timedelta, timezone

_WORKDIR = tempfile.mkdtemp(prefix="channeltruth-bench-")
os.environ["DATABASE_URL"] = f"sqlite:///{_WORKDIR}/bench.db"
os.environ["CHANNELTRUTH_SEED"] = "0"

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import insert  # noqa: E402

from channeltruth.config import Settings  # noqa: E402
from channeltruth.db import Base, SessionLocal, engine  # noqa: E402
from channeltruth.main import create_app  # noqa: E402
from channeltruth.models import Account, Conversion, Touchpoint  # noqa: E402
from channeltruth.tenant import hash_api_key  # noqa: E402

API_KEY = "bench-key"
TODAY = date.today()
PATH = ["display", "meta", "google"]


def seed(journey_count: int) -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    with SessionLocal() as session:
        account = Account(
            name="Bench", slug="bench", api_key_hash=hash_api_key(API_KEY), plan="scale"
        )
        session.add(account)
        session.flush()

        midnight = datetime.combine(TODAY, datetime.min.time())
        touches = []
        conversions = []

        for index in range(journey_count):
            visitor = f"visitor-{index}"
            conversion_time = midnight + timedelta(minutes=index % 1440)
            conversations_uid = str(uuid.uuid5(uuid.NAMESPACE_URL, f"conv-{index}"))
            for position, channel in enumerate(PATH):
                touches.append(
                    {
                        "account_id": account.id,
                        "event_uid": f"{index}-{position}",
                        "visitor_id": visitor,
                        "channel": channel,
                        "campaign": None,
                        "kind": "click",
                        "occurred_at": conversion_time - timedelta(hours=(3 - position) * 8),
                    }
                )
            conversions.append(
                {
                    "account_id": account.id,
                    "event_uid": conversations_uid,
                    "visitor_id": visitor,
                    "revenue_cents": 100_000 + index,
                    "occurred_at": conversion_time,
                }
            )

        session.execute(insert(Touchpoint), touches)
        session.execute(insert(Conversion), conversions)
        session.commit()


def measure(journey_count: int, iterations: int) -> dict:
    seed(journey_count)
    app = create_app(Settings(demo_mode=False, seed_demo_data=False))

    with TestClient(app) as client:
        client.headers.update({"X-API-Key": API_KEY})
        url = f"/api/v1/attribution/compare?from={TODAY.isoformat()}&to={TODAY.isoformat()}"

        for _ in range(2):
            assert client.get(url).status_code == 200

        samples = []
        for _ in range(iterations):
            started = time.perf_counter()
            response = client.get(url)
            samples.append((time.perf_counter() - started) * 1000)
            assert response.status_code == 200
            assert response.json()["journeys"] == journey_count

    samples.sort()
    return {
        "journeys": journey_count,
        "p50_ms": statistics.median(samples),
        "p95_ms": samples[max(0, int(len(samples) * 0.95) - 1)],
        "max_ms": max(samples),
        "bytes": len(response.content),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sizes", type=int, nargs="+", default=[100, 1000, 5000])
    parser.add_argument("--iterations", type=int, default=10)
    args = parser.parse_args()

    print(f"ChannelTruth compare benchmark · 5 models · {args.iterations} iterations")
    print()
    print("| journeys | p50 | p95 | max | payload |")
    print("|---:|---:|---:|---:|---:|")
    for size in args.sizes:
        result = measure(size, args.iterations)
        print(
            f"| {result['journeys']:,} | {result['p50_ms']:.1f} ms | "
            f"{result['p95_ms']:.1f} ms | {result['max_ms']:.1f} ms | "
            f"{result['bytes'] / 1024:.0f} KB |"
        )


if __name__ == "__main__":
    main()
