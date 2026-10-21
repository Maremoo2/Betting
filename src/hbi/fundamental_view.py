"""Descriptive, market-free evidence view; never a model input or decision producer."""
from __future__ import annotations

import re
from collections import Counter
from datetime import date

from .provider_capability import name_key


def fact(kind, value, sources, limitation=None):
    return {"kind": kind, "value": value, "source_refs": sources, "limitation": limitation}


def reference(archive, member, url, observed, pointer):
    return {**archive.source(member), "url": url, "observed_at": observed,
            "json_pointer": pointer, "historical_published_at": None}


def counts(stats):
    keys = ["numberOfStarts", "numberOfFirstPlaces", "numberOfSecondPlaces", "numberOfThirdPlaces"]
    values = [stats.get(k) for k in keys]
    if any(type(v) is not int or v < 0 for v in values) or sum(values[1:]) > values[0]:
        return None
    return dict(zip(["starts", "wins", "seconds", "thirds"], values, strict=True))


def verified_counts(stats, section, label):
    parsed = counts(stats)
    if parsed is None:
        return None
    token = "-".join(str(v) for v in parsed.values())
    if not re.search(re.escape(label) + r"\s*" + re.escape(token) + r"(?!\d)", section):
        return None
    return parsed


def analyze_race(archive, doc, entry, starts):
    """Cross-check the archived PDF section, current roster and program API.

    VERIFIED means concordant archived first-party evidence, not independently
    audited result truth. Provider historical race identities remain unresolved.
    """
    from .date_overview import timestamp

    mid, number = doc["race"]["meeting_id"], doc["race"]["race_number"]
    member = f"meetings/{mid}/race_{number:02d}.json"
    try:
        program = archive.read(member)
    except KeyError:
        program = None
    blockers = list(entry["blockers"])
    payload = program.get("response", {}) if program else {}
    result = payload.get("result", []) if payload.get("success") is True else []
    candidates = [r for r in result if r.get("raceNumber") == number] if isinstance(result, list) else []
    race_api = candidates[0] if len(candidates) == 1 else {}
    if not race_api:
        blockers.append("PROGRAM_RACE_UNAVAILABLE_OR_AMBIGUOUS")
    if race_api.get("raceKey") != f"{mid}#{number}":
        blockers.append("PROGRAM_RACE_IDENTITY_UNRESOLVED")
    if (race_api.get("distance") != doc["race"].get("distance_m")
            or {"Volt": "Voltestart", "Auto": "Autostart"}.get(race_api.get("startMethod"))
            != doc["race"].get("start_method")):
        blockers.append("PROGRAM_PDF_DISTANCE_OR_START_METHOD_CONFLICT")
    observed = [entry["source"]["latest_observation"]]
    if program:
        observed.append(program["fetched_utc"])
    cutoff = max(timestamp(v) for v in observed)
    if not entry["scheduled_start_utc"] or cutoff >= timestamp(entry["scheduled_start_utc"]):
        blockers.append("DESCRIPTIVE_SOURCE_NOT_PROVEN_PRE_START")
    api_rows = race_api.get("starts", [])
    ids = [str(r.get("horseRegistrationNumber") or "") for r in api_rows]
    numbers = [r.get("startNumber") for r in api_rows]
    if len(numbers) != len(set(numbers)) or len(ids) != len(set(ids)):
        blockers.append("DUPLICATE_PROGRAM_IDENTITIES_OR_NUMBERS")
    if set(numbers) != {h["program_number"] for h in doc["entrants"]}:
        blockers.append("PROGRAM_FIELD_MISMATCH")
    api = {r.get("startNumber"): r for r in api_rows}
    roster = {r["selection_id"]: r for r in entry["runners"]}
    horses = []
    for index, horse in enumerate(doc["entrants"]):
        selection = str(horse["program_number"])
        row = api.get(horse["program_number"], {})
        original = roster[selection]
        pdf_ref = reference(archive, "structured_program_day.json", doc["race"]["source_url"],
                            doc["race"]["captured_at_utc"],
                            f"/races/{entry['source_entry_id'].rsplit(':', 1)[-1]}/entrants/{index}")
        refs = [pdf_ref]
        if program:
            refs.append(reference(archive, member, program["source_url"], program["fetched_utc"],
                                  f"/response/result/{result.index(race_api)}/starts/{api_rows.index(row)}" if row else "/response/result"))
        if starts:
            refs.append(reference(archive, f"meetings/{mid}/starts.json", starts["source_url"],
                                  starts["fetched_utc"], f"/response/result/{number}"))
        registration = str(row.get("horseRegistrationNumber") or "")
        stable = bool(registration and not registration.upper().startswith("TMP"))
        parents = [name_key(re.sub(r"\s*\([^)]*\)\s*$", "", row.get(k) or ""))
                   for k in ("father", "mother")]
        pedigree = re.search(r"\be\s+(.+?)\s+\([^)]*\)\s*-\s*(.+?)\s+\([^)]*\)\s+e\s",
                             horse.get("identity_text") or "")
        pdf_parents = [name_key(v) for v in pedigree.groups()] if pedigree else []
        contradiction = (bool(row) and name_key(row.get("horseName")) != name_key(horse["name"])) or (
            stable and registration != str(original["provider_registration_observed"] or ""))
        parent_match = bool(all(parents) and parents == pdf_parents)
        if all(parents) and pdf_parents and not parent_match:
            contradiction = True
        status = "CONFLICT" if contradiction else (
            "VERIFIED" if stable and parent_match and not blockers else "UNRESOLVED")
        identity = {"status": status, "provider": "RIKSTOTO", "registration_observed": registration or None,
                    "verified_registration": registration if status == "VERIFIED" else None,
                    "proof": "ROSTER_PROGRAM_REGISTRATION_AND_PDF_PARENT_CONCORDANCE",
                    "source_refs": refs}
        facts = {"original_identity": fact("UNVERIFIED_SOURCE", horse.get("identity_text"), [pdf_ref]),
                 "source_name": fact("UNVERIFIED_SOURCE", horse["name"], [pdf_ref])}
        trusted = status == "VERIFIED"
        for key, label in [("total", "Tot:"), ("currentYear", f"{archive.day[:4]}:")]:
            stats = row.get("horseAnnualStatistics", {}).get(key, {})
            values = verified_counts(stats, horse.get("raw_section", ""), label) if trusted else None
            if key == "currentYear" and stats.get("year") != int(archive.day[:4]):
                values = None
            facts[key] = fact("VERIFIED_FACT" if values else "MISSING_DATA", values, refs,
                              None if values else "COUNTS_NOT_CROSS_VERIFIED")
        if (facts["total"]["value"] and facts["currentYear"]["value"]
                and any(facts["currentYear"]["value"][k] > facts["total"]["value"][k]
                        for k in facts["total"]["value"])):
            for key in ("total", "currentYear"):
                facts[key] = fact("MISSING_DATA", None, refs, "ANNUAL_CAREER_CONFLICT")
        driver = row.get("driver") if not blockers else None
        driver_ok = trusted and driver and name_key(driver) == name_key(original["driver_startlist"])
        facts["driver_or_rider"] = fact("VERIFIED_FACT" if driver_ok else "UNVERIFIED_SOURCE", driver, refs)
        facts["role"] = fact("UNVERIFIED_SOURCE", "RIDER" if not blockers and race_api.get("isMonte") is True else
                                      "DRIVER" if not blockers and race_api.get("isMonte") is False else None, refs)
        for key in ("postPosition", "extraDistance", "shoes", "sulky"):
            value = row.get(key) if not blockers else None
            facts[key] = fact("UNVERIFIED_SOURCE" if value is not None else "MISSING_DATA",
                              value, refs)
        base, extra = race_api.get("distance"), row.get("extraDistance")
        distance = base + extra if trusted and type(base) is int and type(extra) is int and base > 0 and extra >= 0 else None
        facts["starting_distance_m"] = fact("DERIVED_FEATURE" if distance else "MISSING_DATA", distance, refs,
                                            "PROGRAM_BASE_PLUS_EXTRA_DISTANCE; NOT_A_PERFORMANCE_RATING")
        facts["start_method"] = fact("UNVERIFIED_SOURCE" if not blockers else "MISSING_DATA",
                                     race_api.get("startMethod") if not blockers else None, refs)
        history = []
        seen = Counter(h.get("date") for h in horse.get("past_starts", []))
        for prior in horse.get("past_starts", []):
            day = prior.get("date")
            valid_date = False
            try:
                valid_date = bool(day and date.fromisoformat(day) < date.fromisoformat(archive.day))
            except ValueError:
                pass
            usable = trusted and valid_date and seen[day] == 1
            history.append({"kind": "UNVERIFIED_SOURCE", "event_date": day,
                            "horse_link": "VERIFIED_SECTION_ATTRIBUTION" if trusted else status,
                            "historical_race_identity": "UNRESOLVED",
                            "source_observed_at": doc["race"]["captured_at_utc"],
                            "historical_published_at": None, "model_eligible": False,
                            "display_eligible": usable,
                            "excluded_reason": None if usable else "IDENTITY_DATE_OR_DUPLICATE_UNRESOLVED",
                            "raw_text": prior.get("raw_text") if usable else None,
                            "source_refs": [pdf_ref],
                            "result_interpretation": "NOT_VALIDATED; ZERO/DG/BR/QUALIFIER_NOT_NUMERIC_PLACINGS",
                            "raw_text_warning": "SOURCE_QUOTATION_MAY_CONTAIN_ODDS_COLUMNS; NEVER_PARSED_AS_FEATURES"})
        dates = [h["event_date"] for h in history if h["display_eligible"]]
        latest = max(dates) if dates else None
        facts["days_since_latest_listed_start"] = fact(
            "DERIVED_FEATURE" if latest else "MISSING_DATA",
            (date.fromisoformat(archive.day) - date.fromisoformat(latest)).days if latest else None,
            [pdf_ref], "EXCERPT_ONLY; NOT_CONFIRMED_LAST_START_OR_INACTIVITY")
        facts["validated_individual_results"] = fact("MISSING_DATA", None, [pdf_ref],
                                                      "HISTORICAL_RACE_ID_AND_RESULT_FASIT_NOT_VERIFIED")
        horses.append({"selection_id": selection, "name": horse["name"], "identity": identity,
                       "facts": facts, "history": history})
    eligible = [h for h in horses if h["facts"]["currentYear"]["kind"] == "VERIFIED_FACT"]
    comparisons = []
    if eligible:
        comparisons.append({"kind": "DERIVED_FEATURE", "comparison": "DOCUMENTED_CURRENT_YEAR_COUNTS",
                            "horses": [{"selection_id": h["selection_id"], "name": h["name"],
                                        **h["facts"]["currentYear"]["value"]} for h in eligible],
                            "interpretation": "Observed starts/wins/places, across unequal conditions and classes; not predicted win chance or ranking.",
                            "source_refs": [ref for h in eligible for ref in h["facts"]["currentYear"]["source_refs"]]})
    return {"scope": "DESCRIPTIVE_FUNDAMENTALS_ONLY", "cutoff": cutoff.isoformat(),
            "source_collection_status": archive.manifest["status"],
            "verified_meaning": "CONCORDANT_ARCHIVED_FIRST_PARTY_EVIDENCE_NOT_INDEPENDENT_RESULT_AUDIT",
            "blockers": sorted(set(blockers)), "horses": horses, "comparisons": comparisons,
            "model_eligible": False, "missing": ["VERIFIED_HISTORICAL_RACE_IDS_AND_RESULT_TRUTH",
                "HISTORICAL_PUBLICATION_TIMES", "PIT_TRAIN_TEST_DATASET", "TIME_BASED_OUT_OF_SAMPLE_EVALUATION",
                "CALIBRATION_AND_BASELINE_COMPARISON", "VALIDATED_FULL_FIELD_MODEL"]}


def render(analysis):
    lines = ["  Fundamentalvisning: beskrivende kildeanalyse; ingen modellrangering."]
    for h in analysis["horses"]:
        facts = h["facts"]
        annual = facts["currentYear"]["value"]
        counts_text = (f"{annual['starts']} starter, {annual['wins']} seire, "
                       f"{annual['seconds']} andre, {annual['thirds']} tredje") if annual else "mangler"
        lines.append(f"    {h['selection_id']} {h['name']} | identitet={h['identity']['status']} | "
                     f"{facts['currentYear']['kind']} år: {counts_text} | "
                     f"{facts['starting_distance_m']['kind']} startdistanse={facts['starting_distance_m']['value']} m; "
                     f"{facts['days_since_latest_listed_start']['kind']} dager siden sist LISTET={facts['days_since_latest_listed_start']['value']}")
        lines.append(f"      {facts['driver_or_rider']['kind']} kusk/rytter: {facts['driver_or_rider']['value']}; "
                     f"UNVERIFIED_SOURCE historikkutdrag={sum(p['display_eligible'] for p in h['history'])}; "
                     "MISSING_DATA verifiserte enkeltresultater. Kildereferanser og utdrag i JSON.")
    if analysis["comparisons"]:
        lines.append("    Sammenligning: dokumenterte årsseire/starter kan sammenholdes; ulik klasse, "
                     "distanse og løpsbetingelser hindrer en slutning om vinnersjanse.")
    return lines
