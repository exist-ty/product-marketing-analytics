"""Обновляет материализованные витрины (sql/materialized_marts.sql) после
прогона ETL-пайплайна (etl-portfolio) — не на каждое чтение дашборда/API,
а по расписанию/после загрузки новых данных. REFRESH ... CONCURRENTLY не
блокирует SELECT'ы во время пересчёта (цена — обязательный уникальный
индекс на витрине, уже создан в materialized_marts.sql), обычный REFRESH
был бы проще, но недоступен параллельно с чтением."""
import sys
import time
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml.build_features import get_engine

MATERIALIZED_VIEWS = [
    "mart_channel_economics_mv",
    "mart_customer_ltv_mv",
    "mart_cohort_retention_mv",
]


def refresh_all() -> None:
    engine = get_engine()
    for view in MATERIALIZED_VIEWS:
        start = time.perf_counter()
        with engine.begin() as conn:
            conn.execute(text(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}"))
        elapsed_ms = (time.perf_counter() - start) * 1000
        print(f"{view}: refreshed in {elapsed_ms:.2f} ms")


if __name__ == "__main__":
    refresh_all()
