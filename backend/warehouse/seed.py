"""Build a small synthetic analytics warehouse in DuckDB.

Run: python -m backend.warehouse.seed
"""
from __future__ import annotations

import random
from pathlib import Path

import duckdb

from backend.config import RANDOM_SEED, WAREHOUSE_PATH

TABLES = ["dim_region", "fct_orders", "mart_account_health"]

REGIONS = [
    ("North America", "Americas"),
    ("EMEA", "EMEA"),
    ("LATAM", "Americas"),
    ("APAC", "APAC"),
    ("Other", "Other"),
]
REGION_WEIGHTS = [0.42, 0.28, 0.13, 0.14, 0.03]
CHANNELS = ["Direct", "Partner", "Self-serve"]
SEGMENTS = ["Enterprise", "Mid-market", "SMB"]
QUARTERS = ["2026Q1", "2026Q2", "2026Q3"]


def _orders(rng: random.Random) -> list[tuple]:
    rows: list[tuple] = []
    order_id = 1
    for quarter in QUARTERS:
        q_growth = {"2026Q1": 0.9, "2026Q2": 0.95, "2026Q3": 1.0}[quarter]
        for week in range(1, 14):
            for _ in range(rng.randint(60, 90)):
                region = rng.choices(REGIONS, weights=REGION_WEIGHTS)[0][0]
                channel = rng.choice(CHANNELS)
                segment = rng.choice(SEGMENTS)
                base = {"Enterprise": 42000, "Mid-market": 9000, "SMB": 1200}[segment]
                net = round(
                    base * q_growth * (1 + week * 0.01) * rng.uniform(0.6, 1.5), 2
                )
                discount = round(
                    {"Enterprise": 10, "Mid-market": 16, "SMB": 12}[segment]
                    * rng.uniform(0.4, 1.8),
                    1,
                )
                margin = round(max(20.0, 72 - discount * rng.uniform(0.8, 1.4)), 1)
                rows.append(
                    (
                        order_id,
                        f"2026-{QUARTERS.index(quarter) * 3 + 1:02d}-{(week % 28) + 1:02d}",
                        quarter,
                        f"W{week}",
                        region,
                        channel,
                        segment,
                        net,
                        discount,
                        margin,
                    )
                )
                order_id += 1
    return rows


def _account_health(rng: random.Random) -> list[tuple]:
    rows: list[tuple] = []
    for segment in SEGMENTS:
        for discount in (6, 12, 20):
            margin = round(max(30.0, 70 - discount * rng.uniform(1.0, 1.6)), 1)
            accounts = rng.randint(30, 220)
            rows.append((segment, discount, margin, accounts))
    return rows


def build(path: Path | None = None) -> None:
    path = Path(path) if path is not None else WAREHOUSE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    rng = random.Random(RANDOM_SEED)
    con = duckdb.connect(str(path))
    try:
        con.execute(
            "CREATE TABLE dim_region (region VARCHAR, macro_area VARCHAR)"
        )
        con.executemany(
            "INSERT INTO dim_region VALUES (?, ?)",
            [(r, a) for r, a in REGIONS],
        )
        con.execute(
            """
            CREATE TABLE fct_orders (
                order_id BIGINT, order_date VARCHAR, quarter VARCHAR, week VARCHAR,
                region VARCHAR, channel VARCHAR, segment VARCHAR,
                net_revenue DOUBLE, discount_pct DOUBLE, gross_margin_pct DOUBLE
            )
            """
        )
        con.executemany(
            "INSERT INTO fct_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            _orders(rng),
        )
        con.execute(
            """
            CREATE TABLE mart_account_health (
                segment VARCHAR, avg_discount INTEGER,
                gross_margin DOUBLE, accounts INTEGER
            )
            """
        )
        con.executemany(
            "INSERT INTO mart_account_health VALUES (?, ?, ?, ?)",
            _account_health(rng),
        )
    finally:
        con.close()


if __name__ == "__main__":
    build()
    print(f"Warehouse built at {WAREHOUSE_PATH}")
