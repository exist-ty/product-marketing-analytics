"""Честное сравнение: VIEW (пересчёт на каждый SELECT) vs MATERIALIZED VIEW
(хранит результат, обновляется REFRESH'ем) для всех трёх витрин. Каждый
вариант прогоняется N_RUNS раз (один warmup-прогон не считается), выводится
медианное время. Не благородное соревнование "кто быстрее в вакууме" —
у обеих версий разное назначение (см. README, раздел «Материализованные
витрины»): смысл здесь честно измерить цену пересчёта на этом объёме данных,
а не предположить её."""
import statistics
import sys
import time
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ml.build_features import get_engine

N_RUNS = 20

MARTS = ["mart_channel_economics", "mart_customer_ltv", "mart_cohort_retention"]


def median_wall_time_ms(run_once) -> float:
    run_once()  # warmup, не считается
    samples = []
    for _ in range(N_RUNS):
        start = time.perf_counter()
        run_once()
        samples.append((time.perf_counter() - start) * 1000)
    return statistics.median(samples)


def main() -> None:
    engine = get_engine()

    print(f"{'mart':<28} {'VIEW (ms)':>12} {'MATERIALIZED (ms)':>20} {'speedup':>10}")
    with engine.connect() as conn:
        for mart in MARTS:
            view_ms = median_wall_time_ms(lambda: conn.execute(text(f"SELECT * FROM {mart}")).fetchall())
            mv_ms = median_wall_time_ms(lambda: conn.execute(text(f"SELECT * FROM {mart}_mv")).fetchall())
            speedup = view_ms / mv_ms if mv_ms else float("inf")
            print(f"{mart:<28} {view_ms:>12.2f} {mv_ms:>20.2f} {speedup:>9.1f}x")

    print(f"\nMedian of {N_RUNS} runs on this project's real data.")


if __name__ == "__main__":
    main()
