"""Честное сравнение трёх способов получить "выручка по каналу/месяцу":

1. Postgres VIEW (mart_channel_economics) — пересчитывается целиком на
   каждый SELECT.
2. ClickHouse, агрегация "с нуля" по сырым analytics.order_events —
   колоночное сканирование, но без использования инкрементальной витрины.
3. ClickHouse, чтение analytics.channel_monthly_revenue через
   `-Merge`-комбинаторы — агрегат уже частично посчитан на этапе вставки
   MATERIALIZED VIEW, здесь только комбинируются готовые состояния.

Каждый вариант прогоняется N_RUNS раз (после одного warmup-прогона) и
выводится медианное время. Смысл честно предупредить, а не скрыть: на
объёме данных этого пет-проекта (~2000 заказов) всё укладывается в единицы
миллисекунд на каждом движке — эта разница НЕ показательна как "ClickHouse
быстрее". Ценность здесь архитектурная (см. README): при объёмах, которые
не помещаются в план Postgres целиком в память, выигрывает и колоночное
хранение, и то, что вариант 3 не пересчитывает агрегат с нуля при каждом
запросе — вариант 1 и 2 пересчитывают.
"""
import os
import statistics
import sys
import time
from pathlib import Path

import clickhouse_connect
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

N_RUNS = 20

POSTGRES_QUERY = text("""
    SELECT c.channel, DATE_TRUNC('month', o.order_date) AS revenue_month,
           SUM(o.total_amount) AS revenue, COUNT(*) AS orders
    FROM stg_orders o
    JOIN stg_customers c ON c.customer_id = o.customer_id
    GROUP BY c.channel, DATE_TRUNC('month', o.order_date)
""")

CLICKHOUSE_FROM_RAW = """
    SELECT channel, toStartOfMonth(order_date) AS revenue_month,
           sum(total_amount) AS revenue, count() AS orders
    FROM analytics.order_events
    GROUP BY channel, revenue_month
"""

CLICKHOUSE_FROM_ROLLUP = """
    SELECT channel, revenue_month,
           sumMerge(revenue_state) AS revenue,
           countMerge(orders_state) AS orders
    FROM analytics.channel_monthly_revenue
    GROUP BY channel, revenue_month
"""


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


def median_wall_time_ms(run_once) -> float:
    run_once()  # warmup, не считается
    samples = []
    for _ in range(N_RUNS):
        start = time.perf_counter()
        run_once()
        samples.append((time.perf_counter() - start) * 1000)
    return statistics.median(samples)


def main() -> None:
    pg = get_postgres_engine()
    ch = get_clickhouse_client()

    with pg.connect() as conn:
        pg_ms = median_wall_time_ms(lambda: conn.execute(POSTGRES_QUERY).fetchall())

    ch_raw_ms = median_wall_time_ms(lambda: ch.query(CLICKHOUSE_FROM_RAW).result_rows)
    ch_rollup_ms = median_wall_time_ms(lambda: ch.query(CLICKHOUSE_FROM_ROLLUP).result_rows)

    print(f"Postgres VIEW-style (recompute from scratch):  {pg_ms:.2f} ms (median of {N_RUNS})")
    print(f"ClickHouse, aggregate over raw events:         {ch_raw_ms:.2f} ms (median of {N_RUNS})")
    print(f"ClickHouse, read incremental rollup:           {ch_rollup_ms:.2f} ms (median of {N_RUNS})")
    print(
        "\nAt this data volume (~2000 orders) the difference is not representative "
        "of ClickHouse vs Postgres at scale - see README section on the ClickHouse OLAP layer."
    )


if __name__ == "__main__":
    main()
