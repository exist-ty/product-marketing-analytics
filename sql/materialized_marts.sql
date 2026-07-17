-- Материализованные версии витрин из sql/marts.sql. Не замена оригиналам —
-- обе версии сознательно существуют рядом (см. README, раздел
-- «Материализованные витрины»), чтобы честно сравнить VIEW (пересчёт на
-- каждый SELECT) и MATERIALIZED VIEW (хранит результат, пересчитывается
-- только по явному REFRESH). Оправдано именно здесь: ETL — батчевый
-- пайплайн, данные меняются раз за прогон, а не непрерывно, значит
-- пересчитывать витрину на каждое чтение дашборда/API — трата, а не гарантия
-- свежести, которая реально нужна.
--
-- Применить: psql -U postgres -d etl_portfolio -f sql/materialized_marts.sql
-- (после sql/marts.sql — оригиналы должны существовать)

DROP MATERIALIZED VIEW IF EXISTS mart_channel_economics_mv;
CREATE MATERIALIZED VIEW mart_channel_economics_mv AS
SELECT * FROM mart_channel_economics;

-- UNIQUE-индекс обязателен для REFRESH ... CONCURRENTLY (см.
-- scripts/refresh_marts.py) — без него PostgreSQL не может понять, какие
-- строки поменялись, и REFRESH блокирует чтение на время пересчёта.
CREATE UNIQUE INDEX idx_mart_channel_economics_mv_pk
    ON mart_channel_economics_mv (channel, spend_month);

DROP MATERIALIZED VIEW IF EXISTS mart_customer_ltv_mv;
CREATE MATERIALIZED VIEW mart_customer_ltv_mv AS
SELECT * FROM mart_customer_ltv;

CREATE UNIQUE INDEX idx_mart_customer_ltv_mv_pk
    ON mart_customer_ltv_mv (order_id);

DROP MATERIALIZED VIEW IF EXISTS mart_cohort_retention_mv;
CREATE MATERIALIZED VIEW mart_cohort_retention_mv AS
SELECT * FROM mart_cohort_retention;

CREATE UNIQUE INDEX idx_mart_cohort_retention_mv_pk
    ON mart_cohort_retention_mv (cohort_month, month_number);
