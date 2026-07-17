"""Реплицирует stg_orders + stg_customers (Postgres, etl-portfolio) в
analytics.order_events (ClickHouse) — тот же источник данных, что и
sql/marts.sql, только для колоночного OLAP-движка вместо построчного Postgres.

Идемпотентно: TRUNCATE analytics.order_events и analytics.channel_monthly_revenue
перед вставкой (тот же принцип, что transform-слой etl-portfolio использует
для staging-таблиц) — повторный запуск не дублирует ни сырые события, ни
инкрементальную витрину, которую MATERIALIZED VIEW строит поверх них.
"""
import os
import sys
from pathlib import Path

import clickhouse_connect
import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")


def get_postgres_engine():
    return create_engine(
        f"postgresql+psycopg2://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', '')}"
        f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'etl_portfolio')}"
    )


def get_clickhouse_client():
    return clickhouse_connect.get_client(
        host=os.getenv("CLICKHOUSE_HOST", "localhost"),
        port=int(os.getenv("CLICKHOUSE_PORT", "8123")),
        username=os.getenv("CLICKHOUSE_USER", "default"),
        password=os.getenv("CLICKHOUSE_PASSWORD", ""),
    )


def orders_to_rows(orders: pd.DataFrame, customers: pd.DataFrame) -> pd.DataFrame:
    """orders: order_id, customer_id, order_date, total_amount.
    customers: customer_id, channel. Один ряд на заказ с денормализованным
    channel — типичный OLAP-паттерн: JOIN делается один раз при загрузке,
    а не на каждый аналитический запрос. Заказы без известного клиента
    (не должно случаться на честных staging-данных, но не гарантировано
    FOREIGN KEY между Postgres и ClickHouse) отбрасываются inner join'ом,
    а не падают с ошибкой."""
    merged = orders.merge(customers[["customer_id", "channel"]], on="customer_id", how="inner")
    return merged[["order_id", "customer_id", "channel", "order_date", "total_amount"]]


def main() -> None:
    pg = get_postgres_engine()
    orders = pd.read_sql(
        "SELECT order_id, customer_id, order_date, total_amount FROM stg_orders",
        pg, parse_dates=["order_date"],
    )
    customers = pd.read_sql("SELECT customer_id, channel FROM stg_customers", pg)

    rows = orders_to_rows(orders, customers)

    ch = get_clickhouse_client()
    ch.command("TRUNCATE TABLE IF EXISTS analytics.order_events")
    ch.command("TRUNCATE TABLE IF EXISTS analytics.channel_monthly_revenue")
    ch.insert_df("analytics.order_events", rows)

    print(f"Loaded {len(rows)} order events into analytics.order_events")


if __name__ == "__main__":
    main()
