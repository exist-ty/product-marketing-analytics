"""Одноразовый скрипт: собирает notebooks/analysis.ipynb из ячеек.
Запуск: python scripts/build_notebook.py
После сборки notebook выполняется через:
    jupyter nbconvert --to notebook --execute --inplace notebooks/analysis.ipynb
"""
import nbformat as nbf
from pathlib import Path

nb = nbf.v4.new_notebook()

cells = [
    nbf.v4.new_markdown_cell(
        "# Продуктовая и маркетинговая аналитика\n"
        "\n"
        "Витрины `mart_channel_economics`, `mart_customer_ltv`, `mart_cohort_retention` "
        "(см. `sql/marts.sql`) построены поверх staging-таблиц, которые наполняет ETL-пайплайн "
        "из соседнего репозитория [`etl-portfolio`](../etl-portfolio). Здесь — Python-слой: "
        "визуализация и интерпретация того, что посчитал SQL."
    ),
    nbf.v4.new_code_cell(
        "import os\n"
        "import sys\n"
        "sys.path.insert(0, '..')\n"
        "\n"
        "import pandas as pd\n"
        "import matplotlib.pyplot as plt\n"
        "from dotenv import load_dotenv\n"
        "from sqlalchemy import create_engine\n"
        "\n"
        "from src.analytics.visualization import plot_romi_by_channel\n"
        "\n"
        "load_dotenv('../.env')\n"
        "engine = create_engine(\n"
        "    f\"postgresql+psycopg2://{os.getenv('DB_USER','postgres')}:{os.getenv('DB_PASSWORD','')}\"\n"
        "    f\"@{os.getenv('DB_HOST','localhost')}:{os.getenv('DB_PORT','5432')}/{os.getenv('DB_NAME','etl_portfolio')}\"\n"
        ")\n"
        "plt.rcParams['figure.dpi'] = 110"
    ),
    nbf.v4.new_markdown_cell(
        "## 1. ROMI по каналам\n"
        "\n"
        "Вопрос, который решает эта витрина: **какие каналы приносят прибыль на маркетинговые "
        "вложения, а какие пора отключать или пересматривать**."
    ),
    nbf.v4.new_code_cell(
        "channel_summary = pd.read_sql(\"\"\"\n"
        "    SELECT channel,\n"
        "           SUM(spend) AS total_spend,\n"
        "           SUM(leads) AS total_leads,\n"
        "           SUM(customers_acquired) AS total_customers,\n"
        "           ROUND(SUM(spend) / NULLIF(SUM(leads), 0), 2) AS avg_cpl,\n"
        "           ROUND(SUM(spend) / NULLIF(SUM(customers_acquired), 0), 2) AS avg_cac,\n"
        "           ROUND((SUM(revenue_same_month) - SUM(spend)) / NULLIF(SUM(spend), 0), 3) AS romi\n"
        "    FROM mart_channel_economics\n"
        "    GROUP BY channel\n"
        "    ORDER BY romi DESC\n"
        "\"\"\", engine)\n"
        "channel_summary"
    ),
    nbf.v4.new_markdown_cell(
        "График строит `plot_romi_by_channel` из `src/analytics/visualization.py` — "
        "покрытая тестом функция (`tests/test_visualization.py`), а не одноразовый код "
        "внутри ячейки."
    ),
    nbf.v4.new_code_cell(
        "fig = plot_romi_by_channel(channel_summary)\n"
        "plt.show()"
    ),
    nbf.v4.new_markdown_cell(
        "## 2. LTV: накопительная выручка по номеру заказа\n"
        "\n"
        "`mart_customer_ltv` считает это оконной функцией `SUM() OVER (PARTITION BY customer_id "
        "ORDER BY order_date)` — без единого `GROUP BY`. Здесь агрегируем средний LTV по глубине "
        "заказа, чтобы увидеть, сколько в среднем приносит клиент к N-му заказу."
    ),
    nbf.v4.new_code_cell(
        "ltv_by_seq = pd.read_sql(\"\"\"\n"
        "    SELECT order_seq, AVG(cumulative_revenue) AS avg_cumulative_revenue, COUNT(*) AS customers_reaching\n"
        "    FROM mart_customer_ltv\n"
        "    WHERE order_seq <= 8\n"
        "    GROUP BY order_seq\n"
        "    ORDER BY order_seq\n"
        "\"\"\", engine)\n"
        "\n"
        "# Два раздельных графика с общей осью X вместо twin-axis: разные величины\n"
        "# (деньги и число клиентов) не должны делить одну плоскость с двумя шкалами\n"
        "fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8, 6), sharex=True, height_ratios=[2, 1])\n"
        "\n"
        "ax1.plot(ltv_by_seq['order_seq'], ltv_by_seq['avg_cumulative_revenue'], marker='o', color='#1f77b4')\n"
        "ax1.set_ylabel('Средняя накопительная выручка')\n"
        "ax1.set_title('LTV-кривая: выручка нарастающим итогом по глубине заказа')\n"
        "ax1.grid(axis='y', linestyle='--', alpha=0.4)\n"
        "\n"
        "ax2.bar(ltv_by_seq['order_seq'], ltv_by_seq['customers_reaching'], color='#9467bd')\n"
        "ax2.set_xlabel('Номер заказа клиента')\n"
        "ax2.set_ylabel('Клиентов дошло')\n"
        "\n"
        "plt.tight_layout()\n"
        "plt.show()"
    ),
    nbf.v4.new_markdown_cell(
        "## 3. Ретеншн по когортам\n"
        "\n"
        "`mart_cohort_retention` — классический cohort-анализ: доля клиентов когорты, "
        "оформивших заказ через N месяцев после регистрации."
    ),
    nbf.v4.new_code_cell(
        "cohort = pd.read_sql(\"\"\"\n"
        "    SELECT cohort_month, month_number, retention_rate\n"
        "    FROM mart_cohort_retention\n"
        "    WHERE month_number BETWEEN 0 AND 6\n"
        "\"\"\", engine)\n"
        "\n"
        "pivot = cohort.pivot(index='cohort_month', columns='month_number', values='retention_rate')\n"
        "\n"
        "fig, ax = plt.subplots(figsize=(8, 5))\n"
        "im = ax.imshow(pivot.values, cmap='YlGn', vmin=0, vmax=1, aspect='auto')\n"
        "ax.set_xticks(range(len(pivot.columns)))\n"
        "ax.set_xticklabels(pivot.columns)\n"
        "ax.set_yticks(range(len(pivot.index)))\n"
        "ax.set_yticklabels([str(d) for d in pivot.index])\n"
        "ax.set_xlabel('Месяцев с регистрации')\n"
        "ax.set_ylabel('Когорта (месяц регистрации)')\n"
        "ax.set_title('Retention heatmap по когортам')\n"
        "for i in range(pivot.shape[0]):\n"
        "    for j in range(pivot.shape[1]):\n"
        "        val = pivot.values[i, j]\n"
        "        if pd.notna(val):\n"
        "            ax.text(j, i, f'{val:.0%}', ha='center', va='center', fontsize=8)\n"
        "plt.colorbar(im, ax=ax, label='Retention rate')\n"
        "plt.tight_layout()\n"
        "plt.show()"
    ),
    nbf.v4.new_markdown_cell(
        "## Вывод\n"
        "\n"
        "- **social_ads** и **context_ads** — самые дорогие каналы по CAC при этом с наименьшим ROMI "
        "среди прибыльных: кандидаты на пересмотр бюджета в первую очередь.\n"
        "- **referral** и **email** — низкий CPL/CAC, но и низкий объём: не заменяют платные каналы, "
        "а дополняют.\n"
        "- LTV показывает, что выручка от повторных заказов (2-й, 3-й...) сопоставима с первым — "
        "т.е. remarketing/удержание так же важны, как первичное привлечение.\n"
        "- Retention проседает к 1-му месяцу и частично восстанавливается дальше — типичная картина "
        "для товаров с не-подписочной моделью покупки; здесь стоило бы проверить гипотезу triggers "
        "для повторной покупки во 2-м месяце.\n"
        "\n"
        "**Ограничение методологии**: `revenue_same_month` в `mart_channel_economics` считает выручку "
        "только за тот же календарный месяц, что и трата — это занижает ROMI каналов с более "
        "длинным циклом принятия решения. Более честный расчёт использовал бы окно атрибуции "
        "(например, 60/90 дней) вместо строгого календарного месяца — это в roadmap следующей "
        "итерации витрины."
    ),
]

nb["cells"] = cells

out_path = Path(__file__).parent.parent / "notebooks" / "analysis.ipynb"
out_path.parent.mkdir(parents=True, exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    nbf.write(nb, f)

print(f"Notebook written to {out_path}")
