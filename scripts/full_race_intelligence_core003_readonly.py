"""Offline every-future-physical-race watcher sidecar; no providers/model/stakes.

Runs beside existing CORE-003 on its own isolated SQLite without new schedule or
any source fetch. Lists every future physical race, even when unavailable for
fundamental/market evaluation. Uses ONLY SHA-verified pre-existing model reports.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path

from hbi.full_race_intelligence import analyze_race


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def aware(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    if dt.utcoffset() is None:
        raise ValueError("UNVERIFIED_RACE_OR_MODEL_SOURCE_CLOCK")
    return dt.astimezone(UTC)


def frozen_models(root: Path) -> dict:
    path = root / "cohort-index.json"
    if not path.is_file():
        return {}
    index = json.loads(path.read_bytes())
    if (index.get("schema") != "BET_MVP_002_FIXED_COHORT_INDEX_V1"
            or index.get("bet_authority") is not False):
        raise ValueError("UNTRUSTED_MODEL_COHORT_INDEX")
    models = {}
    for entry in index.get("processed", []):
        relative = entry.get("directory")
        rid = entry.get("race_id")
        if (not isinstance(relative, str)
                or not relative.startswith("bet-mvp-shadow/race-")
                or not isinstance(rid, str)):
            raise ValueError("MODEL_COHORT_PATH_INVALID")
        suffix = relative.removeprefix("bet-mvp-shadow/")
        if not suffix.startswith("race-") or not suffix[5:].isdigit():
            raise ValueError("MODEL_COHORT_PATH_INVALID")
        file = root / suffix / "shadow.json"
        if file.is_symlink():
            raise ValueError("MODEL_SOURCE_SYMLINK")
        raw = file.read_bytes()
        if sha(raw) != entry.get("report_sha256"):
            raise ValueError("MODEL_SOURCE_SHA_MISMATCH")
        model = json.loads(raw)
        if (model.get("schema") != "BET_MVP_001_FROZEN_SHADOW_V1"
                or model.get("bet_authority") is not False
                or (model.get("race") or {}).get("race_id") != rid
                or model.get("run_kind") != "PROSPECTIVE_ATTEMPT"):
            raise ValueError("MODEL_SOURCE_NOT_ORIGINAL_PROSPECTIVE")
        if rid in models:
            raise ValueError("DUPLICATE_MODEL_PHYSICAL_RACE")
        models[rid] = (model, sha(raw))
    return models


def analyze(db: Path, root: Path, *, cutoff: datetime, hours: int = 48) -> dict:
    models = frozen_models(root)
    conn = sqlite3.connect("file:" + str(db.resolve()) + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        race_rows = [dict(x) for x in conn.execute(
            "SELECT race_id,track,race_no,start_time_utc,discipline "
            "FROM races ORDER BY start_time_utc,race_id"
        )]
        report = []
        for race in race_rows:
            start = aware(race["start_time_utc"])
            if not cutoff < start <= cutoff + timedelta(hours=hours):
                continue
            rid = race["race_id"]
            if not rid.startswith("RIKSTOTO:"):
                continue
            runners = [dict(x) for x in conn.execute(
                "SELECT selection_id,horse_name,scratched FROM runners "
                "WHERE race_id=? ORDER BY selection_id", (rid,)
            )]
            if len(runners) < 2:
                report.append({
                    "physical_race_id":rid,"status":"NO_COMPLETE_CANONICAL_ROSTER",
                    "bet_authority":False,
                })
                continue
            bundle = models.get(rid)
            frozen, sha_model = bundle if bundle is not None else (None, None)
            lookup = {}
            if frozen is not None:
                entries = frozen.get("runners")
                if (frozen.get("model_status") == "MODEL_READY"
                        and frozen.get("source_archive_is_immutable_read_only") is True
                        and isinstance(entries, list)
                        and len(entries) == len(runners)):
                    lookup = {x["selection_id"]: x for x in entries}
                    if (set(lookup) != {r["selection_id"] for r in runners}
                            or any(
                                lookup[r["selection_id"]]["horse_name"] != r["horse_name"]
                                or bool(lookup[r["selection_id"]]["scratched"])
                                != bool(r["scratched"])
                                for r in runners
                            )):
                        lookup = {}
            samples = []
            for row in runners:
                record = lookup.get(row["selection_id"])
                samples.append({
                    "selection_id":row["selection_id"],
                    "horse_name":row["horse_name"],
                    "scratched":bool(row["scratched"]),
                    "p_win_frozen":record.get("champion_p_win") if record else None,
                    "lifetime_starts":record.get("historical_starts") if record else None,
                    "lifetime_wins":record.get("historical_wins") if record else None,
                    "win_odds_raw":record.get("win_odds") if record else None,
                    "win_observed_at_utc":(
                        record.get("win_odds_observed_at_utc") if record else None),
                    "win_price_source_sha256":None,
                    "identity_attested":False,
                    "collective_share":None,
                    "history_source_sha256":None,
                    "data_quality":"ORIGINAL_MODEL_SHA_ONLY_NO_INDEPENDENT_IDENTITY",
                    "blockers":["NO_PIT_ORIGINAL_CERTIFICATE"],
                })
            result = analyze_race({
                "physical_race_id":rid,
                "round_name":"ALL_PHYSICAL_RACES_NO_POOL_FILTER",
                "leg":None, "start_utc":race["start_time_utc"],
                "runners":samples,"pit_certified":False,
                "full_field_win_verified":False,
                "model_version":(
                    (frozen.get("model_versions") or {}).get("champion")
                    if frozen else None),
                "model_run_id":sha_model,
                "model_frozen_at_utc":frozen.get("report_created_at_utc") if frozen else None,
                "source_model_sha256":sha_model,
                "source_original_sha256":None,
            },decision_time_utc=cutoff.isoformat())
            result["track"] = race["track"]
            result["race_no"] = race["race_no"]
            result["source_admission"] = (
                "SHA_VERIFIED_RESEARCH_MODEL_NO_PIT" if lookup else
                "NO_FROZEN_OR_FULL_FIELD_PROSPECTIVE_MODEL")
            report.append(result)
        return {
            "schema":"FULL_RACE_INTELLIGENCE_CORE003_SIDECAR_V1",
            "cutoff_utc":cutoff.isoformat(),"future_horizon_hours":hours,
            "all_physical_races_discovered":len(report),
            "fully_modelled_frozen_research_fields":sum(
                x.get("full_field_model_valid") is True for x in report),
            "source_database_read_only":True,
            "no_provider_calls":True, "bet_authority":False,
            "v85_system_ev":"NOT_ESTABLISHED",
            "races":report,
        }
    finally:
        conn.close()


def main() -> None:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",type=Path,required=True)
    p.add_argument("--models",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    args=p.parse_args()
    result=analyze(args.db,args.models,cutoff=datetime.now(UTC))
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    print(json.dumps({
        "races":result["all_physical_races_discovered"],
        "models":result["fully_modelled_frozen_research_fields"],
        "bet_authority":False,
    }))


if __name__=="__main__":
    main()
