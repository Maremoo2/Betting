"""CORE-004: read-only, deliberately *unfitted* market-free multifactor research.

Only lifetime wins, places, earnings and number of starts are scored. All other
handicapping factors are explicitly recorded as unmodelled/missing. Neither this
candidate nor its probability estimates are licensed for WATCH/BET/EV use.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .core_shadow_pilot import _atg_history_source_diagnostic
from .race_core_review import _rows, _utc, historical_win_prior

MODEL_ID = "CORE_004_EXPLORATORY_MULTIFACTOR_V0_NOT_FITTED"
REQUIRED = (
    "history_total_starts",
    "history_total_wins",
    "history_total_seconds",
    "history_total_thirds",
    "history_total_earnings",
)
SCORED_FACTORS = ("career_win_baseline", "career_top3_rate", "career_earnings_per_start", "career_experience")
NOT_SCORED = (
    "recent_5_starts_form", "distance_specific_form", "start_method_specific_form",
    "driver_track_record", "class_adjustment", "pace_or_sectionals",
    "post_position_effect", "age_effect", "trainer_effect",
)


@dataclass(frozen=True)
class ExperimentalCoefficients:
    """Predeclared illustrative weights; NO fitting or performance claim."""

    top3: float = 0.20
    earnings_per_start: float = 0.10
    experience: float = 0.05

    def __post_init__(self) -> None:
        for value in asdict(self).values():
            if not math.isfinite(value) or not 0 <= value <= 0.5:
                raise ValueError("Experimental weights must be finite and 0..0.5")


def _integer(value: Any) -> int | None:
    if type(value) is int and value >= 0:
        return value
    return None


def _earnings(value: Any) -> float | None:
    if type(value) not in (float, int):
        return None
    number = float(value)
    return number if math.isfinite(number) and 0 <= number <= 1e16 else None


def _standardize(values: dict[str, float]) -> dict[str, float]:
    """Within-race centred and capped features, no cross-currency comparisons."""
    if not values:
        return {}
    mean = sum(values.values()) / len(values)
    spread = math.sqrt(sum((v - mean) ** 2 for v in values.values()) / len(values))
    if spread < 1e-12:
        return {k: 0.0 for k in values}
    return {k: max(-2., min(2., (v-mean)/spread)) for k, v in values.items()}


def _latest_asof_fundamental_cohort(
    conn: sqlite3.Connection, race_id: str, cutoff: datetime,
) -> tuple[list[dict[str, Any]], str | None, list[str]]:
    """Use one complete observed-time cohort, comparing actual instants, not ISO strings.

    A newer partial cohort must block rather than silently reverting to an older
    complete one. Invalid or future feature time invalidates the chosen cohort.
    """
    issues: list[str] = []
    times = _rows(conn, "SELECT DISTINCT observed_at_utc FROM runner_fundamental_snapshots WHERE race_id=?", (race_id,))
    eligible: list[tuple[datetime, str]] = []
    for item in times:
        stamp = item.get("observed_at_utc")
        try:
            instant = _utc(str(stamp)).astimezone(UTC)
        except ValueError:
            issues.append("INVALID_OBSERVATION_TIMESTAMP")
            continue
        if instant <= cutoff:
            eligible.append((instant, str(stamp)))
    if not eligible:
        return [], None, sorted(set(issues))
    _, raw_at = max(eligible, key=lambda entry:(entry[0],entry[1]))
    cohort = _rows(conn, "SELECT * FROM runner_fundamental_snapshots WHERE race_id=? AND observed_at_utc=?", (race_id,raw_at))
    for row in cohort:
        try:
            t = _utc(str(row["feature_as_of_utc"])).astimezone(UTC)
            if t > cutoff:
                issues.append("FEATURE_AS_OF_AFTER_CUTOFF")
        except ValueError:
            issues.append("INVALID_FEATURE_TIMESTAMP")
    return cohort, raw_at, sorted(set(issues))


def _field_features(fund: list[dict[str, Any]], roster: list[dict[str, Any]]) -> tuple[dict[str, dict[str, float]], list[str]]:
    blockers: set[str] = set()
    roster_ids = [str(r["selection_id"]) for r in roster]
    fund_ids = [str(r["selection_id"]) for r in fund]
    if not roster_ids:
        blockers.add("NO_CANONICAL_ROSTER")
    if len(set(roster_ids)) != len(roster_ids) or len(set(fund_ids)) != len(fund_ids):
        blockers.add("DUPLICATE_SELECTIONS")
    if set(roster_ids) != set(fund_ids):
        blockers.add("FUNDAMENTAL_FIELD_MISMATCH")
    roster_by = {str(r["selection_id"]): r for r in roster}
    features: dict[str, dict[str, float]] = {}
    for row in fund:
        sel = str(row["selection_id"])
        rr = roster_by.get(sel)
        if rr is None or bool(row.get("scratched")) != bool(rr["scratched"]):
            blockers.add("SCRATCH_OR_IDENTITY_MISMATCH")
            continue
        if bool(row.get("scratched")):
            continue
        if row.get("full_field_history_complete") != 1 or not row.get("source_uri"):
            blockers.add("UNVERIFIED_FULL_FIELD_HISTORY")
            continue
        values = [_integer(row.get(k)) for k in REQUIRED[:4]]
        earn = _earnings(row.get(REQUIRED[4]))
        if any(v is None for v in values) or earn is None:
            blockers.add("MISSING_OR_INVALID_MULTIFACTOR_INPUT")
            continue
        starts, wins, seconds, thirds = values
        if wins > starts or wins + seconds + thirds > starts:
            blockers.add("IMPOSSIBLE_FINISH_COUNTS")
            continue
        # All measures use pre-race lifetime observations, never an observed result.
        # EB top-3 prior is 3/n, distinct from the Champion win prior of 1/n.
        features[sel] = {
            "starts": float(starts), "wins": float(wins),
            "seconds": float(seconds), "thirds": float(thirds),
            "earnings_source_units": earn,
        }
    if len(features) < 2:
        blockers.add("INSUFFICIENT_VERIFIED_ACTIVE_FIELD")
    return features, sorted(blockers)


def analyze_multifactor(
    conn: sqlite3.Connection, *, race_id: str, as_of: str,
    weights: ExperimentalCoefficients | None = None,
) -> dict[str, Any]:
    """As-of market-FREE candidate p(win); reject any incomplete fundamental field."""
    weights = weights or ExperimentalCoefficients()
    cutoff = _utc(as_of).astimezone(UTC)
    races = _rows(conn, "SELECT * FROM races WHERE race_id=?", (race_id,))
    if len(races) != 1:
        raise ValueError("Unknown or ambiguous race_id")
    race = races[0]
    start = _utc(str(race["start_time_utc"])).astimezone(UTC)
    blocks = []
    if cutoff >= start:
        blocks.append("NOT_BEFORE_RECORDED_START")
    # Research-only safety: mutable canonical start may be later than the
    # start already documented by a retained independent ATG source.
    # An earlier source clock constrains T-4 even if no real off-time is proven.
    source = _atg_history_source_diagnostic(
        conn, race_id=race_id,
        cutoff=min(cutoff, start - timedelta(minutes=4)),
    )
    earlier = (
        source.get("earliest_retained_source_start_utc") if source else None
    )
    source_start = _utc(earlier).astimezone(UTC) if earlier else None
    if source_start is not None and cutoff > source_start - timedelta(minutes=4):
        blocks.append("ASOF_AFTER_EARLIEST_SOURCE_T4")
    if source and source.get("source_clock_invalid"):
        blocks.append("INVALID_ARCHIVED_SOURCE_CLOCK")
    roster = _rows(conn, "SELECT selection_id,horse_name,post_position,driver_or_jockey,trainer,scratched FROM runners WHERE race_id=?", (race_id,))
    cohort, observed_at, time_issues = _latest_asof_fundamental_cohort(conn, race_id, cutoff)
    features, problems = _field_features(cohort, roster)
    blocks.extend(problems)
    blocks.extend(time_issues)
    if not observed_at:
        blocks.append("NO_FUNDAMENTAL_COHORT_AS_OF")
    # A mutable current roster does not provide point-in-time scratch evidence.
    active_ids = {str(r["selection_id"]) for r in roster if not r["scratched"]}
    if set(features) != active_ids:
        blocks.append("INCOMPLETE_ACTIVE_FIELD")
    p0, known = historical_win_prior(cohort)
    if known != len(active_ids) or set(p0) != active_ids:
        blocks.append("CHAMPION_BASELINE_NOT_COMPLETE")
    blocks = sorted(set(blocks))
    scored: dict[str, dict[str, float]] = {}
    probs: dict[str, float] = {}
    if not blocks:
        n = len(features)
        place = {
            sid: (f["wins"]+f["seconds"]+f["thirds"]+6*min(1.0, 3/n))/(f["starts"]+6)
            for sid, f in features.items()
        }
        # Earnings are source-native (no FX conversion) and compared ONLY inside one race.
        earn = {sid: math.log1p(f["earnings_source_units"]/(f["starts"]+1)) for sid,f in features.items()}
        exp = {sid: math.log1p(f["starts"]) for sid,f in features.items()}
        zplace, zearn, zexp = (_standardize(vals) for vals in (place, earn, exp))
        raw = {}
        for sid in sorted(features):
            adjustment = weights.top3*zplace[sid] + weights.earnings_per_start*zearn[sid] + weights.experience*zexp[sid]
            raw[sid] = p0[sid]*math.exp(adjustment)
            scored[sid] = {
                **features[sid], "career_top3_rate_smoothed":place[sid],
                "earnings_per_start_log":earn[sid],
                "z_top3":zplace[sid], "z_earnings_per_start":zearn[sid],
                "z_experience":zexp[sid], "log_adjustment":adjustment,
            }
        norm = math.fsum(raw.values())
        probs = {sid:raw[sid]/norm for sid in sorted(raw)}
    roster_by = {str(r["selection_id"]):r for r in roster}
    runners = []
    for sid in sorted(set(roster_by)|set(features),key=lambda s:(not s.isdigit(),int(s) if s.isdigit() else s)):
        rr=roster_by.get(sid,{})
        runners.append({
            "selection_id":sid, "horse_name":rr.get("horse_name"),
            "scratched":bool(rr.get("scratched",False)),
            "p_champion":p0.get(sid) if not blocks else None,
            "p_candidate":probs.get(sid),
            "candidate_minus_champion":(probs[sid]-p0[sid]) if sid in probs else None,
            "scored_source_features":scored.get(sid),
            "context_not_scored": {
                "age":next((f.get("age") for f in cohort if str(f["selection_id"])==sid),None),
                "post_position":rr.get("post_position"),
                "driver_name":rr.get("driver_or_jockey"),
                "trainer_name":rr.get("trainer"),
                "race_distance_m":race.get("distance_m"),
                "race_start_method":race.get("start_method"),
            },
        })
    coverage = {
        "active_runners":len(active_ids), "verified_scored_active":len(features),
        "lifetime_place_counts":sum(all(_integer(r.get(k)) is not None for k in ("history_total_seconds","history_total_thirds")) for r in cohort if not r.get("scratched")),
        "earnings_per_start":sum(_earnings(r.get("history_total_earnings")) is not None and _integer(r.get("history_total_starts")) is not None for r in cohort if not r.get("scratched")),
        "age_context":sum(r.get("age") is not None for r in cohort if not r.get("scratched")),
        "post_position_context":sum(rr.get("post_position") is not None for rr in roster if not rr["scratched"]),
        "driver_name_context":sum(bool(rr.get("driver_or_jockey")) for rr in roster if not rr["scratched"]),
        "race_distance_context":int(race.get("distance_m") is not None),
        "race_start_method_context":int(bool(race.get("start_method"))),
    }
    return {
        "schema_version": "CORE_004_MULTIFACTOR_RESEARCH_V1",
        "model_id":MODEL_ID,
        "status":"CANDIDATE_READY_UNCALIBRATED" if probs else "BLOCKED",
        "authority":"RESEARCH_ONLY_NO_EV_NO_WATCH_NO_BET",
        "race_id":race_id,"track":race.get("track"),"race_no":race.get("race_no"),
        "race_start_utc":start.isoformat(), "decision_as_of_utc":cutoff.isoformat(),
        "earliest_archived_source_start_utc": (
            source_start.isoformat() if source_start else None
        ),
        "source_start_clock_conflict_seconds": (
            abs((start-source_start).total_seconds()) if source_start else None
        ),
        "source_cohort_observed_utc":observed_at,
        "weights_unfitted_illustrative":asdict(weights),
        "scored_factors":SCORED_FACTORS,"unavailable_or_unscored_factors":NOT_SCORED,
        "blocked_reasons":blocks,"coverage":coverage,"p_champion_sum":sum(p0.values()) if not blocks else None,
        "p_candidate_sum":sum(probs.values()) if probs else None,
        "runners":runners,"bet_count":0,"watch_count":0,"ev_calculated":False,
        "roster_point_in_time_attested":False,
        "caveats":[
            "Weights are illustrative, not fitted or calibrated; cannot claim higher accuracy than Champion.",
            "Top-3, earnings, starts and wins are correlated and can double-count ability.",
            "Raw source earnings stay in native units and are compared only within this race.",
            "Historical collection timestamps do not independently attest provider publication time.",
            "Mutable race roster/scratch/start metadata lack independent historical PIT proof.",
            "No recent form, distance-specific form, driver performance, pace or class score is available.",
            "No market odds, EV, minimum prices, WATCH or BET enter this research calculation.",
        ],
    }


def analyze_card(conn: sqlite3.Connection, *, date: str, track: str | None = None, cutoff_minutes: float = 4.) -> dict[str, Any]:
    if not math.isfinite(cutoff_minutes) or cutoff_minutes <= 0:
        raise ValueError("cutoff_minutes must be > 0")
    if datetime.strptime(date, "%Y-%m-%d").strftime("%Y-%m-%d") != date:
        raise ValueError("Expected YYYY-MM-DD")
    q="SELECT race_id,start_time_utc FROM races WHERE race_date=? AND lower(discipline)='trot'"
    params: list[Any] = [date]
    if track:
        q += " AND track=?"
        params.append(track)
    q+=" ORDER BY start_time_utc,race_id"
    races=_rows(conn,q,tuple(params))
    reports = [analyze_multifactor(conn,race_id=r["race_id"],as_of=(_utc(r["start_time_utc"])-timedelta(minutes=cutoff_minutes)).isoformat()) for r in races]
    return {
        "schema_version":"CORE_004_CARD_V1", "authority":"RESEARCH_ONLY_NO_BETS",
        "date":date,"track":track,"cutoff_minutes":cutoff_minutes,
        "races_known":len(reports),
        "candidate_ready":sum(r["status"]=="CANDIDATE_READY_UNCALIBRATED" for r in reports),
        "candidate_blocked":sum(r["status"]=="BLOCKED" for r in reports),
        "races":reports,
    }


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(description="CORE-004 read-only market-free multifactor candidate")
    p.add_argument("--db",required=True)
    p.add_argument("--out",required=True)
    modes=p.add_mutually_exclusive_group(required=True)
    modes.add_argument("--race-id")
    modes.add_argument("--date")
    p.add_argument("--track")
    p.add_argument("--as-of",help="Required for --race-id: aware ISO timestamp")
    p.add_argument("--cutoff-minutes",type=float,default=4.)
    a=p.parse_args(argv)
    if a.race_id and not a.as_of:
        p.error("--as-of required with --race-id")
    path=Path(a.db).resolve()
    if not path.is_file():
        p.error("database not found")
    con=sqlite3.connect(f"file:{path.as_posix()}?mode=ro",uri=True)
    con.row_factory=sqlite3.Row
    try:
        result=(analyze_multifactor(con,race_id=a.race_id,as_of=a.as_of) if a.race_id else analyze_card(con,date=a.date,track=a.track,cutoff_minutes=a.cutoff_minutes))
    finally:
        con.close()
    outfile=Path(a.out)
    outfile.parent.mkdir(parents=True,exist_ok=True)
    outfile.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
    print(json.dumps({"path":str(outfile),"candidate_ready":result.get("candidate_ready",int(result.get("status")=="CANDIDATE_READY_UNCALIBRATED")),"bet_count":0},ensure_ascii=False))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
