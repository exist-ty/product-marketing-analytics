"""Анализ A/B-теста email-кампании реактивации (ab_test_email_campaign).

Три проверки, в таком порядке:
1. Sample Ratio Mismatch (SRM) — прежде чем верить результату, убеждаемся,
   что рандомизация/трекинг не сломаны (иначе разница в конверсии может
   быть артефактом кривого сплита, а не эффектом варианта).
2. Two-proportion z-test — статистическая значимость разницы в конверсии.
3. Power-анализ — честный ответ на "а могли ли мы вообще это заметить"
   при реальном размере выборки, а не только "значимо / не значимо".

Применить: python ab_test/analyze_experiment.py
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats
from sqlalchemy import create_engine
from dotenv import load_dotenv
import os

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

load_dotenv(PROJECT_ROOT / ".env")

ALPHA = 0.05
TARGET_POWER = 0.80


def get_engine():
    return create_engine(
        f"postgresql+psycopg2://{os.getenv('DB_USER', 'postgres')}:{os.getenv('DB_PASSWORD', '')}"
        f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}/{os.getenv('DB_NAME', 'etl_portfolio')}"
    )


def srm_check(n_control: int, n_treatment: int, expected_ratio: float = 0.5) -> tuple[float, float]:
    """Chi-square goodness-of-fit группы наблюдаемых размеров против
    ожидаемого сплита. Возвращает (chi2, p_value). Низкий p-value (< 0.01
    по конвенции SRM, не 0.05 — ложные срабатывания здесь особенно дорого
    стоят) означает, что рандомизация/трекинг вероятно сломаны."""
    total = n_control + n_treatment
    expected_control = total * expected_ratio
    expected_treatment = total * (1 - expected_ratio)
    chi2, p_value = stats.chisquare(
        f_obs=[n_control, n_treatment],
        f_exp=[expected_control, expected_treatment],
    )
    return chi2, p_value


def two_proportion_ztest(x1: int, n1: int, x2: int, n2: int) -> tuple[float, float]:
    """Пуловый two-proportion z-test. x1/n1 = control, x2/n2 = treatment.
    Возвращает (z_stat, p_value), p_value двусторонний."""
    p1, p2 = x1 / n1, x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    se_pool = np.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    z = (p2 - p1) / se_pool
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))
    return z, p_value


def proportion_diff_ci(x1: int, n1: int, x2: int, n2: int, confidence: float = 0.95) -> tuple[float, float, float]:
    """Wald-доверительный интервал для (p2 - p1) — непуловая SE, отдельно
    от теста значимости (это стандартная практика, тест и CI используют
    разные SE не просто по недосмотру). При n~100/группу Wald может быть
    менее точным, чем Wilson — честная оговорка, не единственно верный метод."""
    p1, p2 = x1 / n1, x2 / n2
    diff = p2 - p1
    se_diff = np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    z_crit = stats.norm.ppf(1 - (1 - confidence) / 2)
    return diff, diff - z_crit * se_diff, diff + z_crit * se_diff


def required_sample_size_per_arm(p1: float, p2: float, alpha: float = ALPHA, power: float = TARGET_POWER) -> int:
    """Необходимый размер выборки НА ГРУППУ для обнаружения разницы p2-p1
    с заданной мощностью (стандартная формула для two-proportion z-test)."""
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    z_beta = stats.norm.ppf(power)
    numerator = (z_alpha + z_beta) ** 2 * (p1 * (1 - p1) + p2 * (1 - p2))
    denominator = (p2 - p1) ** 2
    return int(np.ceil(numerator / denominator))


def achieved_power(p1: float, p2: float, n_per_arm: int, alpha: float = ALPHA) -> float:
    """Мощность, которую реально даёт n_per_arm для обнаружения |p2-p1|
    (нормальное приближение — тот же класс формул, что и required_sample_size_per_arm,
    только в обратную сторону: не 'сколько нужно', а 'что уже есть')."""
    p_bar = (p1 + p2) / 2
    delta = abs(p2 - p1)
    z_alpha = stats.norm.ppf(1 - alpha / 2)
    se_alt = np.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
    numerator = delta * np.sqrt(n_per_arm) - z_alpha * np.sqrt(2 * p_bar * (1 - p_bar))
    return float(stats.norm.cdf(numerator / se_alt))


def main():
    engine = get_engine()
    df = pd.read_sql("SELECT variant, converted FROM ab_test_email_campaign", engine)

    control = df[df["variant"] == "control"]
    treatment = df[df["variant"] == "treatment"]
    n1, n2 = len(control), len(treatment)
    x1, x2 = int(control["converted"].sum()), int(treatment["converted"].sum())
    p1, p2 = x1 / n1, x2 / n2

    print(f"Control:   n={n1}, conversions={x1}, rate={p1:.1%}")
    print(f"Treatment: n={n2}, conversions={x2}, rate={p2:.1%}")
    print()

    chi2, srm_p = srm_check(n1, n2)
    print(f"SRM check: chi2={chi2:.3f}, p={srm_p:.3f} "
          f"({'OK, randomization looks clean' if srm_p >= 0.01 else 'WARNING: possible sample ratio mismatch'})")
    print()

    z, p_value = two_proportion_ztest(x1, n1, x2, n2)
    diff, ci_low, ci_high = proportion_diff_ci(x1, n1, x2, n2)
    print(f"Two-proportion z-test: z={z:.3f}, p={p_value:.3f}")
    print(f"Difference (treatment - control): {diff:+.1%}, 95% CI [{ci_low:+.1%}, {ci_high:+.1%}]")
    print()

    n_needed = required_sample_size_per_arm(p1, p2)
    power_now = achieved_power(p1, p2, n1)
    print(f"Power analysis: at observed rates ({p1:.1%} vs {p2:.1%}), "
          f"achieving {TARGET_POWER:.0%} power needs ~{n_needed} customers per arm.")
    print(f"Current sample gives ~{power_now:.0%} power at n={n1} per arm.")
    print()

    if srm_p < 0.01:
        verdict = "NO SHIP - SRM triggered, results not trustworthy until randomization/tracking is fixed."
    elif p_value < ALPHA:
        verdict = "SHIP - statistically significant lift, and SRM check passed."
    else:
        verdict = ("NO SHIP (inconclusive) - no significant difference detected. Given the power analysis above, "
                   "absence of significance at this sample size does not mean absence of effect.")
    print(f"Verdict: {verdict}")


if __name__ == "__main__":
    main()
