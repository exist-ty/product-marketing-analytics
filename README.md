# Product & Marketing Analytics

![Tests](https://github.com/exist-ty/product-marketing-analytics/actions/workflows/test.yml/badge.svg)

Пет-проект уровня Data/Product Analyst: SQL-витрины и Python-визуализация поверх
staging-слоя, который готовит соседний ETL-репозиторий
[`etl-portfolio`](../etl-portfolio). Разделение осознанное: там — приём и
очистка сырых данных, здесь — их анализ и бизнес-интерпретация.

Три вопроса, на которые отвечает этот репозиторий:

1. Какие каналы привлечения окупаются (CAC/CPL/ROMI), а какие пора остановить?
2. Сколько в среднем приносит клиент к N-му заказу (LTV)?
3. Как быстро "отваливаются" клиенты после регистрации (cohort retention)?
4. Можно ли предсказать отток клиента по его поведению до того, как он ушёл?
5. Как выглядит тот же rollup-запрос в колоночном OLAP-движке (ClickHouse) —
   и где реально проходит граница, после которой он обгоняет Postgres?

## Стек

PostgreSQL (window functions, CTE), ClickHouse (MergeTree, AggregatingMergeTree),
Python (pandas, matplotlib, scikit-learn), Jupyter.

## Структура

- `sql/marts.sql` — три VIEW поверх `stg_customers` / `stg_orders` / `stg_marketing_spend`
- `notebooks/analysis.ipynb` — выполненный ноутбук с графиками и интерпретацией (открывается прямо на GitHub)
- `src/analytics/visualization.py` — тестируемая функция построения ROMI-графика
- `ml/build_features.py` — customer-level датасет для churn-классификации (label + фичи)
- `ml/train_churn_model.py` — Logistic Regression / Random Forest, ROC-AUC, PR-AUC, feature importance
- `clickhouse/schema.sql` — `order_events` (MergeTree) + инкрементальная
  витрина `channel_monthly_revenue` (AggregatingMergeTree + MATERIALIZED VIEW)
- `clickhouse/load_to_clickhouse.py` — реплицирует `stg_orders`/`stg_customers`
  из Postgres в ClickHouse (идемпотентно, TRUNCATE перед вставкой)
- `clickhouse/compare_engines.py` — честный замер: та же агрегация в Postgres
  VIEW-стиле vs ClickHouse (с нуля / через инкрементальную витрину)
- `tests/` — pytest для `visualization.py`, `ml/build_features.py` и
  `clickhouse/load_to_clickhouse.py`

## Как запустить

Требует запущенный и наполненный `etl-portfolio` (см. его README) — эта база
и есть источник данных.

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env   # указать пароль от того же etl_portfolio
psql -U postgres -d etl_portfolio -f sql/marts.sql
jupyter nbconvert --to notebook --execute --inplace notebooks/analysis.ipynb
python ml/build_features.py
python ml/train_churn_model.py
pytest
```

Для ClickHouse-слоя дополнительно (после `docker compose up -d clickhouse`,
креды в `.env` — `CLICKHOUSE_USER`/`CLICKHOUSE_PASSWORD`):

```
clickhouse-client --host localhost --multiquery < clickhouse/schema.sql
python clickhouse/load_to_clickhouse.py
python clickhouse/compare_engines.py
```

## Витрины (`sql/marts.sql`)

- **`mart_channel_economics`** — CAC, CPL, ROMI по каналу/месяцу + накопительный
  спенд/выручка через `SUM() OVER (PARTITION BY channel ORDER BY spend_month)`.
- **`mart_customer_ltv`** — накопительная выручка клиента и номер заказа через
  `ROW_NUMBER()` / `SUM() OVER (...ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)`,
  без единого `GROUP BY`.
- **`mart_cohort_retention`** — классический cohort-анализ: CTE считает размер
  когорты по месяцу регистрации, затем помесячную долю вернувшихся клиентов.

## Результаты на текущем датасете

Витрины посчитаны на реально сгенерированных и загруженных данных (200 клиентов,
~2000 заказов, 72 месяца×канала маркетингового спенда) — не придуманы вручную.

**ROMI по каналам за весь период** (доход того же месяца минус спенд, к спенду):

| channel | total spend | avg CPL | avg CAC | ROMI |
|---|---|---|---|---|
| referral | 639 | 11.6 | 23.7 | **+78.9** |
| seo | 3 007 | 15.1 | 68.3 | +22.0 |
| email | 647 | 5.8 | 38.1 | +19.4 |
| context_ads | 9 309 | 45.0 | 131.1 | +16.7 |
| social_ads | 7 540 | 33.5 | 183.9 | **+10.1** |

Вывод: `social_ads` и `context_ads` тянут больше всего бюджета при самом слабом
ROMI среди прибыльных каналов — первые кандидаты на пересмотр (см. график в
ноутбуке, где отдельные месяцы этих каналов уходят в отрицательный ROMI).

**В деньгах**: на каждый потраченный $1 `social_ads` и `context_ads` возвращают
$11.1 и $11.7 выручки того же месяца, `referral` — $79.9. Но это не значит
"просто перелить бюджет в referral" — абсолютный spend `referral` за весь
период (639) на порядок меньше, чем у `social_ads` (7 540): высокий ROMI
здесь считается на маленькой базе (сарафанное радио/реферальная программа
физически не масштабируется линейно с бюджетом), тогда как `social_ads` и
`context_ads` — каналы с доказанным объёмом, где решение "снизить спенд на
X%" реалистично оценить в деньгах уже сейчас, не дожидаясь более сложной
модели предельной отдачи (marginal ROMI) по каждому каналу.

**LTV**: средняя накопительная выручка растёт с 508 у.е. к 1-му заказу до
~2 529 у.е. к 5-му (из 200 клиентов до 5-го заказа доходят 192) — повторные
заказы дают сопоставимую с первым заказом выручку, удержание так же важно,
как первичное привлечение.

**Retention**: в среднем по когортам ~59% клиентов оформляют повторный заказ в
тот же месяц регистрации, к 1-му месяцу проседает до ~47%, дальше колеблется
55-71% без устойчивого тренда на этом объёме данных.

Полные графики (ROMI bar chart, LTV-кривая, cohort heatmap) и интерпретация —
в [`notebooks/analysis.ipynb`](notebooks/analysis.ipynb).

## Ограничение методологии

`revenue_same_month` в `mart_channel_economics` считает выручку только за тот
же календарный месяц, что и маркетинговый спенд — это занижает ROMI каналов с
более длинным циклом принятия решения (типично для B2B/дорогих товаров).
Более честный расчёт использовал бы окно атрибуции (например, 60/90 дней)
вместо строгого календарного месяца — следующий шаг для этой витрины.

## Предиктивный ML: churn prediction (`ml/`)

Мост от описательной аналитики (LTV, cohort retention) к предиктивной:
бинарная классификация оттока клиента.

**Label.** Явного события "отписки" в данных нет, поэтому отток определён
поведенчески: клиент считается оттёкшим, если последний заказ старше 90 дней
относительно `cutoff = max(order_date)` в датасете. Проверено: все клиенты
зарегистрированы минимум за 90 дней до cutoff — цензурирования по времени
наблюдения нет (не засчитываем "свежих" клиентов в отток нечестно).

**Признаки** (`ml/build_features.py`, один ряд на клиента): `total_orders`,
`total_revenue`, `avg_order_value`, `tenure_days`, `first_order_gap_days`,
`order_frequency`, `channel`. `days_since_last_order` в датасет входит, но
**не** используется как фича — это то же поле, из которого построен label
(иначе — target leakage).

**Обучение** (`ml/train_churn_model.py`): stratified train/test split (75/25),
`class_weight="balanced"` в обеих моделях — на 200 клиентах отток случается в
8.5% случаев (17 из 200), без балансировки классификатор просто предсказывал
бы "не ушёл" всегда и получал 91.5% accuracy при нулевой пользе.

| Модель | ROC-AUC | PR-AUC |
|---|---|---|
| Logistic Regression | 0.52 | 0.13 |
| Random Forest | 0.44 | 0.11 |

ROC-кривые и важность признаков (RF `feature_importances_`, LR-коэффициенты
на стандартизированных фичах):

![ROC curves](ml/plots/roc_curves.png)
![Random Forest feature importance](ml/plots/rf_feature_importance.png)
![Logistic Regression coefficients](ml/plots/lr_coefficients.png)

**Честный результат: AUC на уровне случайного угадывания — и это ожидаемо.**
`scripts/generate_data.py` (etl-portfolio) назначает `channel` клиенту и
частоту заказов случайно, без встроенного механизма "этот клиент похож на
тех, кто уходит" — в данных физически нет сигнала, который отличал бы
будущих отточных клиентов от активных. Модель, показывающая AUC≈0.5 на
данных без сигнала — это correct, не баг. Демонстрируется здесь не
"предсказательная сила на реальном бизнесе" (бизнеса нет, данные
синтетические), а сам workflow: honest train/test split, обработка
дисбаланса классов, набор метрик, интерпретация важности признаков — то,
что применяется к реальным данным без изменений. Дополнительное ограничение:
17 положительных примеров на весь датасет (4 в тестовой выборке) — при таком
n любая метрика шумит, доверительный интервал по ROC-AUC здесь шире, чем
разница между моделями.

## OLAP-слой: ClickHouse рядом с Postgres (`clickhouse/`)

Все витрины выше — Postgres VIEW: пересчитываются целиком на каждый SELECT.
Это нормально для этого объёма (~2000 заказов), но не масштабируется на
десятки/сотни миллионов строк. Рядом со staging-слоем поднят второй,
OLAP-профилированный движок на тех же исходных данных — не замена
Postgres-витринам, а демонстрация второй половины типичной data-платформы
(OLTP/staging + OLAP-аналитика).

**Схема (`clickhouse/schema.sql`).** `order_events` — `MergeTree`,
`PARTITION BY toYYYYMM(order_date)`, `ORDER BY (channel, order_date,
customer_id)`: физический порядок хранения на диске под access pattern
"фильтр/группировка по каналу и диапазону дат", тот же, что у
`mart_channel_economics`. Поверх — `channel_monthly_revenue`
(`AggregatingMergeTree`) и `MATERIALIZED VIEW ... TO`, который агрегирует
каждый вставляемый блок сразу при загрузке (`sumState`/`countState`), а не
при чтении: агрегат читается через `-Merge`-комбинаторы
(`sumMerge`/`countMerge`), которые лишь комбинируют уже посчитанные
состояния — принципиально другая модель пересчёта, чем у Postgres VIEW.

**Загрузка (`clickhouse/load_to_clickhouse.py`).** Реплицирует
`stg_orders`/`stg_customers` из Postgres, денормализует `channel` на каждый
заказ при загрузке (типичный OLAP-паттерн: JOIN один раз при вставке, а не
на каждый аналитический запрос). Идемпотентно — `TRUNCATE` перед вставкой,
как в transform-слое `etl-portfolio`.

**Честный замер (`clickhouse/compare_engines.py`).** Один и тот же запрос
("выручка по каналу/месяцу") тремя способами, медиана из 20 прогонов на
реальных 1985 заказах:

| Способ | Медианное время |
|---|---|
| Postgres VIEW-стиль (пересчёт с нуля) | **2.1 ms** |
| ClickHouse, агрегация сырых событий с нуля | 13.2 ms |
| ClickHouse, чтение инкрементальной витрины (`-Merge`) | 5.3 ms |

**На этом объёме данных Postgres быстрее ClickHouse во всех трёх вариантах**
— в том числе быстрее собственной инкрементальной витрины ClickHouse. Это не
баг замера, а честный и объяснимый результат: колоночный движок платит
фиксированную цену за HTTP-запрос и за то, что 60 итоговых строк — это
меньше, чем накладные расходы движка, спроектированного сканировать
миллиарды. Реальное преимущество `MergeTree`/колоночного хранения и
инкрементальных агрегатов проявляется на объёмах, которые физически не
влезают в план Postgres целиком в память или требуют полного
пересканирования при каждом запросе — не на 2000 строках синтетического
пет-проекта. Демонстрируется здесь архитектура (как правильно спроектировать
`ORDER BY`/`PARTITION BY`/инкрементальный rollup), а не измеренный выигрыш —
и это указано прямо, а не скрыто за круглыми цифрами.

## Дашборд

**Metabase (self-hosted, Docker)** — интерактивный дашборд поверх той же
Postgres, что использует пайплайн:

```
docker compose up -d
```

Открыть `http://localhost:3000`, при первом запуске добавить источник
данных Postgres: host `host.docker.internal`, port `5432`, database
`etl_portfolio` (те же креды, что в `.env`). После подключения витрины
`mart_channel_economics` / `mart_customer_ltv` / `mart_cohort_retention`
доступны Metabase напрямую как обычные таблицы.
