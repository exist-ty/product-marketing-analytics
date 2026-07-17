-- Аналитические витрины поверх staging-таблиц, которые готовит ETL-пайплайн
-- из соседнего репозитория etl-portfolio (stg_customers, stg_orders,
-- stg_marketing_spend в БД etl_portfolio). Здесь только SQL, без Python:
-- пайплайн наполняет данные, этот репозиторий их анализирует.
--
-- Применить: psql -U postgres -d etl_portfolio -f sql/marts.sql

-- Mart: юнит-экономика канала (CAC, CPL, ROMI) по месяцам,
-- с накопительным итогом через оконную функцию
DROP VIEW IF EXISTS mart_channel_economics;
CREATE VIEW mart_channel_economics AS
WITH acquisitions AS (
    SELECT
        channel,
        DATE_TRUNC('month', signup_date)::date AS acquisition_month,
        COUNT(*) AS customers_acquired
    FROM stg_customers
    GROUP BY channel, DATE_TRUNC('month', signup_date)
),
revenue AS (
    SELECT
        c.channel,
        DATE_TRUNC('month', o.order_date)::date AS revenue_month,
        SUM(o.total_amount) AS revenue
    FROM stg_orders o
    JOIN stg_customers c ON c.customer_id = o.customer_id
    GROUP BY c.channel, DATE_TRUNC('month', o.order_date)
)
SELECT
    ms.channel,
    ms.spend_month,
    ms.spend,
    ms.leads,
    ROUND(ms.spend / NULLIF(ms.leads, 0), 2) AS cpl,
    COALESCE(a.customers_acquired, 0) AS customers_acquired,
    ROUND(ms.spend / NULLIF(a.customers_acquired, 0), 2) AS cac,
    COALESCE(r.revenue, 0) AS revenue_same_month,
    ROUND((COALESCE(r.revenue, 0) - ms.spend) / NULLIF(ms.spend, 0), 3) AS romi,
    SUM(ms.spend) OVER (PARTITION BY ms.channel ORDER BY ms.spend_month) AS cumulative_spend,
    SUM(COALESCE(r.revenue, 0)) OVER (PARTITION BY ms.channel ORDER BY ms.spend_month) AS cumulative_revenue
FROM stg_marketing_spend ms
LEFT JOIN acquisitions a ON a.channel = ms.channel AND a.acquisition_month = ms.spend_month
LEFT JOIN revenue r ON r.channel = ms.channel AND r.revenue_month = ms.spend_month;

-- Mart: LTV клиента — накопительная выручка и порядковый номер заказа
-- через оконные функции (без единого GROUP BY)
DROP VIEW IF EXISTS mart_customer_ltv;
CREATE VIEW mart_customer_ltv AS
SELECT
    o.customer_id,
    c.channel,
    o.order_id,
    o.order_date,
    o.total_amount,
    ROW_NUMBER() OVER (PARTITION BY o.customer_id ORDER BY o.order_date) AS order_seq,
    SUM(o.total_amount) OVER (
        PARTITION BY o.customer_id ORDER BY o.order_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_revenue,
    ROUND(AVG(o.total_amount) OVER (PARTITION BY o.customer_id), 2) AS avg_order_value
FROM stg_orders o
JOIN stg_customers c ON c.customer_id = o.customer_id;

-- Mart: помесячный ретеншн по когортам регистрации (классический cohort-анализ)
DROP VIEW IF EXISTS mart_cohort_retention;
CREATE VIEW mart_cohort_retention AS
WITH cohorts AS (
    SELECT
        customer_id,
        DATE_TRUNC('month', signup_date)::date AS cohort_month
    FROM stg_customers
),
cohort_sizes AS (
    SELECT cohort_month, COUNT(*) AS cohort_size
    FROM cohorts
    GROUP BY cohort_month
),
activity AS (
    SELECT DISTINCT
        ch.cohort_month,
        ch.customer_id,
        DATE_TRUNC('month', o.order_date)::date AS active_month
    FROM stg_orders o
    JOIN cohorts ch ON ch.customer_id = o.customer_id
),
activity_with_offset AS (
    SELECT
        cohort_month,
        customer_id,
        (DATE_PART('year', active_month) - DATE_PART('year', cohort_month)) * 12
            + (DATE_PART('month', active_month) - DATE_PART('month', cohort_month)) AS month_number
    FROM activity
)
SELECT
    a.cohort_month,
    a.month_number,
    cs.cohort_size,
    COUNT(DISTINCT a.customer_id) AS active_customers,
    ROUND(COUNT(DISTINCT a.customer_id)::numeric / cs.cohort_size, 3) AS retention_rate
FROM activity_with_offset a
JOIN cohort_sizes cs ON cs.cohort_month = a.cohort_month
WHERE a.month_number >= 0
GROUP BY a.cohort_month, a.month_number, cs.cohort_size
ORDER BY a.cohort_month, a.month_number;
