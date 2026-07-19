-- Схема A/B-теста: email-кампания реактивации (control: обычная тема
-- письма, treatment: персонализированная). Таблица наполняется
-- ab_test/generate_experiment.py, анализируется ab_test/analyze_experiment.py.
--
-- Применить: psql -U postgres -d etl_portfolio -f sql/ab_test_schema.sql

DROP TABLE IF EXISTS ab_test_email_campaign;
CREATE TABLE ab_test_email_campaign (
    customer_id INTEGER PRIMARY KEY REFERENCES stg_customers(customer_id),
    variant TEXT NOT NULL CHECK (variant IN ('control', 'treatment')),
    sent_at DATE NOT NULL,
    converted BOOLEAN NOT NULL,
    converted_at DATE
);
