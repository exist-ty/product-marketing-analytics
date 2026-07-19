"""Monte-Carlo валидация power-анализа из analyze_experiment.py — не
"перезапустить эксперимент на большей выборке, пока не получим p<0.05"
(это была бы подгонка результата), а честная проверка: если формула
achieved_power/required_sample_size_per_arm верна, то доля значимых
результатов в тысяче независимых симуляций должна сходиться к
предсказанной ею мощности. Тот же принцип, что и у
etl-portfolio/scripts/generate_scale_data.py — не подогнать вывод, а
эмпирически подтвердить заявленный порог.

Ничего не пишет в БД — это статистическая проверка формулы, а не
"настоящий" эксперимент (тот уже есть в ab_test_email_campaign, n=200,
честно не значим, см. README).

Применить: python ab_test/simulate_power_validation.py
"""
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ab_test.analyze_experiment import (
    ALPHA,
    achieved_power,
    required_sample_size_per_arm,
    two_proportion_ztest,
)

RNG_SEED = 7
N_SIMULATIONS = 1000
TRUE_CONTROL_RATE = 0.08
TRUE_TREATMENT_RATE = 0.12


def simulate_empirical_power(p1: float, p2: float, n_per_arm: int, n_simulations: int, rng: np.random.Generator) -> float:
    """Доля из n_simulations независимых экспериментов размера n_per_arm/группу,
    в которых two_proportion_ztest находит значимость на уровне ALPHA."""
    significant = 0
    for _ in range(n_simulations):
        x1 = int((rng.random(n_per_arm) < p1).sum())
        x2 = int((rng.random(n_per_arm) < p2).sum())
        p_pool = (x1 + x2) / (2 * n_per_arm)
        if p_pool in (0.0, 1.0):
            # Вырожденный случай (все или ни одной конверсии в обеих группах) —
            # тестовая статистика не определена (деление на ноль в SE), это по
            # построению не значимый результат, не баг подсчёта.
            continue
        _, p_value = two_proportion_ztest(x1, n_per_arm, x2, n_per_arm)
        if p_value < ALPHA:
            significant += 1
    return significant / n_simulations


def main():
    rng = np.random.default_rng(RNG_SEED)
    n_needed = required_sample_size_per_arm(TRUE_CONTROL_RATE, TRUE_TREATMENT_RATE)

    print(f"True rates: control={TRUE_CONTROL_RATE:.0%}, treatment={TRUE_TREATMENT_RATE:.0%}")
    print(f"Required n per arm for 80% power (formula): {n_needed}")
    print()

    for label, n_per_arm in [("current real sample (n=100/arm)", 100), (f"required sample (n={n_needed}/arm)", n_needed)]:
        theoretical = achieved_power(TRUE_CONTROL_RATE, TRUE_TREATMENT_RATE, n_per_arm)
        empirical = simulate_empirical_power(TRUE_CONTROL_RATE, TRUE_TREATMENT_RATE, n_per_arm, N_SIMULATIONS, rng)
        print(f"{label}:")
        print(f"  Theoretical power (formula): {theoretical:.1%}")
        print(f"  Empirical power ({N_SIMULATIONS} simulations): {empirical:.1%}")
        print()


if __name__ == "__main__":
    main()
