"""Строит customer-level датасет для churn-классификации из тех же
stg_customers/stg_orders, что и sql/marts.sql (etl-portfolio). Отдельно от
март-витрин: там аналитика по каналам/когортам, здесь — один ряд на клиента
для sklearn.

Churn определён поведенчески (нет явного события "отписки"): клиент считается
оттёкшим, если его последний заказ старше CHURN_WINDOW_DAYS относительно
CUTOFF_DATE. CUTOFF_DATE = последняя дата заказа в датасете (граница
"настоящего" в этих синтетических данных). Проверено: все клиенты
зарегистрированы минимум за CHURN_WINDOW_DAYS до cutoff, так что нет
"свежих" клиентов, которых нечестно засчитали бы в отток — цензурирования
по времени наблюдения здесь нет.
"""
import sys
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine
from dotenv import load_dotenv
import os

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

CHURN_WINDOW_DAYS = 90


def get_engine():
    return create_engine(
        f"postgresql+psycopg2://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', '')}"
        f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'etl_portfolio')}"
    )


def build_customer_features(customers: pd.DataFrame, orders: pd.DataFrame, cutoff_date, churn_window_days: int) -> pd.DataFrame:
    """customers: customer_id, channel, signup_date.
    orders: customer_id, order_date, total_amount.
    Один ряд на клиента (все клиенты имеют >=1 заказ в этом датасете)."""
    agg = orders.groupby("customer_id").agg(
        total_orders=("order_date", "count"),
        total_revenue=("total_amount", "sum"),
        avg_order_value=("total_amount", "mean"),
        first_order_date=("order_date", "min"),
        last_order_date=("order_date", "max"),
    )

    df = customers.set_index("customer_id").join(agg, how="inner")

    df["tenure_days"] = (cutoff_date - df["signup_date"]).dt.days
    df["days_since_last_order"] = (cutoff_date - df["last_order_date"]).dt.days
    df["first_order_gap_days"] = (df["first_order_date"] - df["signup_date"]).dt.days
    df["order_frequency"] = df["total_orders"] / df["tenure_days"].clip(lower=1)
    df["avg_order_value"] = df["avg_order_value"].round(2)

    df["churned"] = (df["days_since_last_order"] > churn_window_days).astype(int)

    return df[[
        "channel", "tenure_days", "total_orders", "total_revenue", "avg_order_value",
        "first_order_gap_days", "order_frequency", "days_since_last_order", "churned",
    ]].reset_index()


def main() -> None:
    engine = get_engine()
    customers = pd.read_sql("SELECT customer_id, channel, signup_date FROM stg_customers", engine, parse_dates=["signup_date"])
    orders = pd.read_sql("SELECT customer_id, order_date, total_amount FROM stg_orders", engine, parse_dates=["order_date"])

    cutoff_date = orders["order_date"].max()
    min_signup_to_cutoff = (cutoff_date - customers["signup_date"]).dt.days.min()
    if min_signup_to_cutoff < CHURN_WINDOW_DAYS:
        print(
            f"WARNING: youngest customer has only {min_signup_to_cutoff}d before cutoff "
            f"(< {CHURN_WINDOW_DAYS}d churn window) — label may be unfair for recent signups"
        )

    features = build_customer_features(customers, orders, cutoff_date, CHURN_WINDOW_DAYS)

    out_path = Path(__file__).parent / "data" / "churn_features.csv"
    out_path.parent.mkdir(exist_ok=True)
    features.to_csv(out_path, index=False)

    print(f"cutoff_date={cutoff_date.date()}, churn_window={CHURN_WINDOW_DAYS}d")
    print(f"{len(features)} customers, churn rate = {features['churned'].mean():.1%}")
    print(f"Saved {out_path}")


if __name__ == "__main__":
    main()
