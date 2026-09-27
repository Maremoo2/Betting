"""Horse Betting Intelligence (HBI) core package."""

from .probability import combine_probabilities, fair_odds, normalize_market_odds
from .race_difficulty import RaceDifficultyInput, RaceDifficultyResult, score_race_difficulty

__all__ = [
    "combine_probabilities",
    "fair_odds",
    "normalize_market_odds",
    "RaceDifficultyInput",
    "RaceDifficultyResult",
    "score_race_difficulty",
]
