"""Evidence-driven October tracker. Reads frozen records; has no execution authority."""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from statistics import mean

from .evaluation import calibration_bins, log_loss, multiclass_brier
from .operations_report import OSLO, _time, build_operations_report
from .provider_capability import full_field_gate
from .storage import SQLiteStore

ROOT = Path(__file__).parents[2]
CHAMPION = "FUNDAMENTAL_CHAMPION_V1_1"
SHADOW = "SHADOW_RESEARCH_V1_EQUAL_LOG_POOL"
START, END = date(2026, 10, 1), date(2026, 10, 31)
LAYERS = ("fundamental", "market", "combined")


class ReadOnlyStore(SQLiteStore):
    @contextmanager
    def connect(self):
        connection = sqlite3.connect(Path(self.path).resolve().as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
        finally:
            connection.close()


def _distribution(raw):
    try:
        data = json.loads(raw)
        if not isinstance(data, dict) or not data:
            return None
        data = {str(k): float(v) for k, v in data.items()}
        if not all(math.isfinite(p) and 0 < p <= 1 for p in data.values()):
            return None
        return data if math.isclose(sum(data.values()), 1, abs_tol=1e-6) else None
    except (ValueError, TypeError, AttributeError):
        return None


def _qualify(store, run):
    if run["fundamental_model_version"] != CHAMPION or run["shadow_model_version"] != SHADOW:
        return "OTHER_MODEL_COHORT", None
    if run["decision_status"] not in {"PASS", "WATCH", "SHADOW_BET"}:
        return "NOT_EXECUTABLE", None
    decision, start, market_time = map(_time, (
        run["created_at_utc"], run["race_start_time_utc"], run["source_market_observed_at_utc"]))
    if not decision or not start or not market_time or not market_time <= decision < start:
        return "INVALID_PRE_RACE_TIMESTAMPS", None
    rows = store.latest_runner_fundamentals(run["race_id"], before=decision)
    reason = full_field_gate(store, run["race_id"], rows, decision)
    if reason:
        return reason, None
    active = {r["selection_id"] for r in rows if not r["scratched"]}
    distributions = {layer: _distribution(run[f"{layer}_probabilities_json"]) for layer in LAYERS}
    if not active or any(p is None or set(p) != active for p in distributions.values()):
        return "INCOMPLETE_FROZEN_PROBABILITIES", None
    model = store.latest_fundamental_model_run(run["race_id"], before=decision)
    if not model or not model["shadow_eligible"] or model["model_version"] != CHAMPION:
        return "NO_ELIGIBLE_CHAMPION_COHORT", None
    p = _distribution(model["probabilities_json"])
    if (not p or set(p) != active or any(
            r["feature_as_of_utc"] != model["feature_as_of_utc"]
            for r in rows if not r["scratched"])
            or any(not math.isclose(p[k], distributions["fundamental"][k], abs_tol=1e-9)
                   for k in active)):
        return "MODEL_COHORT_MISMATCH", None
    return None, distributions


def _paired_summary(rows):
    output = {"n": len(rows), "layers": {}}
    for layer in LAYERS:
        output["layers"][layer] = {
            "log_loss": mean(log_loss(r["probabilities"][layer], r["winner"]) for r in rows)
            if rows else None,
            "brier": mean(multiclass_brier(r["probabilities"][layer], r["winner"]) for r in rows)
            if rows else None,
            "calibration": calibration_bins(
                ((p, key == r["winner"]) for r in rows
                 for key, p in r["probabilities"][layer].items()), width=.1),
        }
    for layer in ("fundamental", "combined"):
        output[f"{layer}_minus_market_log_loss"] = (
            output["layers"][layer]["log_loss"] - output["layers"]["market"]["log_loss"]
            if rows else None)
    return output


def _history(store, now):
    required = {"horse_id", "historical_race_id", "race_start_utc", "distance_m", "race_class",
                "track", "finish_position", "source_uri", "observed_at_utc", "available_at_utc",
                "market_free"}
    with store.connect() as c:
        schema = {r["name"] for r in c.execute("PRAGMA table_info(horse_start_history)")}
        if not schema:
            return {"status": "NOT_IMPLEMENTED", "starts": None, "horses": None,
                    "reason": "Detaljert historikk per tidligere start mangler lagringskontrakt."}
        if not required <= schema:
            return {"status": "INVALID_SCHEMA", "starts": None, "horses": None,
                    "reason": "Historikken mangler identitet, løpsfelt eller tids-/kildebevis."}
        rows = [dict(r) for r in c.execute("SELECT * FROM horse_start_history")]
    valid = {}
    for r in rows:
        observed, available, start = map(_time, (
            r["observed_at_utc"], r["available_at_utc"], r["race_start_utc"]))
        if (observed and available and start and start < available <= observed <= now
                and r["market_free"] == 1 and all(r[k] is not None and r[k] != ""
                                                for k in required - {"market_free"})
                and not str(r["horse_id"]).startswith("TMP-")):
            valid[(r["horse_id"], r["historical_race_id"])] = r
    return {"status": "COLLECTING" if valid else "NO_VALID_HISTORY", "starts": len(valid),
            "horses": len({key[0] for key in valid}), "rejected_rows": len(rows) - len(valid),
            "reason": "Historikkopptelling er ikke dokumentasjon på at modellen bruker variablene."}


def _economics(tickets, qualified, provenance, now):
    values, excluded, clvs = [], Counter(), []
    for t in tickets:
        if t["race_id"] not in qualified or t["status"] == "NOT_EXECUTABLE":
            continue
        try:
            run, distributions = qualified[t["race_id"]]
            prov = provenance[run["decision_run_id"]]
            policy = json.loads(prov["decision_policy_json"])
            quotes = json.loads(prov["market_odds_json"])
            selections = json.loads(t["selections_json"])
            if (t["product"] != "V" or len(selections) != 1 or t["model_version"] != SHADOW
                    or t["decision"] != "BET"):
                raise ValueError("UNSUPPORTED_TICKET")
            selection = str(selections[0])
            probability = distributions["combined"][selection]
            decision, snapshot, start, settled = map(_time, (
                t["decision_time_utc"], t["source_snapshot_time_utc"],
                run["race_start_time_utc"], t["settled_at_utc"]))
            price = float(t["available_price"])
            thresholds = [float(policy[k]) for k in ("minimum_edge", "safety_margin")]
            if not all(math.isfinite(v) and v >= 0 for v in thresholds):
                raise ValueError("INVALID_PRICE_POLICY")
            if (not decision or not snapshot or not start
                    or decision != _time(run["created_at_utc"])
                    or snapshot != _time(run["source_market_observed_at_utc"])
                    or not 0 <= (decision - snapshot).total_seconds() <= 120
                    or not 0 < (start - decision).total_seconds() <= 300
                    or not math.isfinite(price) or price <= 1
                    or not math.isclose(price, float(quotes[selection]), abs_tol=1e-9)
                    or price < (1 + max(thresholds)) / probability):
                raise ValueError("UNVERIFIED_EXECUTABLE_PRICE")
            if t["status"] != "SETTLED" or not settled or not start <= settled <= now:
                raise ValueError("UNSETTLED")
            stake, gross, pnl = map(float, (t["stake_nok"], t["gross_return_nok"], t["net_pnl_nok"]))
            if (not all(math.isfinite(v) for v in (stake, gross, pnl)) or stake <= 0 or gross < 0
                    or not math.isclose(pnl, gross - stake, abs_tol=1e-9)):
                raise ValueError("INVALID_PNL")
            values.append((stake, pnl))
            close, clv = t["closing_price"], t["clv"]
            if close is not None and clv is not None:
                close, clv = float(close), float(clv)
                if (math.isfinite(close) and close > 1 and math.isfinite(clv)
                        and math.isclose(clv, math.log(price / close), abs_tol=1e-9)):
                    clvs.append(clv)
        except (ValueError, TypeError, KeyError) as exc:
            excluded[str(exc)] += 1
    stake = sum(v[0] for v in values)
    pnl = sum(v[1] for v in values)
    return {"settled_verified_price_n": len(values), "stake_nok": stake if values else None,
            "paper_pnl_nok": pnl if values else None, "roi": pnl / stake if stake else None,
            "clv_n": len(clvs), "mean_clv": mean(clvs) if clvs else None,
            "missing_clv_n": len(values) - len(clvs), "excluded": dict(excluded)}


def build_tracker(db_path, *, now=None):
    now = now or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Tracker requires an aware observation time")
    local_day = now.astimezone(OSLO).date()
    store = ReadOnlyStore(db_path)
    operations = build_operations_report(db_path, START, END, now=now)
    race_info = {r["race_id"]: r for r in operations["races"]}
    provenance = {r["decision_run_id"]: r for r in store.fetch_table("decision_provenance")}
    outcomes = {r["race_id"]: r for r in store.fetch_table("outcomes")
                if _time(r["settled_at_utc"]) and _time(r["settled_at_utc"]) <= now}
    runs = sorted(store.fetch_table("shadow_decision_runs"), key=lambda r: r["created_at_utc"])
    qualified, excluded, paired = {}, Counter(), []
    seen = set()
    for run in runs:
        rid = run["race_id"]
        if rid not in race_info or not rid.startswith("RIKSTOTO:"):
            continue
        if not _time(run["created_at_utc"]) or _time(run["created_at_utc"]) > now:
            continue
        if run["shadow_model_version"] != SHADOW or rid in seen:
            continue
        seen.add(rid)
        reason, distributions = _qualify(store, run)
        prov = provenance.get(run["decision_run_id"], {})
        if not reason and not all(prov.get(k) for k in (
                "code_sha", "governance_hash", "market_odds_json", "decision_policy_json",
                "combination_policy_json")):
            reason = "MISSING_FROZEN_PROVENANCE"
        if not reason:
            try:
                for key in ("market_odds_json", "decision_policy_json", "combination_policy_json"):
                    value = json.loads(prov[key])
                    if not isinstance(value, dict) or not value:
                        raise ValueError("empty or invalid provenance")
            except (ValueError, TypeError):
                reason = "INVALID_FROZEN_PROVENANCE"
        if reason:
            excluded[reason] += 1
            continue
        qualified[rid] = (run, distributions)
        outcome = outcomes.get(rid)
        if (outcome and _time(outcome["settled_at_utc"]) >= _time(run["race_start_time_utc"])
                and str(outcome["winner_selection_id"]) in distributions["fundamental"]):
            paired.append({"race_id": rid, "country": race_info[rid]["country"],
                           "day": race_info[rid]["day"], "winner": str(outcome["winner_selection_id"]),
                           "probabilities": distributions})
    history = _history(store, now)
    paths = defaultdict(set)
    market_rows = store.fetch_table("provider_market_snapshots")
    for r in market_rows:
        info = race_info.get(r["race_id"])
        stamp = _time(r["observed_at_utc"])
        price = r["odds_decimal"]
        if (info and r["product"] == "V" and stamp and stamp <= now
                and price is not None and math.isfinite(float(price)) and float(price) > 1
                and stamp < _time(info["start_time_utc"])):
            paths[(r["race_id"], r["selection_key"])].add(stamp)
    market_paths = {"runner_paths": len(paths), "runner_paths_with_2_plus_times": sum(
        len(times) >= 2 for times in paths.values()), "pre_race_snapshots": sum(map(len, paths.values()))}
    audits = {}
    for r in sorted(store.fetch_table("integrity_audits"), key=lambda r: r["generated_at_utc"]):
        if _time(r["generated_at_utc"]) and _time(r["generated_at_utc"]) <= now:
            audits[r["audit_type"]] = {"status": r["status"], "at": r["generated_at_utc"]}
    challengers = []
    events = store.fetch_table("challenger_forward_events")
    for r in store.fetch_table("challenger_registry"):
        registered = _time(r["registered_at_utc"])
        forward, cutoff = _time(r["forward_start_utc"]), _time(r["discovery_cutoff_utc"])
        if not registered or not forward or not cutoff or registered > now:
            continue
        eligible = {e["race_id"] for e in events if e["challenger_id"] == r["challenger_id"]
                    and e["eligible"] and _time(e["race_start_utc"])
                    and max(forward, cutoff, registered) < _time(e["race_start_utc"]) <= now
                    and _time(e["evaluation_created_at_utc"])
                    and _time(e["race_start_utc"]) <= _time(e["evaluation_created_at_utc"]) <= now}
        challengers.append({"id": r["challenger_id"], "model": r["model_version"],
                           "registered_at": r["registered_at_utc"], "forward_n": len(eligible),
                           "minimum_n": r["minimum_forward_races"], "status": r["status"]})
    governance = json.loads((ROOT / "docs/research_governance.json").read_text())
    guard = (governance["shadow_champion"] == CHAMPION
             and all(governance[k] is False for k in (
                 "execution_authority", "real_money_execution", "auto_promotion_enabled",
                 "adaptive_switching_enabled")))
    summaries = {country: _paired_summary([r for r in paired if r["country"] == country])
                 for country in ("SE", "DK", "NO", "FR")}
    tickets = store.fetch_table("shadow_tickets")
    economics = _economics(tickets, qualified, provenance, now)
    economics_by_country = {country: _economics(
        tickets, {rid: value for rid, value in qualified.items()
                  if race_info[rid]["country"] == country}, provenance, now)
        for country in ("SE", "DK", "NO", "FR")}
    n = len(paired)
    audit_ready = all(k in audits and audits[k]["status"] == "PASS"
                      and (now - _time(audits[k]["at"])).total_seconds() <= 86400 for k in (
        "TEMPORAL_INTEGRITY", "SETTLEMENT_INTEGRITY", "RUNTIME_REPLAY_PARITY"))
    # Row counts cannot certify detailed-history coverage of the active cohort.
    # An explicit research review is still required before registration.
    candidate_ready = guard and audit_ready and n >= 100 and bool(history["starts"])
    milestones = [
        {"id": "operations", "period": "1.–7. oktober", "title": "Kontrollere daglig drift",
         "status": "REVIEW_REQUIRED" if local_day > date(2026, 10, 7) else "IN_PROGRESS",
         "next": "Kontroller dekningshull, identiteter, T−4 og oppgjør for hver dag.",
         "blockers": ["Uken er ikke ferdig kontrollert."] if local_day <= date(2026, 10, 7)
         else ["Sluttkontroll av syv dager og siste oppgjørsfrist kreves; dato alene godkjenner ikke drift."]},
        {"id": "history", "period": "8.–14. oktober", "title": "Bygge hestehistorikk og markedsforløp",
         "status": "IN_PROGRESS" if history["starts"] else "NOT_STARTED",
         "next": "Lagre tidligere starter med stabil hesteidentitet, kilde og tilgjengelighetstid.",
         "blockers": [] if history["starts"] else [history["reason"]]},
        {"id": "analysis", "period": "15.–21. oktober", "title": "Sammenligne på de samme løpene",
         "status": "READY_FOR_REVIEW" if n >= 100 else "COLLECTING" if n else "NO_EVIDENCE",
         "next": "Vurder log loss, Brier og kalibrering før økonomiske resultater.",
         "blockers": [] if n >= 100 else [f"{n} sammenlignbare løp; 100 er første diagnosepunkt."]},
        {"id": "challenger", "period": "22.–31. oktober", "title": "Én separat Challenger-test",
         "status": "FORWARD_TESTING" if challengers else "READY_FOR_HUMAN_REVIEW"
         if candidate_ready else "BLOCKED",
         "next": "Vurder få historikkvariabler og registrer en egen fremovertest etter eksplisitt beslutning.",
         "blockers": ["Dekning av historikkvariablene og forskningshypotesen må vurderes manuelt."]
         if candidate_ready and not challengers else [] if challengers else [
             "Krever historikk, minst 100 sammenlignbare løp og beståtte integritetskontroller."]},
    ]
    return {"schema_version": "HBI_OCTOBER_TRACKER_V1", "generated_at": now.isoformat(),
            "champion": CHAMPION, "guardrails_ok": guard, "automatic_registration": False,
            "automatic_promotion": False, "real_money_execution": False,
            "qualified_races_n": len(qualified), "paired_races_n": n,
            "sample_band": "SERIOUS_REVIEW_STARTING_POINT" if n >= 500 else
            "EARLY_DIAGNOSTICS" if n >= 100 else "OPERATIONS_CHECK",
            "sample_targets": [{"n": target, "current": n, "remaining": max(0, target - n)}
                               for target in (50, 100, 300, 500)],
            "excluded_decisions": dict(excluded), "qualified_race_ids": sorted(qualified),
            "paired_race_ids": sorted(r["race_id"] for r in paired),
            "milestones": milestones, "operations": operations, "history": history,
            "market_paths": market_paths, "paired_evaluation": _paired_summary(paired),
            "evaluation_by_country": summaries, "economics": economics,
            "economics_by_country": economics_by_country,
            "integrity": audits, "challengers": challengers,
            "daily_samples": [{"day": date(2026, 10, day).isoformat(),
                               "qualified": sum(race_info[rid]["day"] == date(2026, 10, day).isoformat()
                                                for rid in qualified),
                               "paired": sum(r["day"] == date(2026, 10, day).isoformat() for r in paired)}
                              for day in range(1, 32)],
            "interpretation": "50–100 løp: driftssjekk. 100–300: tidlige diagnoser. 500+ er et "
            "utgangspunkt for seriøs vurdering, ingen garanti. Negativ feilforskjell mot markedet "
            "betyr lavere feil på samme kohort, ikke bevist edge. Ingen milepæl godkjennes av dato alene."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--output-dir", default="research-v1")
    args = parser.parse_args()
    report = build_tracker(args.db)
    from .tracker_view import render_tracker
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "october-tracker.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    (output / "october-tracker.html").write_text(render_tracker(report), encoding="utf-8")
    console = dict(report)
    console["operations"] = {k: v for k, v in report["operations"].items() if k != "races"}
    print(json.dumps(console, indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
