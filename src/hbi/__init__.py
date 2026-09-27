"""Horse Betting Intelligence (HBI) core package."""

from .conflict import selection_log_ratio_conflict, total_variation_conflict
from .probability import combine_probabilities, fair_odds, normalize_market_odds
from .race_difficulty import RaceDifficultyInput, RaceDifficultyResult, score_race_difficulty

__all__ = [
    "combine_probabilities",
    "fair_odds",
    "normalize_market_odds",
    "selection_log_ratio_conflict",
    "total_variation_conflict",
    "RaceDifficultyInput",
    "RaceDifficultyResult",
    "score_race_difficulty",
]
