"""Research semantic adapter for existing collector past_start records.

The companion collector retains sole ownership of PDF race/horse/line parsing.
This module never discovers PDF headers or horse blocks and never joins identity.
"""
from __future__ import annotations

import re
from copy import deepcopy
from datetime import date

SCHEMA = "HBI_SEMANTIC_HISTORY_V1"
VERSION = "0.1.0"
FIELDS = ("historical_date", "historical_race_number", "historical_track", "track_identity",
    "distance_m", "start_method", "placing", "km_time", "gallop_flag", "disqualification_flag", "qualification_flag")
HEADER = re.compile(r"^(.+?)\s+(\d{2}\.\d{2}\.\d{2})-(\d{1,2})\|")
DECIMAL = re.compile(r"(\d{1,2}),(\d)(a?g?|ga?)$")


def fact(value="UNKNOWN", status="NOT_EXTRACTED", raw="", basis=""):
    return {"value": value, "status": status, "raw": raw, "basis": basis}


def normalize_prior(prior, *, target_date, provenance, codebook):
    """Add semantics without overwriting the upstream parser's original values."""
    if codebook["schema"] != "M7B1_HISTORY_CODEBOOK_V1" or codebook["version"] != VERSION:
        raise ValueError("UNSUPPORTED_HISTORY_CODEBOOK")
    raw = prior.get("raw_text", "")
    fields = {key: fact(raw=raw) for key in FIELDS}
    result = {"schema": SCHEMA, "parser_version": VERSION, "normalization_version": codebook["version"],
        "raw_text": raw, "upstream": deepcopy(prior), "source": deepcopy(provenance), "fields": fields,
        "raw_codes": {}, "result_status": "NOT_EXTRACTED", "historical_identity_status": "UNRESOLVED",
        "official_result_verification": "NOT_PERFORMED_BY_ADAPTER", "pit_status": "UNVERIFIED",
        "allowed_use": "RESEARCH_ONLY", "model_eligible": False, "history_accepted": False,
        "exclusion_reasons": ["HISTORY_FEATURE_CONTRACT_NOT_VALIDATED", "HISTORICAL_IDENTITY_UNRESOLVED", "PIT_UNVERIFIED"]}
    try:
        event = date.fromisoformat(prior["date"])
        target = date.fromisoformat(target_date)
    except (ValueError, KeyError, TypeError):
        result["exclusion_reasons"].append("INVALID_UPSTREAM_HISTORY_DATE")
        return result
    fields["historical_date"] = fact(prior["date"], "EXTRACTED", basis="EXISTING_COLLECTOR_DATE")
    if type(prior.get("race_number")) is not int or prior["race_number"] < 1:
        result["exclusion_reasons"].append("INVALID_UPSTREAM_HISTORY_RACE_NUMBER")
        return result
    fields["historical_race_number"] = fact(prior["race_number"], "EXTRACTED", basis="EXISTING_COLLECTOR_RACE_NUMBER")
    if event >= target:
        result["exclusion_reasons"].append("FUTURE_OR_SAME_DAY_HISTORY_REJECTED")
        result["result_status"] = "REJECTED_TEMPORAL"
        return result
    header = HEADER.match(raw)
    if (not header or header[2] != event.strftime("%d.%m.%y") or int(header[3]) != prior["race_number"]):
        result["exclusion_reasons"].append("UPSTREAM_RAW_LINE_DATE_OR_RACE_CONFLICT")
        return result
    track = header[1].split()[-1]
    fields["historical_track"] = fact(track, "EXTRACTED", track, "LITERAL_PRINTED_TRACK_CODE_NOT_PHYSICAL_IDENTITY")
    registry = codebook["track_register"].get(track)
    if registry and registry["status"] == "EXTRACTED" and len(registry["candidates"]) == 1:
        fields["track_identity"] = fact(registry["candidates"][0], "EXTRACTED", track, registry["source"])
    else:
        fields["track_identity"] = {**fact(status="AMBIGUOUS" if registry else "UNKNOWN_CODE", raw=track,
            basis="NO_TARGET_COUNTRY_GUESS"), "candidates": registry["candidates"] if registry else []}
        result["exclusion_reasons"].append("HISTORICAL_TRACK_IDENTITY_UNRESOLVED")
    tokens = raw[header.end():].split()
    candidates = []
    # Evaluate only the upstream history table prefix. Market/prize columns and
    # narrative numbers never participate in structural inference.
    for i in range(2, min(5, len(tokens) - 1)):
        posts, placing, distance = tokens[:i - 1], tokens[i - 1], tokens[i]
        if (1 <= len(posts) <= 2 and all(re.fullmatch(r"\d{1,4}", p) for p in posts)
                and re.fullmatch(r"\d{1,2}|d|k|-", placing) and re.fullmatch(r"\d{3,4}", distance)
                and 300 <= int(distance) <= 9999 and not tokens[i + 1].isdigit()):
            candidates.append((i, placing, int(distance)))
    if len(candidates) != 1:
        result["exclusion_reasons"].append("AMBIGUOUS_OR_UNSUPPORTED_HISTORY_COLUMNS")
        result["result_status"] = "AMBIGUOUS"
        return result
    i, placing, distance = candidates[0]
    time = tokens[i + 1]
    suffix = tokens[i + 2] if len(tokens) > i + 2 and tokens[i + 2] in ("a", "g", "ag", "ga") else ""
    fields["distance_m"] = fact(distance, "EXTRACTED", str(distance), "HISTORICAL_STARTER_DISTANCE_CELL")
    result["raw_codes"] = {"placing": placing, "km_time": time, "separate_suffix": suffix}
    result["history_accepted"] = True  # Syntax and historical date only, not PIT/model approval.
    fields["start_method"] = fact(status="AMBIGUOUS", raw=time + " " + suffix, basis="ABSENCE_OF_A_DOES_NOT_PROVE_VOLT")
    for key in ("gallop_flag", "disqualification_flag", "qualification_flag"):
        fields[key] = fact("NOT_REPORTED", "NOT_REPORTED", basis="ABSENCE_IS_NOT_FALSE")
    if placing.isdigit() and int(placing) > 0:
        fields["placing"] = fact(int(placing), "EXTRACTED", placing, "POSITIVE_PLACING_CELL")
        result["result_status"] = "PLACED"
    elif placing == "0":
        fields["placing"] = fact("UNPLACED", "EXTRACTED", placing, "ZERO_IS_CATEGORY_NOT_RANK_OR_DQ")
        result["result_status"] = "UNPLACED"
    elif placing == "k" and len(tokens) > i + 2 and tokens[i + 2] == "gdk":
        fields["placing"] = fact("NOT_APPLICABLE", "EXTRACTED", placing, "QUALIFIER_NOT_COMPETITIVE_PLACING")
        fields["qualification_flag"] = fact(True, "EXTRACTED", "k gdk", "CONTEXTUAL_QUALIFICATION_AND_APPROVAL")
        result["result_status"] = "QUALIFICATION_APPROVED"
    else:
        fields["placing"] = fact(status="UNKNOWN_CODE", raw=placing, basis="NO_CROSS_COUNTRY_RESULT_GUESS")
        fields["disqualification_flag"] = fact(status="UNKNOWN_CODE", raw=placing)
        result["result_status"] = "UNKNOWN_CODE"
    numeric = DECIMAL.fullmatch(time)
    if numeric and int(numeric[1]) > 0:
        fields["km_time"] = fact(60 + int(numeric[1]) + int(numeric[2]) / 10, "EXTRACTED", time, "EXPLICIT_DECIMAL_SECONDS_PER_KM")
    elif time == "it":
        fields["km_time"] = fact("NOT_REPORTED", "NOT_REPORTED", time, "PRIMARY_INDEX_NO_TIMING")
    else:
        fields["km_time"] = fact(status="UNKNOWN_CODE", raw=time, basis="NON_DECIMAL_CODE_IS_NOT_NUMERIC_TIME")
    known_suffix = (numeric[3] if numeric else "") + suffix
    if "a" in known_suffix:
        fields["start_method"] = fact("AUTO", "EXTRACTED", time + " " + suffix, "EXPLICIT_A_MARKER_ONLY")
    # Documented g marker is separate from uncertain full result/time codes.
    # Narrative use is restricted to explicit own-event phrases; 'leder g' etc
    # does not turn another horse's gallop into this horse's feature.
    own_gallop = bool(re.search(r"\b(?:Startgal(?:opp)?|startgal(?:opp)?|[Ss]g,|[Gg]al e\b|ny gal\b|gal \d+ kv\b|g fra start\b)", raw))
    digit_g = bool(re.fullmatch(r"\d+g", time))
    if "g" in known_suffix or digit_g or own_gallop:
        fields["gallop_flag"] = fact(True, "EXTRACTED", time + " " + suffix, "EXPLICIT_G_MARKER_OR_OWN_GALLOP_NARRATIVE")
    if re.search(r"\b(?:Startgal|Sg), diskad\.", raw):
        fields["disqualification_flag"] = fact(True, "EXTRACTED", "diskad", "EXPLICIT_OWN_DISQUALIFICATION_NARRATIVE")
        result["result_status"] = "DISQUALIFIED"
    if time == "frd8a":
        fields["start_method"] = fact(status="UNKNOWN_CODE", raw=time, basis="COMPOUND_NOT_DECOMPOSED_BY_ASSUMPTION")
        if fields["gallop_flag"]["status"] != "EXTRACTED":
            fields["gallop_flag"] = fact(status="UNKNOWN_CODE", raw=time)
    return result
