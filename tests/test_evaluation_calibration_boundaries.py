"""Synthetic metric contracts only; not evidence of model or betting quality."""
import math

import pytest

from hbi.evaluation import calibration_bins


@pytest.mark.parametrize("width,p,low,high", [
    (0.3, 0.95, 0.9, 1.0),
    (0.6, 0.75, 0.6, 1.0),
    (0.05, 0.15, 0.15, 0.2),
    (0.1, 0.3, 0.3, 0.4),
    (0.1, math.nextafter(0.3, 0), 0.2, 0.3),
    (0.1, math.nextafter(0.3, 1), 0.3, 0.4),
    (0.3, 1.0, 0.9, 1.0),
    (1.0, 1.0, 0.0, 1.0),
    (0.3, 0.0, 0.0, 0.3),
])
def test_decimal_boundary_and_short_final_bin(width, p, low, high):
    assert calibration_bins([(p, True)], width=width) == [{
        "bin_low": low, "bin_high": high, "n": 1,
        "mean_predicted": p, "observed_rate": 1.0,
    }]


def test_bin_fix_preserves_all_observations_and_original_probabilities():
    original = [(0.0, False), (0.15, True), (0.3, False), (0.95, True), (1.0, True)]
    saved = list(original)
    rows = calibration_bins(original, width=0.3)
    assert sum(row["n"] for row in rows) == len(original)
    assert sum(row["n"] * row["observed_rate"] for row in rows) == 3
    assert original == saved


@pytest.mark.parametrize("width", [0, -0.1, 1.1, float("nan"), float("inf")])
def test_invalid_width_remains_rejected(width):
    with pytest.raises(ValueError):
        calibration_bins([(0.5, False)], width=width)
