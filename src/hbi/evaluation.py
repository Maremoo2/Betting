from __future__ import annotations

import math
from collections.abc import Iterable, Mapping


def multiclass_brier(predicted: Mapping[str, float], winner: str) -> float:
    if winner not in predicted:
        raise ValueError("winner must be present in predicted field")
    return sum(
        (probability - (1.0 if selection == winner else 0.0)) ** 2
        for selection, probability in predicted.items()
    )


def log_loss(predicted: Mapping[str, float], winner: str, epsilon: float = 1e-15) -> float:
    if winner not in predicted:
        raise ValueError("winner must be present in predicted field")
    p = max(min(predicted[winner], 1 - epsilon), epsilon)
    return -math.log(p)


def calibration_bins(
    probabilities_and_outcomes: Iterable[tuple[float, bool]],
    *,
    width: float = 0.05,
) -> list[dict[str, float | int]]:
    if not 0 < width <= 1:
        raise ValueError("width must be in (0, 1]")
    bins: dict[int, list[tuple[float, bool]]] = {}
    for probability, outcome in probabilities_and_outcomes:
        if not 0 <= probability <= 1:
            raise ValueError("probabilities must be in [0, 1]")
        index = min(int(probability / width), int(1 / width) - 1)
        bins.setdefault(index, []).append((probability, outcome))

    output: list[dict[str, float | int]] = []
    for index in sorted(bins):
        values = bins[index]
        output.append(
            {
                "bin_low": round(index * width, 6),
                "bin_high": round(min((index + 1) * width, 1.0), 6),
                "n": len(values),
                "mean_predicted": sum(p for p, _ in values) / len(values),
                "observed_rate": sum(1 for _, outcome in values if outcome) / len(values),
            }
        )
    return output
