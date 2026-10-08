"""Full-field identity, market, product and PIT validation before normalization."""
from math import isclose

from betting.v33 import POLICY_HASH
from rikstoto_crawler.extract import PRODUCTS, numeric, utc
from rikstoto_crawler.integrity import cohort

from .normalization import normalize


def validate(row):
    if row["schema_version"] != "RIKSTOTO_PRE_WINNER_ARCHIVE_V2":
        raise ValueError("V2 product/leg metadata required")
    if row["policy_hash"] != POLICY_HASH:
        raise ValueError("signal policy mismatch")
    key, number = row["raceday_key"], row["race_number"]
    if row["race_id"] != f"RIKSTOTO:{key}:{number}" or row["date"] != key[-10:]:
        raise ValueError("race identity mismatch")
    active = set(row["active_field"])
    if len(active) < 2 or len(active) != len(row["active_field"]):
        raise ValueError("invalid active field")
    runners = row["runners"]
    if any(type(r["scratched"]) is not bool for r in runners.values()):
        raise ValueError("unknown scratch status")
    if {n for n, r in runners.items() if not r["scratched"]} != active:
        raise ValueError("active/scratch mismatch")
    identities = [r["horse_id"] for r in runners.values()]
    if not all(identities) or len(set(identities)) != len(identities):
        raise ValueError("ambiguous horse identity")
    for n, r in runners.items():
        if str(r["start_number"]) != n or not n.isdigit() or not r["horse_name"]:
            raise ValueError("runner identity mismatch")
    odds = {n: numeric(runners[n]["win_odds"], minimum=1.000001) for n in sorted(active, key=int)}
    for n in active:
        numeric(runners[n]["place_min"], minimum=1)
        if numeric(runners[n]["place_max"], minimum=1) < runners[n]["place_min"]:
            raise ValueError("inverted PLACE range")
        for field in ("win_updated_at", "place_updated_at"):
            if utc(runners[n][field]).date() != utc(row["race_start"]).date():
                raise ValueError("unrelated market timestamp")
    pwin = normalize(odds, active, odds=True)
    check_distribution(row["pWIN"], pwin)
    for market in ("V", "P"):
        numeric(row["turnover"][market]["nok"], minimum=.01)
    pools = {}
    if not row["collective"]:
        raise ValueError("missing collective markets")
    for pool_id, pool in row["collective"].items():
        product, leg, start = pool["product"], pool["leg"], pool["pool_start_race"]
        if (product not in PRODUCTS or type(leg) is not int or leg < 1
                or pool["pool_race_numbers"][leg - 1] != number
                or pool["pool_race_numbers"][0] != start
                or pool_id != f"{key}#{product}#{start}"):
            raise ValueError("pool/race/product/leg mismatch")
        if set(pool["raw_shares"]) != active:
            raise ValueError("incomplete collective field")
        shares = {n: numeric(pool["raw_shares"][n]) for n in sorted(active, key=int)}
        if any(v > 100 for v in shares.values()):
            raise ValueError("invalid collective percentages")
        pcol = normalize(shares, active)
        check_distribution(pool["pCOL"], pcol)
        timestamp = utc(pool["updated_at"])
        if timestamp.date() > utc(row["race_start"]).date():
            raise ValueError("collective timestamp after race date")
        skew = max(abs((utc(runners[n]["win_updated_at"]) - timestamp).total_seconds()) for n in active)
        if not isclose(numeric(pool["win_skew_seconds"]), skew, abs_tol=1e-6):
            raise ValueError("stored timing mismatch")
        if pool["contemporaneous"] is not (skew <= 60):
            raise ValueError("contemporaneous flag mismatch")
        source = pool["source"]
        if (not source or not source["url"].startswith("https://www.rikstoto.no/api/")
                or len(source["body_sha256"]) != 64):
            raise ValueError("missing collective provenance")
        utc(source["fetched_at"])
        numeric(row["collective_turnover"][pool_id]["nok"], minimum=.01)
        pools[pool_id] = {"pCOL": pcol, "skew": skew, "cohort": cohort(skew)}
    return pwin, pools


def check_distribution(stored, calculated):
    if set(stored) != set(calculated) or any(not isclose(numeric(stored[n]), calculated[n], abs_tol=1e-9)
                                            for n in calculated):
        raise ValueError("stored probability normalization mismatch")
