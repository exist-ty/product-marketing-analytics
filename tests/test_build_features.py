import pandas as pd

from ml.build_features import build_customer_features


def test_churn_label_uses_90_day_recency_window():
    cutoff = pd.Timestamp("2025-12-31")
    customers = pd.DataFrame([
        {"customer_id": 1, "channel": "seo", "signup_date": pd.Timestamp("2025-01-01")},
        {"customer_id": 2, "channel": "seo", "signup_date": pd.Timestamp("2025-01-01")},
    ])
    orders = pd.DataFrame([
        {"customer_id": 1, "order_date": pd.Timestamp("2025-12-20"), "total_amount": 100.0},  # recent -> active
        {"customer_id": 2, "order_date": pd.Timestamp("2025-06-01"), "total_amount": 50.0},   # >90d -> churned
    ])

    features = build_customer_features(customers, orders, cutoff, churn_window_days=90)
    result = features.set_index("customer_id")["churned"]

    assert result.loc[1] == 0
    assert result.loc[2] == 1


def test_total_revenue_and_avg_order_value_are_aggregated_per_customer():
    cutoff = pd.Timestamp("2025-12-31")
    customers = pd.DataFrame([{"customer_id": 1, "channel": "seo", "signup_date": pd.Timestamp("2025-01-01")}])
    orders = pd.DataFrame([
        {"customer_id": 1, "order_date": pd.Timestamp("2025-02-01"), "total_amount": 100.0},
        {"customer_id": 1, "order_date": pd.Timestamp("2025-03-01"), "total_amount": 50.0},
    ])

    features = build_customer_features(customers, orders, cutoff, churn_window_days=90)
    row = features.iloc[0]

    assert row["total_orders"] == 2
    assert row["total_revenue"] == 150.0
    assert row["avg_order_value"] == 75.0
