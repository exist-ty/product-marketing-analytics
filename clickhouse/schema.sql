-- ClickHouse: OLAP-слой поверх тех же данных заказов, что источник для
-- sql/marts.sql (Postgres). Задача не заменить Postgres-витрины, а показать
-- вторую половину типичной data-платформы: OLTP/staging в Postgres,
-- аналитические rollup'ы на объёме — в колоночном движке.
--
-- Применить: clickhouse-client --host localhost --multiquery < clickhouse/schema.sql
-- (контейнер поднимается через docker compose up -d clickhouse)

CREATE DATABASE IF NOT EXISTS analytics;

-- Сырые события заказов, реплицированные из Postgres stg_orders/stg_customers
-- (denormalized при загрузке — см. load_to_clickhouse.py). ORDER BY здесь —
-- не ограничение уникальности, а физический порядок хранения на диске:
-- (channel, order_date, customer_id) даёт эффективную фильтрацию и
-- группировку по каналу и диапазону дат — ровно тот access pattern, что у
-- mart_channel_economics в Postgres (../sql/marts.sql).
CREATE TABLE IF NOT EXISTS analytics.order_events
(
    order_id     UInt32,
    customer_id  UInt32,
    channel      LowCardinality(String),
    order_date   Date,
    total_amount Decimal(10, 2)
)
ENGINE = MergeTree
PARTITION BY toYYYYMM(order_date)
ORDER BY (channel, order_date, customer_id);

-- Инкрементальная витрина: выручка и число заказов по каналу/месяцу —
-- аналог mart_channel_economics, но с другой моделью пересчёта (см. README,
-- раздел "OLAP-слой: ClickHouse рядом с Postgres"). AggregatingMergeTree
-- хранит промежуточное состояние агрегатной функции (sumState/countState),
-- а не готовое число: при мёрже частей на диске ClickHouse комбинирует уже
-- посчитанные состояния, а не пересчитывает агрегат с нуля по всей таблице.
-- Плата за это — читать нужно через `-Merge`-комбинатор (пример ниже).
CREATE TABLE IF NOT EXISTS analytics.channel_monthly_revenue
(
    channel       LowCardinality(String),
    revenue_month Date,
    revenue_state AggregateFunction(sum, Decimal(10, 2)),
    orders_state  AggregateFunction(count)
)
ENGINE = AggregatingMergeTree
ORDER BY (channel, revenue_month);

-- MATERIALIZED VIEW с TO — триггер на вставку в order_events: каждый
-- вставленный блок сразу агрегируется и дописывается в
-- channel_monthly_revenue. В отличие от Postgres VIEW (пересчёт на каждый
-- SELECT), здесь агрегат поддерживается инкрементально при загрузке.
CREATE MATERIALIZED VIEW IF NOT EXISTS analytics.channel_monthly_revenue_mv
    TO analytics.channel_monthly_revenue
AS
SELECT
    channel,
    toStartOfMonth(order_date) AS revenue_month,
    sumState(total_amount)     AS revenue_state,
    countState()               AS orders_state
FROM analytics.order_events
GROUP BY channel, revenue_month;

-- Пример чтения витрины (обязательный `-Merge`-комбинатор завершает
-- частичные состояния в готовое число):
--
-- SELECT channel, revenue_month,
--        sumMerge(revenue_state)  AS revenue,
--        countMerge(orders_state) AS orders
-- FROM analytics.channel_monthly_revenue
-- GROUP BY channel, revenue_month
-- ORDER BY channel, revenue_month;
