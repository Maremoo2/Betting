"""Bounded offline availability/correction research; never features or model admission."""
from __future__ import annotations

import argparse
import html
import io
import json
import re
import zipfile
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .date_overview import DailyArchive, timestamp
from .history_feasibility import (
    MISSING,
    SCENARIOS,
    archive_index,
    local_instant,
    target_document,
)
from .history_feasibility import (
    run as feasibility_run,
)
from .history_source_verification import PROGRAM_SHA, dnt_review
from .pdf_semantic_validation import checked_bytes, read_sources
from .pdf_validation import sha
from .provider_capability import name_key

SOURCE_SHA = "7dd9b3ec393887e4fbc206b8a79c00cdf3957b4e6fc3f8f69fd467a1624e32ed"
EVIDENCE_SHA = "e8cb7e8967b236d33a9840c61961646dbc6385a1a66a52caa5f03d7d39041582"
REVIEW = {"M7A1-003": "DNT_REGISTRATION:578001020205025", "M7A1-009": "DNT_REGISTRATION:578001020215363",
    "M7B1-H-001": "DNT_REGISTRATION:578001020160529", "M7B1-H-007": "DNT_REGISTRATION:578001020180623",
    "M7A1-010": "ATG_HORSE:793549", "M7A1-017": "ATG_HORSE:791286", "M7A1-040": "ATG_HORSE:788027", "M7A1-052": "ATG_HORSE:793918"}


def load_new(fixtures):
    with zipfile.ZipFile(io.BytesIO(checked_bytes(fixtures / "m7b2b-official-snapshots-v1.zip", SOURCE_SHA))) as z:
        if len(z.namelist()) != len(set(z.namelist())) or sum(i.file_size for i in z.infolist()) > 20_000_000:
            raise ValueError("INVALID_SOURCE_ARCHIVE")
        manifest = json.loads(z.read("manifest.json"))
        if manifest["schema"] != "M7B2B_OFFICIAL_AVAILABILITY_SNAPSHOTS_V1":
            raise ValueError("UNREVIEWED_SOURCE_SCHEMA")
        output = {}
        for member, ref in manifest["sources"].items():
            raw = z.read(member)
            if sha(raw) != ref["sha256"] or len(raw) != ref["bytes"] or ref["status"] != 200 or ref["url"] != ref["final_url"]:
                raise ValueError("SOURCE_PROVENANCE_CONFLICT")
            timestamp(ref["observed_at"])
            output[ref["url"]] = ({**ref, "archive_sha256": SOURCE_SHA, "member": member}, raw)
    return output


def pit_decision(record):
    """Versioned research contract: labels may be late; input bytes may not be."""
    if record.get("evaluate") is False:
        return {"pit_decision": "PIT_NOT_EVALUATED", "reasons": ["OUTSIDE_EVALUATED_SCOPE"], "model_eligible": False}
    reasons, violations = [], []
    if record.get("model_eligible") is not False:
        violations.append("MODEL_ADMISSION_FORBIDDEN")
    if record.get("purpose") != "AS_OBSERVED_INPUT_EVIDENCE":
        violations.append("LABEL_OR_UNAPPROVED_ROLE_CANNOT_BECOME_INPUT")
    if record.get("origin") != "ORIGINAL_ARCHIVED_BYTES":
        violations.append("RECONSTRUCTED_SNAPSHOT_FORBIDDEN")
    if record.get("correction_status") == "CORRECTED_WITHOUT_ASOF_VERSION":
        reasons.append("CORRECTION_HAS_NO_PRESERVED_ASOF_VERSION")
    if not record.get("identity_evidence", {}).get("stable_identity"):
        reasons.append("IDENTITY_EVIDENCE_MISSING")
    if record.get("identity_evidence", {}).get("conflict"):
        violations.append("IDENTITY_COLLISION_OR_CONFLICT")
    cutoff = record.get("decision_cutoff_at", MISSING)
    if cutoff == MISSING:
        reasons.append("CUTOFF_MISSING")
    else:
        end = timestamp(cutoff)
        zone = record.get("target_timezone")
        if zone not in {"Europe/Oslo", "Europe/Stockholm"}:
            violations.append("UNAPPROVED_TARGET_TIMEZONE")
        else:
            expected = timestamp(local_instant(record["target_schedule_local"], zone)) - timedelta(minutes=record["cutoff_minutes"])
            if end != expected:
                violations.append("CUTOFF_OFFSET_OR_DST_CONFLICT")
        for field in ("published_at", "source_snapshot_at", "first_observed_at"):
            value = record.get(field, MISSING)
            if value != MISSING and timestamp(value) >= end:
                violations.append(f"{field}:POST_CUTOFF")
        event = record.get("event_time", MISSING)
        if event != MISSING and timestamp(event) >= end:
            violations.append("EVENT_AFTER_CUTOFF")
        elif event == MISSING:
            event_date = record.get("event_date", MISSING)
            if event_date == MISSING:
                reasons.append("EVENT_TIME_AND_DATE_MISSING")
            elif zone in {"Europe/Oslo", "Europe/Stockholm"}:
                local_day = end.astimezone(ZoneInfo(zone)).date()
                if date.fromisoformat(event_date) > local_day:
                    violations.append("EVENT_AFTER_CUTOFF")
                elif date.fromisoformat(event_date) == local_day:
                    reasons.append("EVENT_CLOCK_MISSING_ON_CUTOFF_DAY")
    available = record.get("availability_evidence", {})
    version = record.get("source_version", {})
    if (not re.fullmatch(r"[0-9a-f]{64}", str(version.get("sha256", "")))
            or not version.get("url") or not version.get("archive_sha256") or not version.get("member")):
        reasons.append("SOURCE_VERSION_PROVENANCE_MISSING")
    if (available.get("type") != "HASH_BOUND_OBSERVATION" or not available.get("reference")
            or record.get("source_snapshot_at", MISSING) == MISSING or record.get("first_observed_at", MISSING) == MISSING):
        reasons.append("NO_POSITIVE_OBSERVATION_PROOF")
    if (record.get("source_snapshot_at", MISSING) != record.get("first_observed_at", MISSING)
            or record.get("source_snapshot_at", MISSING) != version.get("observed_at", MISSING)
            or available.get("reference", {}).get("sha256") != version.get("sha256")):
        reasons.append("OBSERVATION_NOT_BOUND_TO_SELECTED_VERSION")
    status = "PIT_VIOLATION" if violations else "PIT_UNPROVEN" if reasons else "PIT_VERIFIED"
    return {"pit_decision": status, "reasons": sorted(set(reasons + violations)), "model_eligible": False,
        "scope": "AS_OBSERVED_SOURCE_EVIDENCE_ONLY_NOT_MODEL_FEATURE_ADMISSION"}


def compare_versions(before, after):
    changes = {k: {"before": before.get(k, MISSING), "after": after.get(k, MISSING)}
        for k in sorted(set(before) | set(after)) if before.get(k, MISSING) != after.get(k, MISSING)}
    return {"interval_status": "SCOPED_CHANGE_OBSERVED" if changes else "NO_SCOPED_CHANGE_OBSERVED", "changes": changes,
        "full_correction_history": "UNKNOWN_BEFORE_FIRST_PRESERVED_AND_BETWEEN_OBSERVATIONS"}


def signature(row, race, identity, ref, raw, no_case, program):
    if race["country"] == "NO":
        check = dnt_review(row, no_case, (ref, raw), program)
        return {"horse_id": check["horse_identity"], "race": race["external_race_identifier"],
            "cells": check["raw_official_result"]["cells"], "start_method": check["values"]["start_method"]}
    data = json.loads(raw)
    if len(data["races"]) != 1:
        raise ValueError("CONFLICTING_OFFICIAL_RACE")
    r = data["races"][0]
    horse_id = int(identity.split(":")[1])
    selected = [s for s in r["starts"] if s["horse"]["id"] == horse_id]
    if (r["id"] != race["external_race_identifier"] or r["date"] != row["historical_date"]
            or r["number"] != row["historical_race_number"] or r["track"]["countryCode"] != "SE"
            or r["sport"] != "trot" or len(selected) != 1
            or len({s["horse"]["id"] for s in r["starts"]}) != len(r["starts"])):
        raise ValueError("OFFICIAL_RACE_OR_HORSE_COLLISION")
    s = selected[0]
    h = s["horse"]
    return {"horse_id": f"ATG_HORSE:{h['id']}", "name": h["name"], "pedigree": h["pedigree"],
        "race": r["id"], "race_status": r["status"], "track": r["track"]["id"], "distance": s["distance"],
        "start_method": r["startMethod"], "scratched": s.get("scratched", MISSING),
        "result": {k: s["result"].get(k, MISSING) for k in ("place", "finishOrder", "kmTime", "galloped", "disqualified")}}


def source_control(oid, row, doc, pdfhorse, sig, current, all_new, canonical):
    """The source-first packet contains no prior identity status/normalized answer."""
    stable = REVIEW[oid]  # Codex source-read findings, separately compared below.
    source_identity = sig["horse_id"]
    selected = next(h for h in canonical if h["startNumber"] == row["target_program_number"])
    extra = {}
    if stable.startswith("DNT_"):
        url = "https://www.travsport.no/sportsbasen/sportssok/horse/" + stable.split(":")[1]
        profile_ref, body = all_new[url]
        text = " ".join(html.unescape(re.sub(r"<[^>]+>", " ", body.decode())).split())
        match = re.search(r"UELN:\s*(\d+)", text)
        year = re.search(r"Årgang\s*:\s*(\d{4})", text)
        valid = bool(match and stable.split(":")[1] == match[1] == selected["horseRegistrationNumber"])
        extra = {"profile_source": profile_ref, "profile_registration": match[1] if match else MISSING,
            "documented_birth_year": int(year[1]) if year else MISSING}
    else:
        # Names are only localization. Stable ID plus two pedigree attributes are
        # checked against the original PDF; earlier ATG target chain is separate.
        from .swedish_identity import biography
        bio = biography(pdfhorse["identity_text"])
        pedigree = tuple(name_key(sig["pedigree"][k]["name"]) for k in ("father", "mother"))
        valid = bool(bio and bio[2:] == pedigree and name_key(sig["name"]) == name_key(pdfhorse["name"]))
        extra = {"original_pdf_biography": pdfhorse["identity_text"], "official_pedigree": sig["pedigree"],
            "original_tmp_preserved": selected["horseRegistrationNumber"], "target_chain_scope": "PINNED_M7B2A_CHAIN_REPLAYED_SEPARATELY"}
    return {"observation_id": oid, "status": "SOURCE_FIRST_CORROBORATED" if valid and stable == source_identity else "CONTROL_CONFLICT",
        "reader_source_findings": stable, "actual_current_source_identity": source_identity, "original_name": pdfhorse["name"],
        "original_pdf_line": row["raw_history_line"], "official_source": current, **extra,
        "controller": "SAME_CODEX_SEPARATE_AGENT_CONTROL_NOT_HUMAN_OR_BLINDED", "model_eligible": False}


def run(root):
    from pypdf import PdfReader

    root = Path(root)
    docs, fixtures = root / "docs", root / "tests/fixtures"
    evidence = json.loads(checked_bytes(docs / "M7B2A_EVIDENCE.json", EVIDENCE_SHA))
    old_reports = {}
    for spec in evidence["outputs"]:
        if spec["path"].startswith("docs/"):
            old_reports[Path(spec["path"]).name] = json.loads(checked_bytes(root / spec["path"], spec["sha256"]))
    if feasibility_run(root) != old_reports:
        raise ValueError("M7B2A_FROZEN_BASELINE_CHANGED")
    new = load_new(fixtures)
    old_index, old_targets = archive_index(fixtures)
    original = read_sources(fixtures / "m7a-pdf-validation.zip")
    pdf_generation = {}
    with zipfile.ZipFile(fixtures / "m7a-pdf-validation.zip") as z:
        for digest, (meta, _) in original.items():
            md = PdfReader(io.BytesIO(z.read(meta["pdf_member"]))).metadata
            dt = md.creation_date
            pdf_generation[digest] = {"raw": md.get("/CreationDate", MISSING),
                "value": dt.isoformat() if dt and dt.tzinfo else MISSING, "basis": "PDF_DECLARED_CREATION_DATE_NOT_PUBLICATION"}
    rows = json.loads((fixtures / "m7a1-ground-truth-v1.json").read_bytes())["rows"] + json.loads((fixtures / "m7b1-holdout-v1.json").read_bytes())["rows"]
    rows = {r["observation_id"]: r for r in rows}
    ids = old_reports["M7B2A_IDENTITY_LEDGER.json"]["observations"]
    races = {r["observation_id"]: r for r in old_reports["M7B2A_RACE_IDENTITY_LEDGER.json"]["observations"]}
    times = {r["observation_id"]: r for r in old_reports["M7B2A_PIT_EVIDENCE.json"]["observations"]}
    program = DailyArchive(fixtures / "rikstoto-2026-10-20.zip", PROGRAM_SHA, "2026-10-20")
    claims = json.loads((docs / "M7B1A_REVIEW_CLAIMS.json").read_bytes())["no_cases"]
    claims += [c for c in json.loads((docs / "M7B1B_REVIEW_CLAIMS.json").read_bytes())["claims"] if c["kind"] == "DNT"]
    availability, corrections, controls, decisions = [], [], [], []
    for ident in ids:
        oid = ident["observation_id"]
        row, race, t = rows[oid], races[oid], times[oid]
        prior_ref = ident["official_historical_source"]
        old_ref, old_body = old_index[(prior_ref["url"], prior_ref["sha256"])]
        ref, body = new[prior_ref["url"]]
        case = next((c for c in claims if c["observation_id"] == oid), None)
        before = signature(row, race, ident["stable_identity"], old_ref, old_body, case, program)
        after = signature(row, race, ident["stable_identity"], ref, body, case, program)
        compare = compare_versions(before, after)
        version_before = json.loads(old_body).get("currentVersion", MISSING) if race["country"] == "SE" else MISSING
        version_after = json.loads(body).get("currentVersion", MISSING) if race["country"] == "SE" else MISSING
        corrections.append({"observation_id": oid, **compare, "before": before, "after": after,
            "before_source": old_ref, "after_source": ref, "provider_version_before": version_before,
            "provider_version_after": version_after, "version_meaning": "OPAQUE_CURRENT_VERSION_NOT_PUBLICATION_OR_CORRECTION_TIMESTAMP",
            "adjudication_research_indicator": "PDF_RAW_FRD_COMPONENT_NO_BEFORE_VERSION_OR_CHANGE_TIME" if oid == "M7A1-017" else "NOT_EVIDENCE_OF_LATER_CHANGE",
            "model_eligible": False})
        meta, doc, pdfhorse = target_document(row, original)
        mid, no = row["target_race_id"].split(":")[1:]
        canonical = meta["canonical_starts"][mid]["response"]["result"][no]
        if oid in REVIEW:
            controls.append(source_control(oid, row, doc, pdfhorse, after, ref, new, canonical))
        same_url_refs = [r for r, _ in old_index.values() if r["url"] == prior_ref["url"]] + [ref]
        earliest = min(same_url_refs, key=lambda r: timestamp(r["observed_at"]))
        availability.append({"observation_id": oid, "event_time": t["historical_race_datetime"], "event_date": row["historical_date"],
            "result_official_at": MISSING, "published_at": MISSING, "first_observed_at": t["source_observed_at"],
            "first_official_observed_at": earliest["observed_at"], "first_official_observation_reference": earliest,
            "first_observed_meaning": "EARLIEST_PRESERVED_IN_AVAILABLE_ARCHIVES_NOT_EARLIEST_EVER",
            "pdf_generated_at": pdf_generation[row["pdf_sha256"]], "pdf_downloaded_at": t["source_observed_at"],
            "pdf_generation_reference": {"pdf_sha256": row["pdf_sha256"], "source_archive": "tests/fixtures/m7a-pdf-validation.zip"},
            "pdf_evidence": t["availability_evidence_reference"]["pdf"], "later_control_source": ref,
            "transport_headers": ref["headers"], "header_interpretation": "HTTP_DATE_ETAG_AGE_ARE_NOT_RESULT_PUBLICATION_OR_APPROVAL",
            "official_status_at_snapshot": after.get("race_status", "OFFICIAL_DNT_RESULT_TABLE_PRESENT_NO_APPROVAL_TIMESTAMP"),
            "publication_search": "Checked race/result fields and HTML time/publication metadata; no documented publication/approval clock or revision log supplied",
            "decision_cutoffs": {str(a["minutes_before_scheduled_start"]): a["decision_cutoff_at"] for a in old_reports["M7B2A_CUTOFF_AUDIT.json"]["observations"] if a["observation_id"] == oid},
            "model_eligible": False})
        for audit in old_reports["M7B2A_CUTOFF_AUDIT.json"]["observations"]:
            if audit["observation_id"] != oid:
                continue
            base = {"observation_id": oid, "event_time": t["historical_race_datetime"], "event_date": row["historical_date"], "published_at": MISSING,
                "first_observed_at": t["source_observed_at"], "source_snapshot_at": t["source_observed_at"],
                "decision_cutoff_at": audit["decision_cutoff_at"], "target_schedule_local": timestamp(t["target_race_datetime"]).astimezone(ZoneInfo(t["target_timezone"])).replace(tzinfo=None).isoformat(),
                "target_timezone": t["target_timezone"], "cutoff_minutes": audit["minutes_before_scheduled_start"],
                "source_version": t["availability_evidence_reference"]["pdf"], "correction_status": "ORIGINAL_PDF_AS_OBSERVED_UNKNOWN_PRIOR_HISTORY",
                "identity_evidence": {"stable_identity": ident["stable_identity"], "role": "RETROSPECTIVE_REVIEW_ONLY_NOT_PRE_RACE_ID_ASSERTION", "conflict": False},
                "availability_evidence": {"type": "HASH_BOUND_OBSERVATION", "reference": t["availability_evidence_reference"]["pdf"]},
                "purpose": "AS_OBSERVED_INPUT_EVIDENCE", "origin": "ORIGINAL_ARCHIVED_BYTES", "model_eligible": False}
            pdf_pit = pit_decision(base)
            # Never insert the later controls into an old decision. An absent
            # original official chain is UNPROVEN; attempting to use it is a violation.
            chain = "PIT_VERIFIED" if audit["pit_status"] == "PIT_VERIFIED" and not compare["changes"] else "PIT_UNPROVEN"
            decisions.append({"observation_id": oid, "cutoff_minutes": base["cutoff_minutes"], "decision_cutoff_at": base["decision_cutoff_at"],
                "pdf_contract": base, "pdf_pit_decision": pdf_pit, "historical_result_chain_pit_decision": chain,
                "baseline_selected_chain_status": audit["pit_status"], "A_C_D": audit["A_D"], "A_E_research": audit["A_E"] and chain == "PIT_VERIFIED",
                "exclusion_reasons": sorted(set(audit["exclusion_reasons"] + (["NO_ORIGINAL_OFFICIAL_ASOF_CHAIN"] if chain != "PIT_VERIFIED" else []))),
                "model_eligible": False})
    replay = historical_replay(original, old_targets, new, decisions)
    report = summarize(availability, corrections, controls, decisions, ids, races, root)
    common = {"version": "0.1.0", "allowed_use": "RESEARCH_ONLY", "model_eligible": False}
    return {"M7B2B_AVAILABILITY_LEDGER.json": {"schema": "M7B2B_AVAILABILITY_V1", **common, "observations": availability},
        "M7B2B_CORRECTION_AUDIT.json": {"schema": "M7B2B_CORRECTION_AUDIT_V1", **common, "observations": corrections},
        "M7B2B_IDENTITY_REVIEW.json": {"schema": "M7B2B_IDENTITY_REVIEW_V1", **common,
            "selection_method": "RISK_BASED_4_NO_UELN_PROFILE_AND_4_SE_TMP_ATG_PEDIGREE_DQ_FRD_WIN_COMPOSITION",
            "controller": "SAME_CODEX_SEPARATE_SOURCE_FIRST_AGENT_CONTROL", "organizationally_independent": False,
            "human": False, "blinded": False, "prior_status_used_as_lookup_truth": False, "all_51_mechanically_checked": True, "observations": controls},
        "M7B2B_HISTORICAL_REPLAY.json": {"schema": "M7B2B_HISTORICAL_REPLAY_V1", **common, **replay},
        "M7B2B_GATE_REPORT.json": {"schema": "M7B2B_GATE_REPORT_V1", **common, **report, "cutoff_observations": decisions}}


def historical_replay(originals, targets, new, decisions):
    t_ref, payload = targets["atg-2026-10-21_5_9.json"]
    target = payload["races"][0]
    if target["id"] != "2026-10-21_5_9" or target["status"] != "results" or timestamp(t_ref["observed_at"]).date().isoformat() <= target["date"]:
        raise ValueError("COMPLETED_HISTORICAL_TARGET_NOT_PROVEN")
    meta, _ = next((m, pages) for m, pages in originals.values() if m["date"] == "2026-10-21")
    doc = next(d for d in meta["archived_parser_output"] if d["race"]["race_number"] == 9 and any(h["name"] == "FLYING FINN" for h in d["entrants"]))
    starts_ref, body = new["https://www.rikstoto.no/api/racedays/S1_NR_2026-10-21/starts"]
    starts = json.loads(body)["response"]["result"]["9"]
    if {(h["program_number"], name_key(h["name"])) for h in doc["entrants"]} != {(h["startNumber"], name_key(h["horseName"])) for h in starts}:
        raise ValueError("ORIGINAL_REPLAY_FIELD_CONFLICT")
    # Freeze only the original program/canonical source. No later ATG ID/result
    # or today's official response is supplied to this historical basis.
    frozen = {"pdf_sha256": meta["pdf_sha256"], "target_race_id": "RIKSTOTO:S1_NR_2026-10-21:9",
        "original_starts_source": {k: starts_ref[k] for k in ("url", "observed_at", "sha256", "parent_archive_sha256", "parent_member", "parent_asset_url")}, "scheduled_time_local": doc["race"]["scheduled_time_local"],
        "roster": [{"number": h["startNumber"], "name": h["horseName"], "original_registration": h["horseRegistrationNumber"]} for h in starts],
        "raw_history_by_horse": [{"name": h["name"], "number": h["program_number"], "biography": h["identity_text"],
            "history_lines": [p["raw_text"] for p in h["past_starts"]]} for h in doc["entrants"]]}
    basis_sha = sha(json.dumps(frozen, ensure_ascii=False, sort_keys=True).encode())
    source_observed = next(a["pdf_contract"]["source_snapshot_at"] for a in decisions if a["observation_id"] == "M7A1-040")
    scenarios = []
    for minutes in SCENARIOS:
        a = next(a for a in decisions if a["observation_id"] == "M7A1-040" and a["cutoff_minutes"] == minutes)
        proven = timestamp(source_observed) < timestamp(a["decision_cutoff_at"]) and timestamp(starts_ref["observed_at"]) < timestamp(a["decision_cutoff_at"])
        scenarios.append({"cutoff_minutes": minutes, "decision_cutoff_at": a["decision_cutoff_at"], "source_snapshot_replay": "PROVEN" if proven else "REPLAY_NOT_PROVEN",
            "frozen_basis_sha256": basis_sha, "verified_historical_result_input_replay": "REPLAY_NOT_PROVEN",
            "reason": "Original PDF and TMP roster exist before cutoff; official historical-result and stable ATG evidence were observed later. No retrospective lookup enters frozen basis.", "model_eligible": False})
    return {"target_race_id": frozen["target_race_id"], "completion_evidence_label_only": t_ref,
        "original_frozen_basis": frozen, "frozen_basis_sha256": basis_sha, "field_size": len(starts),
        "raw_history_lines": sum(len(h["history_lines"]) for h in frozen["raw_history_by_horse"]), "scenarios": scenarios,
        "authentic_source_replay_scenarios": sum(s["source_snapshot_replay"] == "PROVEN" for s in scenarios),
        "verified_historical_input_replay_scenarios": 0,
        "prospective_plan_not_activated": "Archive official source versions and identity evidence before registered cutoffs; append corrections with observation/publication/officialization clocks where supplied. Never overwrite old bytes. No new collection or automation activated."}


def summarize(availability, corrections, controls, decisions, ids, races, root):
    baseline = json.loads((root / "docs/M7B1B_GATE_REPORT.json").read_bytes())
    by_id = {r["observation_id"]: r for r in baseline["observations"]}
    groups = {}
    for b in by_id.values():
        b["physical_venue"] = b["historical_venue"]["name"] if isinstance(b["historical_venue"], dict) else MISSING
        b["start_method"] = b["after_fields"]["start_method"]["value"]
        b["km_time_status"] = b["after_fields"]["km_time"]["status"]
        b["raw_result_code"] = json.dumps(b["raw_codes"], sort_keys=True, ensure_ascii=False)
    for key in ("historical_country", "printed_track", "physical_venue", "historical_date", "result_status", "gallop_evidence", "dq_evidence", "start_method", "km_time_status", "raw_result_code"):
        groups[key] = {}
        for value in sorted({by_id[i["observation_id"]][key] for i in ids}):
            subset = {i["observation_id"] for i in ids if by_id[i["observation_id"]][key] == value}
            groups[key][value] = {"observations": len(subset), "published": 0, "official_approval_time": 0,
                "cutoffs": {str(m): {"chain_pit_verified": sum(d["historical_result_chain_pit_decision"] == "PIT_VERIFIED" for d in decisions if d["observation_id"] in subset and d["cutoff_minutes"] == m),
                    "A_E_research": sum(d["A_E_research"] for d in decisions if d["observation_id"] in subset and d["cutoff_minutes"] == m)} for m in SCENARIOS}}
    return {"observations": len(availability), "identity_chains_checked": len(ids), "source_first_controls": len(controls),
        "A_C": sum(d["A_C_D"] for d in decisions if d["cutoff_minutes"] == 4), "outside_cohort_pit": {"PIT_NOT_EVALUATED": 39},
        "source_first_conflicts": sum(c["status"] != "SOURCE_FIRST_CORROBORATED" for c in controls),
        "publication_times_verified": 0, "publication_times_unknown": len(availability), "official_approval_times_verified": 0,
        "documented_scoped_corrections": sum(bool(c["changes"]) for c in corrections), "complete_correction_histories": 0,
        "opaque_provider_version_changes": sum(c["provider_version_before"] != c["provider_version_after"] for c in corrections),
        "cutoffs": {str(m): {"pdf_pit_verified": sum(d["pdf_pit_decision"]["pit_decision"] == "PIT_VERIFIED" for d in decisions if d["cutoff_minutes"] == m),
            "chain_pit_counts": dict(Counter(d["historical_result_chain_pit_decision"] for d in decisions if d["cutoff_minutes"] == m)),
            "A_C_D": sum(d["A_C_D"] for d in decisions if d["cutoff_minutes"] == m),
            "A_E_research": sum(d["A_E_research"] for d in decisions if d["cutoff_minutes"] == m)} for m in SCENARIOS},
        "selection_groups": groups, "baseline_reference_unchanged": "M7B2A_GATE_REPORT.json:51/33/18/9;33 late controls;model0",
        "existing_gate_admission": "CLOSED_UNCHANGED", "representative": False, "recommendation": "M7B2_NEXT_RESEARCH"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists():
        raise ValueError("NEW_RESEARCH_OUTPUT_DIRECTORY_REQUIRED")
    reports = run(args.root)
    args.output_dir.mkdir(parents=True)
    for name, report in reports.items():
        (args.output_dir / name).write_text(json.dumps(report, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")
    summary = reports["M7B2B_GATE_REPORT.json"]
    print(json.dumps({k: v for k, v in summary.items() if k not in ("selection_groups", "cutoff_observations")}, indent=2))


if __name__ == "__main__":
    main()
