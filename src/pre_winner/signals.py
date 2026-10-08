"""Confirmed exclusive research tiers, available to decision support without execution."""
import json
from hashlib import sha256

from betting.v33 import divergence

TIERS = [("EXTREME_POS", .075, 1.50), ("STRONG_POS", .050, 1.25),
         ("MOD_POS", .025, 1.15), ("EXTREME_NEG", -.075, .67),
         ("STRONG_NEG", -.050, .75), ("MOD_NEG", -.025, .85)]
TIERS_HASH = sha256(json.dumps(TIERS).encode()).hexdigest()


def classify(pcol, pwin):
    evidence = divergence(pcol, pwin)
    delta, ratio = evidence["delta"], evidence["ratio"]
    for name, d, r in TIERS:
        qualifies = (delta >= d - 1e-12 and ratio >= r - 1e-12) if d > 0 else (
            delta <= d + 1e-12 and ratio <= r + 1e-12)
        if qualifies:
            return {**evidence, "signal": name}
    return {**evidence, "signal": "NONE"}


def collective_consensus(signals):
    pos, neg = signals.count("STRONG_POS"), signals.count("STRONG_NEG")
    return {"DUAL_POOL_STRONG": pos >= 2,
            "COL_CONSENSUS": "CONFLICT" if pos and neg else "POSITIVE" if pos >= 2
            else "NEGATIVE" if neg >= 2 else "INSUFFICIENT"}
