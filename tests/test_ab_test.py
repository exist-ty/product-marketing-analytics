import pytest

from ab_test.analyze_experiment import (
    achieved_power,
    proportion_diff_ci,
    required_sample_size_per_arm,
    srm_check,
    two_proportion_ztest,
)


def test_srm_check_passes_on_balanced_split():
    chi2, p_value = srm_check(100, 100)
    assert chi2 == pytest.approx(0.0)
    assert p_value == pytest.approx(1.0)


def test_srm_check_flags_skewed_split():
    _, p_value = srm_check(70, 130)
    assert p_value < 0.01


def test_two_proportion_ztest_matches_hand_computed_value():
    z, p_value = two_proportion_ztest(8, 100, 12, 100)
    assert z == pytest.approx(0.9428, abs=1e-3)
    assert p_value == pytest.approx(0.3458, abs=1e-3)


def test_proportion_diff_ci_contains_zero_when_not_significant():
    diff, ci_low, ci_high = proportion_diff_ci(8, 100, 12, 100)
    assert diff == pytest.approx(0.04)
    assert ci_low < 0 < ci_high


def test_required_sample_size_exceeds_available_pool():
    # Честная находка проекта: 200 клиентов недостаточно, чтобы уверенно
    # поймать лифт 8% -> 12% — это должно требовать в разы больше на группу,
    # чем есть в датасете (100/группу).
    n_needed = required_sample_size_per_arm(0.08, 0.12)
    assert n_needed > 500


def test_achieved_power_is_low_at_current_sample_size():
    power = achieved_power(0.08, 0.12, 100)
    assert power < 0.30


def test_achieved_power_reaches_target_at_required_sample_size():
    n_needed = required_sample_size_per_arm(0.08, 0.12)
    power = achieved_power(0.08, 0.12, n_needed)
    # required_sample_size_per_arm ceils to a whole number of customers, so
    # the resulting power lands just at (not strictly above) the 80% target.
    assert power == pytest.approx(0.80, abs=1e-2)
