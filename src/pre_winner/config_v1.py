"""Confirmed constants only. Unspecified protocol thresholds are never inferred."""
from betting.v33 import POLICY_HASH
from rikstoto_crawler.transport import digest

from .signals import TIERS, TIERS_HASH

CONFIG = {"version": "PRE_WINNER_ENGINE_V1", "signal_policy_hash": POLICY_HASH,
          "primary_max_seconds": 60, "secondary_max_seconds": 300,
          "strong_positive": {"delta": .05, "R": 1.25},
          "strong_negative": {"delta": -.05, "R": .75},
          "exclusive_tiers": TIERS, "tier_policy_hash": TIERS_HASH,
          "multi_pool_scope": "SAME_RACE_HORSE_TIME_CLASS_DISTINCT_PRODUCTS",
          "duplicate_policy": "IDENTICAL_SKIP_CONFLICTING_RACE_QUARANTINE",
          "prospective": False, "outputs": "RESEARCH_ONLY"}
CONFIG_HASH = digest(CONFIG)
