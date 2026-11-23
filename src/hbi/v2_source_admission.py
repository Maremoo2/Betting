"""V2-only canonical adapter using the existing reviewed-original receipt gate.

No receipt is approved here. Empty repository review pins mean no real admission.
Coverage is an independent reviewed completeness attestation, not a caller flag;
the bound raw graph must also reproduce the supplied state with original V2 math.
"""
from __future__ import annotations

import hashlib
from datetime import timedelta
from pathlib import Path

from .admission_originals import verified_original
from .cloud_run003_model import IndependentScratchEvidence
from .horse_identity import AttestedHorseIdentity, identity_fields
from .shadow import ShadowPolicy
from .t4_evidence import _aware


def _reviewed(item, role, moment, cutoff):
    if not isinstance(item, dict):
        return None
    observed = _aware(item.get("observed_at_utc"))
    if observed is None or not observed <= moment or observed >= cutoff:
        return None
    try:
        raw = Path(item["original_file"]).read_bytes()
        return verified_original(role, item["uri"], item["sha256"], observed, raw, cutoff)
    except (KeyError, OSError, TypeError, ValueError):
        return None


def assess_sources(packet, state_raw, state_sha256, evidence, *, artifact_sha256, moment):
    """Return all blockers; never infer approval from state.PIT_CERTIFIED."""
    from .benchmark002_shadow import checked_json, feature_matrix
    from .daily_v2 import collector_packet
    from .v2_feature_state import advance
    from .v2_source_recovery import load_bundle

    report = {"qualified": False, "blockers": [], "PIT_CERTIFIED": False,
              "BET_AUTHORITY": False, "reviewed_receipts": []}
    blocks = report["blockers"]
    start = _aware(packet.get("start_at"))
    if moment.utcoffset() is None or start is None:
        blocks.append("V2_CANONICAL_CLOCK_INVALID")
        return report
    cutoff = start-timedelta(minutes=ShadowPolicy().target_minutes_to_start)
    report["cutoff_utc"] = cutoff.isoformat()
    if moment >= cutoff:
        blocks.append("V2_ADMISSION_AT_OR_AFTER_T4")
    evidence = evidence if isinstance(evidence, dict) else {}
    docs = {}
    roles = {"coverage": "V2_STATE_COVERAGE", "registry": "REGISTRY_BINDING",
             "scratchings": "INDEPENDENT_SCRATCH"}
    for key, role in roles.items():
        doc = _reviewed(evidence.get(key), role, moment, cutoff)
        if doc is None:
            blocks.append("REVIEWED_"+role+"_ORIGINAL_MISSING_OR_INVALID")
        else:
            docs[key] = doc
            report["reviewed_receipts"].append({"role": role, "uri": evidence[key]["uri"],
                "sha256": evidence[key]["sha256"], "observed_at_utc": evidence[key]["observed_at_utc"]})
    if blocks:
        return report
    try:
        state = checked_json(state_raw, state_sha256)
        if state.get("known_gaps"):
            raise ValueError("V2_GRAPH_HAS_KNOWN_GAPS")
        active, _ = feature_matrix(packet)
        active_keys = {r["selection_id"] for r in active}
        collector = collector_packet(evidence["collector_root"], packet["race_id"], now=moment)
        original_runners = [{"selection_id": str(r["startNumber"]), "registration": r["horseRegistrationNumber"],
            "horse_id": "RIKSTOTO_REG:"+r["horseRegistrationNumber"], "horse_name": r["horseName"],
            "scratched": r["isScratched"]} for r in collector["roster"]]
        if (packet["runners"] != original_runners or packet["start_at"] != collector["start_at"]
                or packet.get("collector_source_hashes") != collector["source_hashes"]):
            raise ValueError("V2_COLLECTOR_PACKET_BINDING_CONFLICT")
        if not isinstance(packet.get("collector_source_hashes"), dict):
            raise TypeError("V2_COLLECTOR_BINDING_MISSING")
        bundle = Path(evidence["graph_bundle"])
        bundle_sha = hashlib.sha256(bundle.read_bytes()).hexdigest()
        expected_coverage = {"schema": "VERIFIED_V2_COMPLETE_STATE_V1", "race_id": packet["race_id"],
            "start_at": packet["start_at"], "state_sha256": state_sha256,
            "model_artifact_sha256": artifact_sha256, "source_policy": "RIKSTOTO_ONLY",
            "collector_source_hashes": packet["collector_source_hashes"],
            "graph_bundle_sha256": bundle_sha, "complete_careers_and_opponent_graph": True,
            "exact_versions_available_before_cutoff": True}
        if docs["coverage"] != expected_coverage:
            raise ValueError("V2_REVIEWED_STATE_BINDING_CONFLICT")
        registry = docs["registry"]
        if (registry.get("schema") != "VERIFIED_V2_REGISTRY_FIELD_V1"
                or registry.get("race_id") != packet["race_id"]
                or registry.get("startlist_sha256") != packet["startlist_sha256"]):
            raise ValueError("V2_REVIEWED_REGISTRY_FIELD_CONFLICT")
        bindings = registry["runners"]
        if len(bindings) != len(active) or {b["selection_id"] for b in bindings} != active_keys:
            raise ValueError("V2_REGISTRY_ACTIVE_FIELD_INCOMPLETE")
        identities = []
        for runner in active:
            item, = [b for b in bindings if b["selection_id"] == runner["selection_id"]]
            if item["native_registration"] != runner["registration"]:
                raise ValueError("V2_REGISTRY_NATIVE_ID_CONFLICT")
            resolved = identity_fields(packet["race_id"], runner["selection_id"], (
                AttestedHorseIdentity(packet["race_id"], runner["selection_id"], item["horse_id"],
                                      item["source"], item["source_version"]),))
            identities.append(resolved["horse_id"])
            h = runner["horse_id"]
            if packet["state"][h] != {"history": state["histories"][h], "rating": state["ratings"][h]}:
                raise ValueError("V2_PACKET_STATE_VALUES_CONFLICT")
        if len(set(identities)) != len(identities):
            raise ValueError("V2_DUPLICATE_PERMANENT_IDENTITY")
        roster = tuple((r["selection_id"], r["scratched"]) for r in packet["runners"])
        item = evidence["scratchings"]
        scratch = IndependentScratchEvidence(packet["race_id"], roster, _aware(item["observed_at_utc"]),
            item["sha256"], item["uri"], Path(item["original_file"]).read_bytes())
        if not scratch.is_usable(packet["race_id"], moment):
            raise ValueError("V2_INDEPENDENT_SCRATCH_FIELD_CONFLICT")
        # Capture availability is checked independently from event dates. The
        # reviewed coverage binds the complete raw graph; the replay proves the
        # numerical state, including all prior opponents, without training.
        fields, audits = load_bundle(bundle)
        if not fields or any(a["status"] != "RETROSPECTIVE_RECONSTRUCTED" for a in audits):
            raise ValueError("V2_GRAPH_ORIGINALS_INVALID_OR_INCOMPLETE")
        if len({f["race_id"] for f in fields}) != len(fields):
            raise ValueError("V2_GRAPH_DUPLICATE_RACE")
        if any(f["day"] >= packet["day"] for f in fields):
            raise ValueError("V2_GRAPH_CONTAINS_TARGET_OR_FUTURE_RESULT")
        empty = {"last_day": "2014-12-31", "histories": {}, "ratings": {}, "event_refs": {},
                 "identities": {}, "applied_races": {}, "known_gaps": []}
        replayed, receipt = advance(bundle.parent, empty, fields, moment.isoformat())
        if receipt["pending_same_day"] or receipt["excluded"]:
            raise ValueError("V2_GRAPH_SOURCE_NOT_AVAILABLE_BEFORE_CUTOFF")
        if any(replayed[k] != state[k] for k in ("histories", "ratings", "event_refs", "applied_races", "last_day")):
            raise ValueError("V2_GRAPH_REPLAY_STATE_MISMATCH")
    except (ValueError, KeyError, TypeError, OSError, IndexError) as exc:
        blocks.append(str(exc))
        return report
    report.update(qualified=True, PIT_CERTIFIED=True, permanent_identities=identities,
                  replay_fields=len(fields), state_sha256=state_sha256)
    return report
