"""Offline observation-scoped identity and availability study; never model admission."""
from __future__ import annotations

import argparse
import io
import json
import re
import zipfile
from collections import Counter
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .date_overview import DailyArchive, timestamp
from .history_quality import SOURCE_SHA as QUALITY_SOURCE_SHA
from .history_quality import run as quality_run
from .history_semantic_benchmark import HOLDOUT_SHA, KNOWN_SHA
from .history_source_verification import (
    ATG_SHA,
    OFFICIAL_SHA,
    PROGRAM_SHA,
    SOURCE_SHA,
    atg_review,
    bind_verified,
    dnt_review,
    sources,
)
from .pdf_semantic_validation import checked_bytes, read_sources, truth_data
from .pdf_validation import physical_candidates, sha
from .provider_capability import name_key
from .swedish_identity import biography

MANIFEST_SHA = "e66bbb68234f45822ab26735f4d7bab4fcb9f5ba91ab494b0e8cad772828aee0"
BASELINE_SHA = "2d577dd47e62272da39a994f8ace4fd16bbcbd253fc7f37c513cb7d06557c270"
SCENARIOS = (1440, 60, 15, 4)
MISSING = "NOT_REPORTED"


def local_instant(value, zone):
    """Require a unique real local instant; never guess a DST fold/gap or zone."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is not None:
        raise ValueError("LOCAL_TIME_MUST_HAVE_EXPLICIT_IANA_ZONE")
    tz = ZoneInfo(zone)
    candidates = {dt.replace(tzinfo=tz, fold=f).astimezone(UTC) for f in (0, 1)
        if dt.replace(tzinfo=tz, fold=f).astimezone(UTC).astimezone(tz).replace(tzinfo=None) == dt}
    if len(candidates) != 1:
        raise ValueError("AMBIGUOUS_OR_NONEXISTENT_LOCAL_TIME")
    return candidates.pop().isoformat()


def provenance(ref):
    try:
        return bool(ref["url"] and re.fullmatch(r"[0-9a-f]{64}", ref["sha256"]) and timestamp(ref["observed_at"]))
    except (KeyError, TypeError, ValueError):
        return False


def select_asof(snapshots, cutoff):
    """A future/corrected version cannot replace the bytes frozen before cutoff."""
    end = timestamp(cutoff)
    candidates = [s for s in snapshots if provenance(s) and timestamp(s["observed_at"]) < end
        and (s.get("published_at", MISSING) == MISSING or timestamp(s["published_at"]) <= timestamp(s["observed_at"]))]
    if not candidates:
        return None
    latest = max(timestamp(s["observed_at"]) for s in candidates)
    chosen = [s for s in candidates if timestamp(s["observed_at"]) == latest]
    if len({s["sha256"] for s in chosen}) != 1:
        raise ValueError("CONFLICTING_ASOF_VERSIONS")
    return deepcopy(chosen[0])


def pit_check(event_date, event_at, cutoff, chains, event_zone="Europe/Stockholm"):
    """Validate specified source roles as-of; late retrieval is not late publication."""
    reasons, selected = [], {}
    if not chains:
        reasons.append("NO_POSITIVE_AVAILABILITY_CHAIN")
    if cutoff == MISSING:
        return {"pit_status": "PIT_UNKNOWN", "reasons": ["TARGET_TIME_OR_CUTOFF_MISSING"], "selected_sources": {}}
    end = timestamp(cutoff)
    if event_at != MISSING:
        if timestamp(event_at) >= end:
            reasons.append("HISTORICAL_EVENT_NOT_BEFORE_CUTOFF")
    elif date.fromisoformat(event_date) > end.astimezone(ZoneInfo(event_zone)).date():
        reasons.append("HISTORICAL_EVENT_NOT_BEFORE_CUTOFF")
    elif timestamp(local_instant((date.fromisoformat(event_date) + timedelta(days=1)).isoformat() + "T00:00", event_zone)) > end:
        reasons.append("EVENT_CLOCK_MISSING_OR_SAME_DAY")
    for role, snapshots in chains.items():
        if any(not provenance(s) for s in snapshots):
            reasons.append(f"{role}:INVALID_PROVENANCE")
        try:
            found = select_asof(snapshots, cutoff)
        except ValueError:
            reasons.append(f"{role}:CONFLICTING_VERSIONS")
            found = None
        if found:
            selected[role] = found
        else:
            reasons.append(f"{role}:NO_DOCUMENTED_ASOF_VERSION")
            if any(provenance(s) and timestamp(s["observed_at"]) >= end for s in snapshots):
                reasons.append(f"{role}:POST_CUTOFF_OBSERVATION_NOT_USABLE")
            if any(s.get("published_at", MISSING) != MISSING and timestamp(s["published_at"]) >= end for s in snapshots):
                reasons.append(f"{role}:POST_CUTOFF_PUBLICATION")
    if "HISTORICAL_EVENT_NOT_BEFORE_CUTOFF" in reasons or any("POST_CUTOFF" in s or "CONFLICTING" in s for s in reasons):
        status = "PIT_VIOLATION"
    elif reasons:
        status = "PIT_DATE_ONLY" if event_date else "PIT_UNKNOWN"
    else:
        status = "PIT_VERIFIED"
    return {"pit_status": status, "reasons": sorted(set(reasons)), "selected_sources": selected,
        "interpretation": "Selected evidence-chain usability, not earliest public availability or model approval."}


def se_identity(pdf, target, historical, number, expected_id):
    """Independent research D check: complete target field, biography and stable ID."""
    reasons = []
    field, past = target["starts"], historical["starts"]
    for starts in (field, past):
        if (len({s["horse"]["id"] for s in starts}) != len(starts)
                or len({s["number"] for s in starts}) != len(starts)
                or len({name_key(s["horse"]["name"]) for s in starts}) != len(starts)):
            return {"status": "IDENTITY_AMBIGUOUS", "reasons": ["FIELD_ID_OR_NAME_COLLISION"]}
    if {(h["program_number"], name_key(h["name"])) for h in pdf} != {(s["number"], name_key(s["horse"]["name"])) for s in field}:
        return {"status": "IDENTITY_CONFLICT", "reasons": ["TARGET_FULL_FIELD_CONFLICT"]}
    a = [s["horse"] for s in field if s["number"] == number]
    b = [s["horse"] for s in past if s["horse"]["id"] == expected_id]
    p = [h for h in pdf if h["program_number"] == number]
    if len(a) != 1 or len(b) != 1 or len(p) != 1:
        return {"status": "IDENTITY_NOT_FOUND", "reasons": ["STABLE_ID_OR_TARGET_NOT_FOUND"]}
    a, b, p = a[0], b[0], p[0]
    bio = biography(p["identity_text"])
    if type(expected_id) is not int or expected_id <= 0 or a["id"] != expected_id:
        reasons.append("STABLE_ID_CONFLICT")
    if not bio:
        return {"status": "IDENTITY_CANDIDATE", "reasons": ["BIOGRAPHY_NOT_DOCUMENTED"]}
    expected = (a.get("age"), a.get("sex"), *(name_key(a["pedigree"][k]["name"]) for k in ("father", "mother")))
    if bio != expected or tuple(name_key(b["pedigree"][k]["name"]) for k in ("father", "mother")) != bio[2:]:
        reasons.append("BIOGRAPHY_CONFLICT")
    if len({name_key(h["name"]) for h in (a, b, p)}) != 1:
        reasons.append("NAME_CHANGE_REQUIRES_SEPARATE_DOCUMENTATION")
    return {"status": "IDENTITY_CONFLICT" if reasons else "IDENTITY_VERIFIED", "reasons": reasons,
        "stable_identity": f"ATG_HORSE:{expected_id}", "names": {"pdf": p["name"], "target": a["name"], "historical": b["name"]},
        "attributes": {"target_age": a.get("age", MISSING), "sex": a.get("sex", MISSING),
            "sire": a["pedigree"]["father"], "dam": a["pedigree"]["mother"], "birth_year": MISSING},
        "method": "BOUND_TARGET_FULL_FIELD_PLUS_AGE_SEX_PEDIGREE_AND_SAME_HISTORICAL_OFFICIAL_ID"}


def combined(gates, identity, pit):
    values = {**gates, "D": "PASS" if identity == "IDENTITY_VERIFIED" else
        "FAIL" if identity in ("IDENTITY_CONFLICT", "IDENTITY_AMBIGUOUS") else "MISSING_EVIDENCE",
        "E": "PASS" if pit == "PIT_VERIFIED" else "FAIL" if pit == "PIT_VIOLATION" else "MISSING_EVIDENCE"}
    return {"gates": values, "A_C": all(values[g] == "PASS" for g in "ABC"),
        "A_D": all(values[g] == "PASS" for g in "ABCD"), "A_E": all(values[g] == "PASS" for g in "ABCDE"),
        "A_C_plus_D": all(values[g] == "PASS" for g in "ABCD"), "A_C_plus_D_plus_E": all(values[g] == "PASS" for g in "ABCDE"),
        "allowed_use": "RESEARCH_ONLY", "model_eligible": False}


def envelope_files(path, expected):
    with zipfile.ZipFile(io.BytesIO(checked_bytes(path, expected))) as z:
        m = json.loads(z.read("manifest.json"))
        result = {}
        for member, digest in m["files_sha256"].items():
            body = checked_bytes_from_zip(z, member, digest)
            e = json.loads(body)
            if not e["success"] or e["status_code"] != 200:
                raise ValueError("OFFICIAL_RESPONSE_NOT_SUCCESSFUL")
            ref = {"url": e["url"], "observed_at": e["observed_at"], "sha256": digest,
                "archive_sha256": expected, "member": member, "hash_basis": "ARCHIVED_ENVELOPE_BYTES"}
            if not provenance(ref):
                raise ValueError("INVALID_ENVELOPE_PROVENANCE")
            result[member] = (ref, e["payload"])
        return result


def checked_bytes_from_zip(z, member, expected):
    body = z.read(member)
    if sha(body) != expected:
        raise ValueError("ARCHIVE_MEMBER_HASH_MISMATCH")
    return body


def archive_index(fixtures):
    index = {}
    for name, digest, schema in [("m7b1a-official-sources-v1.zip", SOURCE_SHA, "M7B1A_OFFICIAL_SOURCE_ARCHIVE_V1"),
            ("m7b1b-official-sources-v1.zip", QUALITY_SOURCE_SHA, "M7B1B_OFFICIAL_SOURCE_ARCHIVE_V1")]:
        for member, (meta, body) in sources(fixtures / name, expected_sha=digest, expected_schema=schema).items():
            ref = {**meta, "archive_sha256": digest, "member": member, "hash_basis": "ORIGINAL_RESPONSE_BYTES"}
            index[(meta["url"], meta["sha256"])] = (ref, body)
    old = envelope_files(fixtures / "m7a1-atg-results-v1.zip", OFFICIAL_SHA)
    for ref, payload in old.values():
        index[(ref["url"], ref["sha256"])] = (ref, json.dumps(payload).encode())
    return index, old


def crawler_proofs(fixtures, originals):
    result = {}
    with zipfile.ZipFile(io.BytesIO(checked_bytes(fixtures / "m7b2a-crawler-manifests-v1.zip", MANIFEST_SHA))) as z:
        manifest = json.loads(z.read("manifest.json"))
        if manifest["schema"] != "M7B2A_CRAWLER_MANIFEST_SUBSET_V1":
            raise ValueError("UNREVIEWED_CRAWLER_MANIFEST")
        for member, spec in manifest["sources"].items():
            raw = checked_bytes_from_zip(z, member, spec["sha256"])
            doc = json.loads(raw)
            meta, _ = originals[spec["pdf_sha256"]]
            if spec["parent_archive_sha256"] != meta["source_archive_sha256"] or spec["pdf_member"] != meta["source_archive_member"]:
                raise ValueError("ORIGINAL_PARENT_CHAIN_CONFLICT")
            url = meta["archived_parser_output"][0]["race"]["source_url"]
            matches = [x for x in doc["requests"] if x.get("url") == url and x.get("sha256") == spec["pdf_sha256"] and x.get("status") == "PDF_OK"]
            if len(matches) != 1:
                raise ValueError("ORIGINAL_PDF_DOWNLOAD_NOT_VERIFIED")
            req = matches[0]
            result[spec["pdf_sha256"]] = {"url": url, "sha256": spec["pdf_sha256"], "observed_at": req["at_utc"],
                "archive_sha256": MANIFEST_SHA, "member": member, "manifest_member_sha256": spec["sha256"],
                "original_parent": spec, "evidence_type": "ORIGINAL_CRAWLER_PDF_OK_HASH_AND_TIMESTAMP"}
    return result


def target_document(row, originals):
    meta, pages = originals[row["pdf_sha256"]]
    mid, no = row["target_race_id"].split(":")[1:]
    candidates = [d for d in meta["archived_parser_output"] if physical_candidates(d, meta["canonical_starts"]) == [f"{mid}#{no}"]]
    if len(candidates) != 1:
        raise ValueError("TARGET_PHYSICAL_FIELD_NOT_UNIQUE")
    doc = candidates[0]
    horse = [h for h in doc["entrants"] if h["program_number"] == row["target_program_number"]]
    if len(horse) != 1 or name_key(horse[0]["name"]) != name_key(row["target_horse_name"]):
        raise ValueError("TARGET_HORSE_BLOCK_CONFLICT")
    # Existing parser's scheduled field is checked against the printed heading.
    clock = doc["race"]["scheduled_time_local"]
    if not re.fullmatch(r"\d{2}:\d{2}", clock or "") or not any(clock in page and doc["entrants"][0]["header_text"] in page for page in pages):
        raise ValueError("TARGET_SCHEDULE_NOT_REPRODUCED_IN_PDF")
    return meta, doc, horse[0]


def run(root):
    root = Path(root)
    fixtures, docs = root / "tests/fixtures", root / "docs"
    baseline = json.loads(checked_bytes(docs / "M7B1B_GATE_REPORT.json", BASELINE_SHA))
    if quality_run(root) != baseline:
        raise ValueError("FROZEN_M7B1B_BASELINE_CHANGED")
    rows = truth_data(fixtures / "m7a1-ground-truth-v1.json", KNOWN_SHA)["rows"]
    rows += json.loads(checked_bytes(fixtures / "m7b1-holdout-v1.json", HOLDOUT_SHA))["rows"]
    originals = read_sources(fixtures / "m7a-pdf-validation.zip")
    downloads = crawler_proofs(fixtures, originals)
    official, old = archive_index(fixtures)
    m6 = envelope_files(fixtures / "atg-se-2026-10-20-identity.zip", ATG_SHA)
    program = DailyArchive(fixtures / "rikstoto-2026-10-20.zip", PROGRAM_SHA, "2026-10-20")
    claims = json.loads((docs / "M7B1A_REVIEW_CLAIMS.json").read_bytes())["no_cases"]
    claims += [c for c in json.loads((docs / "M7B1B_REVIEW_CLAIMS.json").read_bytes())["claims"] if c["kind"] == "DNT"]
    register = json.loads((docs / "M7B1B_TRACK_REGISTER.json").read_bytes())
    truth = {r["observation_id"]: r for r in rows}
    identities, races, evidence, audits = [], [], [], []
    for b in baseline["observations"]:
        if b["after"]["gates"]["C"] != "PASS":
            continue
        row = truth[b["observation_id"]]
        meta, target_doc, pdfhorse = target_document(row, originals)
        source_ref, body = official[(b["official_control"]["url"], b["official_control"]["sha256"])]
        country = b["historical_country"]
        mid, no = row["target_race_id"].split(":")[1:]
        target_raw = meta["canonical_starts"][mid]
        original = target_raw["response"]["result"][no]
        selected = next(h for h in original if h["startNumber"] == row["target_program_number"])
        identity_refs = []
        if country == "NO":
            case = next(c for c in claims if c["observation_id"] == row["observation_id"])
            review = dnt_review(row, case, (source_ref, body), program)
            stable = review["horse_identity"]
            identity = {"status": "IDENTITY_VERIFIED", "stable_identity": stable, "reasons": [],
                "names": {"pdf": pdfhorse["name"], "target": selected["horseName"], "historical": review["raw_official_result"]["cells"][2]},
                "attributes": {"original_registration": selected["horseRegistrationNumber"], "pdf_biography": pdfhorse["identity_text"],
                    "birth_year": MISSING}, "method": "EXACT_STABLE_REGISTRATION_IN_CANONICAL_TARGET_AND_DATED_OFFICIAL_HISTORICAL_RESULT"}
            external_race = re.search(r'(?:BJ|JA|BI|MO|KL|OR)_NR_' + row["historical_date"] + '/' + str(row["historical_race_number"]) + r'(?=[^0-9]|$)', body.decode()).group()
            historical_at, official_clock = MISSING, MISSING
            race_conditions = review["raw_official_result"]
            original_ref = program.source(f"meetings/{mid}/starts.json")
            identity_raw = program.read(f"meetings/{mid}/starts.json")
            identity_refs = [{"url": identity_raw["source_url"], "sha256": original_ref["member_sha256"], "observed_at": identity_raw["fetched_utc"], "archive_sha256": PROGRAM_SHA, **original_ref}]
        else:
            payload = json.loads(body)
            if len(payload["races"]) != 1:
                raise ValueError("AMBIGUOUS_HISTORICAL_RACE")
            historical = payload["races"][0]
            # All targets are already archived. Select race metadata/identity only,
            # never target result, pools, statistics, equipment or market values.
            if mid.endswith("2026-10-20"):
                tid = next(c["horse_id"] for c in json.loads((docs / "M7B1B_REVIEW_CLAIMS.json").read_bytes())["claims"] if c["observation_id"] == row["observation_id"]) if row["observation_id"] not in ("M7A1-017", "M7A1-020") else {"M7A1-017": 791286, "M7A1-020": 794752}[row["observation_id"]]
                options = [(ref, p["races"][0]) for ref, p in m6.values() if "races" in p and len(p["races"]) == 1
                    and any(s["horse"]["id"] == tid for s in p["races"][0]["starts"])]
                if len(options) != 1:
                    raise ValueError("TARGET_IDENTITY_SOURCE_NOT_UNIQUE")
                target_ref, target = options[0]
            else:
                member = "atg-2026-10-21_5_9.json" if mid.endswith("2026-10-21") else "atg-2026-10-24_7_1.json"
                target_ref, p = old[member]
                target = p["races"][0]
                tid = next(s["horse"]["id"] for s in target["starts"] if s["number"] == row["target_program_number"])
            if (target["date"] != meta["date"] or target["number"] != int(no) or target["sport"] != "trot"
                    or target["track"]["countryCode"] != "SE"):
                raise ValueError("TARGET_RACE_NAMESPACE_CONFLICT")
            identity = se_identity(target_doc["entrants"], target, historical, row["target_program_number"], tid)
            if identity["status"] != "IDENTITY_VERIFIED":
                raise ValueError(f"FROZEN_SOURCE_IDENTITY_REVIEW_CHANGED:{row['observation_id']}:{tid}:{identity}")
            proof = {"horse_id": tid, "pedigree": [name_key(identity["attributes"][k]["name"]) for k in ("sire", "dam")], "proof": target_ref}
            review = atg_review(row, {"country": "SE", "horse_id": tid}, (source_ref, body), proof) if source_ref["hash_basis"] != "ARCHIVED_ENVELOPE_BYTES" else None
            if review is None:
                raw = json.dumps(payload).encode()
                check_ref = {**source_ref, "sha256": sha(raw), "bytes": len(raw), "status": 200, "final_url": source_ref["url"]}
                review = atg_review(row, {"country": "SE", "horse_id": tid}, (check_ref, raw), proof)
            selected_start = next(s for s in historical["starts"] if s["horse"]["id"] == tid)
            external_race = historical["id"]
            official_clock = historical.get("startTime", MISSING)
            historical_at = local_instant(official_clock, "Europe/Stockholm") if official_clock != MISSING else MISSING
            race_conditions = {"start_method": historical["startMethod"], "distance_m": selected_start["distance"],
                "scratched": selected_start.get("scratched", MISSING), "raw_result": selected_start["result"]}
            identity_refs = [target_ref]
        verified_race = bind_verified(row, review, register)
        racekey = f"RESEARCH_RACE_V1:{sha(json.dumps([country, verified_race['track'], row['historical_date'], external_race], sort_keys=True).encode())}"
        oid = row["observation_id"]
        pdf_ref = downloads[row["pdf_sha256"]]
        zone = "Europe/Oslo" if b["target_country"] == "NO" else "Europe/Stockholm"
        target_at = local_instant(meta["date"] + "T" + target_doc["race"]["scheduled_time_local"], zone)
        raw_pdf_ref = {**pdf_ref, "pdf_page": row["pdf_page"], "raw_history_line": row["raw_history_line"]}
        identity.update({"observation_id": oid, "target_race_id": row["target_race_id"], "target_program_number": row["target_program_number"],
            "original_registration": selected["horseRegistrationNumber"], "pdf": raw_pdf_ref, "official_historical_source": source_ref,
            "target_identity_sources": identity_refs, "name_variants": sorted(set(identity["names"].values())),
            "alias_scope": "THIS_OBSERVATION_ONLY_NO_GLOBAL_MAPPING", "allowed_use": "RESEARCH_ONLY", "model_eligible": False})
        identities.append(identity)
        races.append({"observation_id": oid, "status": "PHYSICAL_RACE_VERIFIED", "country": country,
            "venue": verified_race["track"], "historical_date": row["historical_date"], "race_number": row["historical_race_number"],
            "pdf_printed_reference": {"track": row["historical_track"], "date": row["historical_date"], "race_number": row["historical_race_number"]},
            "external_race_identifier": external_race, "research_race_identifier": racekey, "official_source": source_ref,
            "conditions_and_label_only": race_conditions, "official_values_retrospective_only": review["values"], "historical_race_datetime": historical_at,
            "historical_raw_clock": official_clock, "historical_timezone": "Europe/Stockholm" if country == "SE" else "Europe/Oslo",
            "model_eligible": False})
        ev = {"observation_id": oid, "historical_race_datetime": historical_at, "historical_race_date": row["historical_date"],
            "result_official_at": MISSING, "source_published_at": MISSING, "source_available_to_provider_at": MISSING,
            "source_observed_at": pdf_ref["observed_at"], "parser_captured_at": row["source_evidence"]["source_observed_at"],
            "official_result_observed_at": source_ref["observed_at"], "identity_sources_observed_at": [x["observed_at"] for x in identity_refs],
            "target_race_datetime": target_at, "target_datetime_basis": "ORIGINAL_PDF_SCHEDULE_NOT_ACTUAL_START", "target_actual_start_at": MISSING, "target_timezone": zone,
            "target_schedule_pdf_pages": [i + 1 for i, page in enumerate(originals[row["pdf_sha256"]][1]) if target_doc["race"]["scheduled_time_local"] in page and target_doc["entrants"][0]["header_text"] in page],
            "availability_evidence_type": "HASH_BOUND_CRAWLER_OBSERVATION_PLUS_OFFICIAL_SNAPSHOTS",
            "availability_evidence_reference": {"pdf": raw_pdf_ref, "historical_official": source_ref, "identity": identity_refs},
            "publication_and_correction_history": "NOT_REPORTED_NO_EARLIEST_PUBLICATION_OR_OFFICIALIZATION_CLAIM",
            "model_eligible": False}
        evidence.append(ev)
        for minutes in SCENARIOS:
            cutoff = (timestamp(target_at) - timedelta(minutes=minutes)).isoformat()
            chains = {"PDF_EXCERPT": [pdf_ref], "OFFICIAL_HISTORICAL_RESULT": [source_ref],
                **{f"IDENTITY_{i}": [ref] for i, ref in enumerate(identity_refs)}}
            audit = pit_check(row["historical_date"], historical_at, cutoff, chains)
            pdf_audit = pit_check(row["historical_date"], historical_at, cutoff, {"PDF_EXCERPT": [pdf_ref]})
            gates = combined(b["after"]["gates"], identity["status"], audit["pit_status"])
            audits.append({"observation_id": oid, "minutes_before_scheduled_start": minutes, "decision_cutoff_at": cutoff,
                "target_race_datetime": target_at, "historical_event_before_cutoff": date.fromisoformat(row["historical_date"]) < timestamp(cutoff).date(),
                "pdf_only_availability": pdf_audit, **audit, **gates,
                "retrospective_label_research_usable": identity["status"] == "IDENTITY_VERIFIED", "research_asof_evidence_usable": gates["A_E"], "feature_materialized": False, "training_ready": False,
                "exclusion_reasons": sorted(set(b["after"]["exclusion_reasons"] + audit["reasons"] + identity["reasons"])),
                "legacy_reasons_preserved_not_rewritten": True})
    for ev in evidence:
        ev["pit_status_by_cutoff"] = {str(a["minutes_before_scheduled_start"]): a["pit_status"] for a in audits if a["observation_id"] == ev["observation_id"]}
    return build_reports(identities, races, evidence, audits, baseline)


def build_reports(identities, races, evidence, audits, baseline):
    by_id = {r["observation_id"]: r for r in baseline["observations"]}
    cohort = [by_id[r["observation_id"]] for r in identities]
    summaries = {}
    for minutes in SCENARIOS:
        subset = [r for r in audits if r["minutes_before_scheduled_start"] == minutes]
        summaries[str(minutes)] = {"observations": len(subset), "pit_status_counts": {s: sum(r["pit_status"] == s for r in subset) for s in ("PIT_VERIFIED", "PIT_DATE_ONLY", "PIT_INFERRED_UNAPPROVED", "PIT_UNKNOWN", "PIT_VIOLATION")},
            "pdf_only_status_counts": dict(Counter(r["pdf_only_availability"]["pit_status"] for r in subset)),
            **{key: sum(r[key] for r in subset) for key in ("A_C", "A_D", "A_E", "A_C_plus_D", "A_C_plus_D_plus_E")},
            "gate_counts": {g: dict(Counter(r["gates"][g] for r in subset)) for g in "ABCDE"},
            "exclusion_reason_counts": dict(sorted(Counter(v for r in subset for v in r["exclusion_reasons"]).items()))}
    groups = {}
    dimensions = {key: (lambda b, key=key: str(b[key])) for key in ("historical_country", "printed_track", "historical_date", "result_status", "gallop_evidence", "dq_evidence", "start_kind")}
    dimensions.update(start_method=lambda b: str(b["after_fields"]["start_method"]["value"]),
        km_time_complete=lambda b: str(b["after_fields"]["km_time"]["status"] == "EXTRACTED"))
    for dim, getter in dimensions.items():
        groups[dim] = {}
        for val in sorted({getter(b) for b in cohort}):
            ids = {b["observation_id"] for b in cohort if getter(b) == val}
            groups[dim][val] = {"observations": len(ids), "gate_D_pass": sum(r["status"] == "IDENTITY_VERIFIED" for r in identities if r["observation_id"] in ids),
                "gate_B_pass": sum(b["after"]["gates"]["B"] == "PASS" for b in cohort if b["observation_id"] in ids),
                "scenario_counts": {str(m): {"E_pass": sum(a["pit_status"] == "PIT_VERIFIED" for a in audits if a["observation_id"] in ids and a["minutes_before_scheduled_start"] == m),
                    "ABCDE": sum(a["A_E"] for a in audits if a["observation_id"] in ids and a["minutes_before_scheduled_start"] == m)} for m in SCENARIOS}}
    summary = {"cohort": len(identities), "original_diagnostic_denominator": 90, "A_C": sum(all(b["after"]["gates"][g] == "PASS" for g in "ABC") for b in cohort),
        "identity_status_counts": {s: sum(r["status"] == s for r in identities) for s in ("IDENTITY_VERIFIED", "IDENTITY_CANDIDATE", "IDENTITY_AMBIGUOUS", "IDENTITY_CONFLICT", "IDENTITY_NOT_FOUND")}, "physical_race_verified": len(races),
        "unique_physical_races": len({r["research_race_identifier"] for r in races}), "single_gate_counts": {"A": {"PASS": 51}, "B": {"PASS": 33, "MISSING_EVIDENCE": 18}, "C": {"PASS": 51}, "D": {"PASS": sum(r["status"] == "IDENTITY_VERIFIED" for r in identities)}},
        "outside_cohort_D_E": {"NOT_EVALUATED": 39}, "critical_identity_conflicts": sum(r["status"] in ("IDENTITY_CONFLICT", "IDENTITY_AMBIGUOUS") for r in identities),
        "future_historical_events": sum(not r["historical_event_before_cutoff"] for r in audits), "source_published_at_documented": 0,
        "pdf_observation_documented": len(evidence), "official_observation_documented": len(evidence),
        "scenarios": summaries, "selection_groups": groups, "model_eligible": 0, "representative": False,
        "history_feature_contract": "HISTORY_FEATURE_CONTRACT_NOT_VALIDATED", "recommendation": "M7B2_NEXT_RESEARCH"}
    common = {"version": "0.1.0", "allowed_use": "RESEARCH_ONLY", "model_eligible": False}
    return {"M7B2A_IDENTITY_LEDGER.json": {"schema": "M7B2A_IDENTITY_LEDGER_V1", **common, "observations": identities},
        "M7B2A_RACE_IDENTITY_LEDGER.json": {"schema": "M7B2A_RACE_LEDGER_V1", **common, "observations": races},
        "M7B2A_PIT_EVIDENCE.json": {"schema": "M7B2A_PIT_EVIDENCE_V1", **common, "observations": evidence},
        "M7B2A_CUTOFF_AUDIT.json": {"schema": "M7B2A_CUTOFF_AUDIT_V1", **common, "observations": audits},
        "M7B2A_GATE_REPORT.json": {"schema": "M7B2A_GATE_REPORT_V1", **common, **summary}}


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
    summary = reports["M7B2A_GATE_REPORT.json"]
    print(json.dumps({k: v for k, v in summary.items() if k != "selection_groups"}, indent=2))


if __name__ == "__main__":
    main()
