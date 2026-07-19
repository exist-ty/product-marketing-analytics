"""Симулирует рандомизированный A/B-тест email-кампании реактивации на
реальном пуле клиентов (stg_customers, БД etl_portfolio). Честное
ограничение с самого начала: в этих данных всего 200 клиентов — это
СИЛЬНО меньше, чем нужно для уверенного обнаружения умеренного лифта
(см. power-анализ в analyze_experiment.py). Baseline и treatment rate
здесь заданы искусственно (мы играем роль "истины", которую сам тест
не видит) — реальный тест этого не знает и должен её оценить по данным,
как и положено.

Применить: python ab_test/generate_experiment.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os
from datetime import date, timedelta

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

RNG_SEED = 42
SENT_AT = date(2025, 6, 1)
CONVERSION_WINDOW_DAYS = 14

# "Истинные" вероятности конверсии по группам — известны только здесь,
# генератору. Реальный лифт в 4 п.п. (8% -> 12%) — правдоподобный, но не
# гарантированно уловимый на n=200 (см. power-анализ).
TRUE_CONTROL_RATE = 0.08
TRUE_TREATMENT_RATE = 0.12


def get_engine():
    return create_engine(
        f"postgresql+psycopg2://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', '')}"
        f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'etl_portfolio')}"
    )


def assign_and_simulate(customer_ids: list[int], rng: np.random.Generator) -> pd.DataFrame:
    """Случайное разбиение 50/50 + симуляция конверсии по группе.
    Возвращает customer_id, variant, sent_at, converted, converted_at."""
    ids = np.array(customer_ids)
    rng.shuffle(ids)
    half = len(ids) // 2
    variant = np.array(["control"] * half + ["treatment"] * (len(ids) - half))

    converted = np.where(
        variant == "control",
        rng.random(len(ids)) < TRUE_CONTROL_RATE,
        rng.random(len(ids)) < TRUE_TREATMENT_RATE,
    )
    days_to_convert = rng.integers(1, CONVERSION_WINDOW_DAYS + 1, size=len(ids))
    converted_at = [
        SENT_AT + timedelta(days=int(d)) if c else None
        for c, d in zip(converted, days_to_convert)
    ]

    return pd.DataFrame({
        "customer_id": ids,
        "variant": variant,
        "sent_at": SENT_AT,
        "converted": converted,
        "converted_at": converted_at,
    })


def main():
    engine = get_engine()
    customers = pd.read_sql("SELECT customer_id FROM stg_customers", engine)
    rng = np.random.default_rng(RNG_SEED)
    experiment = assign_and_simulate(customers["customer_id"].tolist(), rng)

    with engine.begin() as conn:
        conn.execute(text("TRUNCATE TABLE ab_test_email_campaign"))
        experiment.to_sql("ab_test_email_campaign", conn, if_exists="append", index=False)

    counts = experiment.groupby("variant").size().to_dict()
    print(f"Generated experiment: {len(experiment)} customers, groups: {counts}")


if __name__ == "__main__":
    main()
