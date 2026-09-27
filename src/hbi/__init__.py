"""Horse Betting Intelligence (HBI) core package."""

from .benchmark import closing_line_value, evaluate_against_market
from .conflict import selection_log_ratio_conflict, total_variation_conflict
from .decision import DecisionPolicy, ValueAssessment, assess_value
from .engine import CombinationPolicy, RaceDecisionResult, evaluate_race
from .probability import combine_probabilities, fair_odds, normalize_market_odds
from .race_difficulty import RaceDifficultyInput, RaceDifficultyResult, score_race_difficulty

__all__ = [
    "CombinationPolicy",
    "DecisionPolicy",
    "RaceDecisionResult",
    "RaceDifficultyInput",
    "RaceDifficultyResult",
    "ValueAssessment",
    "assess_value",
    "closing_line_value",
    "combine_probabilities",
    "evaluate_against_market",
    "evaluate_race",
    "fair_odds",
    "normalize_market_odds",
    "score_race_difficulty",
    "selection_log_ratio_conflict",
    "total_variation_conflict",
]
