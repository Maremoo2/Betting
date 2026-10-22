"""Research candidate view within M5 records. No probability or model admission."""
from .date_overview import timestamp

REQUIRED_FEATURES = ("driver", "trainer", "distance_m", "start_method", "history")


def candidate(row):
    reasons = []
    inputs = []
    active = [h for h in row["roster"] if h.get("scratched") is False]
    if (not row["full_field_identity_verified"] or len(active) < 2
            or len({h["registration_observed"] for h in active}) != len(active)):
        reasons.append("FULL_FIELD_IDENTITY_UNVERIFIED")
    if row["country"] not in {"NO", "SE"} or row["discipline"] != "trot":
        reasons.append("OUTSIDE_NO_SE_TROT")
    cutoff = timestamp(row["event_time"]) if row.get("event_time") else None
    if not cutoff:
        reasons.append("RACE_TIME_MISSING")
    refs = {(r["url"], r["body_sha256"], r["fetched_at"]) for r in row["source_refs"]}
    for horse in active:
        features = {}
        for key in REQUIRED_FEATURES:
            fact = horse.get("features", {}).get(key)
            valid = bool(fact and fact.get("value") is not None and cutoff
                and (fact.get("source_url"), fact.get("source_body_sha256"), fact.get("source_observed_at")) in refs
                and timestamp(fact["source_observed_at"]) < cutoff
                and fact.get("status") == "PIT_VERIFIED")
            # History needs a separately validated historical feature contract;
            # arbitrary lists (including retrospective labels) never qualify.
            if key == "history":
                valid = False
            if not valid:
                reasons.append(f"{horse['selection_id']}:{key}:MISSING_OR_PIT_UNVERIFIED")
            features[key] = {"fact": fact, "pit_verified": valid}
        if set(horse.get("features", {})) - {*REQUIRED_FEATURES, "extra_distance_m"}:
            reasons.append(f"{horse['selection_id']}:UNAPPROVED_FEATURE")
        inputs.append({"selection_id": horse["selection_id"],
            "horse_identity": {"namespace": "RIKSTOTO_REGISTRATION", "value": horse["registration_observed"],
                "status": horse["identity_status"]}, "name": horse["name"], "features": features})
    labels = row["labels"]
    ids = {h["selection_id"]: h["registration_observed"] for h in active}
    if (not row["authoritative_result_verified"] or len(labels) != len(ids)
            or {l["selection_id"]: l["registration"] for l in labels} != ids
            or len({l["selection_id"] for l in labels}) != len(labels)
            or sum(l["placing"] == 1 for l in labels) != 1
            or any(l["semantics"] != "NUMERIC_PLACING" or l["placing"] is None for l in labels)):
        reasons.append("COMPLETE_UNAMBIGUOUS_RESULT_LABELS_REQUIRED")
    if row["status"] == "CONFLICT":
        reasons.append("SOURCE_CONFLICT")
    # Deliberate initial exclusion until a documented history feature definition exists.
    reasons.append("HISTORY_FEATURE_CONTRACT_NOT_VALIDATED")
    return {"schema": "HBI_RACE_MODEL_CANDIDATE_V1", "race_id": row["race_id"],
        "country": row["country"], "track": row["track"], "event_time": row["event_time"],
        "inputs": inputs, "label_role": "RETROSPECTIVE_LABEL_ONLY_SEPARATE_FROM_INPUTS",
        "data_ready": False, "exclusion_reasons": sorted(set(reasons)),
        "model_eligible": False}
