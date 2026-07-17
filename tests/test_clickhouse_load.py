import pandas as pd

from clickhouse.load_to_clickhouse import orders_to_rows


def test_orders_to_rows_denormalizes_channel_onto_each_order():
    orders = pd.DataFrame([
        {"order_id": 1, "customer_id": 10, "order_date": pd.Timestamp("2025-01-01"), "total_amount": 100.0},
        {"order_id": 2, "customer_id": 20, "order_date": pd.Timestamp("2025-01-02"), "total_amount": 50.0},
    ])
    customers = pd.DataFrame([
        {"customer_id": 10, "channel": "seo"},
        {"customer_id": 20, "channel": "referral"},
    ])

    result = orders_to_rows(orders, customers)

    assert list(result.columns) == ["order_id", "customer_id", "channel", "order_date", "total_amount"]
    assert result.set_index("order_id")["channel"].to_dict() == {1: "seo", 2: "referral"}


def test_orders_to_rows_drops_orders_with_unknown_customer():
    orders = pd.DataFrame([
        {"order_id": 1, "customer_id": 10, "order_date": pd.Timestamp("2025-01-01"), "total_amount": 100.0},
        {"order_id": 2, "customer_id": 999, "order_date": pd.Timestamp("2025-01-02"), "total_amount": 50.0},
    ])
    customers = pd.DataFrame([{"customer_id": 10, "channel": "seo"}])

    result = orders_to_rows(orders, customers)

    assert len(result) == 1
    assert result.iloc[0]["order_id"] == 1
