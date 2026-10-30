"""Read-only official result fetch audit for one paper Shadow ticket.

Never writes HBI SQLite, never calls settle_open_shadow_tickets, never records P&L
and never promotes any model or betting authority.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

from hbi.settlement_source_review import assess_winner_settlement


def fetch_summary(result):
    """Retain only non-sensitive HTTP provenance metadata, no raw result body."""
    uri = getattr(result, "url", None)
    parsed = urlparse(uri) if isinstance(uri, str) else None
    return {
        "source_uri": uri if parsed and parsed.scheme == "https"
        and parsed.hostname == "www.rikstoto.no" else None,
        "https_official_origin": bool(parsed and parsed.scheme == "https"
                                      and parsed.hostname == "www.rikstoto.no"),
        "http_success": getattr(result, "success", None) is True,
        "http_status": getattr(result, "status_code", None),
        "response_sha256": getattr(result, "response_body_sha256", None),
        "response_completed_at_utc": (
            result.response_completed_at.isoformat()
            if getattr(result, "response_completed_at", None) else None
        ),
        "source_http_date": getattr(result, "http_date", None),
        "source_http_etag": getattr(result, "http_etag", None),
        "error_type": (
            str(getattr(result, "error", "") or "").split(":")[0][:80]
            if getattr(result, "error", None) else None
        ),
    }


def participant_evidence(complete, raceday, race_number, selected):
    """Selected public result's scalar contract fields, not the raw body."""
    result = {
        "selected_row_count": 0, "place": None, "km_time": None,
        "odds": None, "scratched": None, "result_status": None,
        "winner_selection": None, "winner_dividend_status": None,
        "winner_dividend_odds": None,
    }
    rows = complete.get("results") if isinstance(complete, dict) else None
    if not isinstance(rows, list):
        return result
    chosen = [r for r in rows if isinstance(r, dict)
              and str(r.get("startNumber")) == selected]
    result["selected_row_count"] = len(chosen)
    if len(chosen) == 1:
        row = chosen[0]
        result.update({
            "place": row.get("place") if type(row.get("place")) is int else None,
            "km_time": str(row["kmTime"])[:60]
            if row.get("kmTime") is not None else None,
            "odds": row.get("odds") if type(row.get("odds")) in (int, float) else None,
            "scratched": row.get("scratched") if type(row.get("scratched")) is bool
            else None,
            "result_status": str(row["status"])[:60]
            if row.get("status") is not None else None,
        })
    winners = [str(r.get("startNumber")) for r in rows
               if isinstance(r, dict) and r.get("place") == 1]
    if len(winners) != 1:
        return result
    result["winner_selection"] = winners[0]
    try:
        div = raceday["finalOdds"]["winOdds"][str(race_number)][winners[0]]
        result["winner_dividend_status"] = div.get("payoutStatus")
        result["winner_dividend_odds"] = div.get("odds")
    except (KeyError, TypeError, AttributeError):
        pass
    return result


def race_result_status_distribution(complete):
    """Aggregate only anonymous original result-code shapes for review.

    No individual runner names or additional ticket selections are exposed.
    The code distribution is *descriptive*, never a payout rule.
    """
    rows = complete.get("results") if isinstance(complete, dict) else None
    if not isinstance(rows, list):
        return {"parseable": False, "rows": 0, "place_zero": 0,
                "zero_km_time_categories": {}, "payout_authority": False}
    counts = {"Dsk": 0, "ZERO_TIME": 0, "OTHER_TIME": 0, "MISSING_TIME": 0}
    zeros = 0
    for item in rows:
        if not isinstance(item, dict):
            continue
        if type(item.get("place")) is not int or item["place"] != 0:
            continue
        zeros += 1
        value = item.get("kmTime")
        if value == "Dsk":
            counts["Dsk"] += 1
        elif value == "0,0":
            counts["ZERO_TIME"] += 1
        elif value is None:
            counts["MISSING_TIME"] += 1
        else:
            counts["OTHER_TIME"] += 1
    return {
        "parseable": True,
        "rows": len(rows),
        "place_zero": zeros,
        "zero_km_time_categories": counts,
        "payout_authority": False,
    }


def original_start_and_scratch_evidence(client, day_key, race_no, selection):
    """Only explicit per-race starts/scratches, not a guess from place=0."""
    starts = client.starts(day_key)
    scratches = client.scratched(day_key)
    start_meta = fetch_summary(starts)
    scratch_meta = fetch_summary(scratches)
    start_items = None
    scratch_items = None
    if starts.success:
        payload = client.result_object(starts)
        if isinstance(payload, dict):
            start_items = payload.get(str(race_no))
    if scratches.success:
        payload = client.result_object(scratches)
        if isinstance(payload, dict):
            scratch_items = payload.get(str(race_no))
    found = []
    if isinstance(start_items, list):
        found = [r for r in start_items if isinstance(r, dict)
                 and str(r.get("startNumber")) == selection]
    scratch_markers = []
    all_scratch_rows_recognized = isinstance(scratch_items, list)
    if isinstance(scratch_items, list):
        for entry in scratch_items:
            if isinstance(entry, dict) and entry.get("startNumber") is not None:
                scratch_markers.append(str(entry["startNumber"]))
            elif type(entry) is int:
                scratch_markers.append(str(entry))
            else:
                all_scratch_rows_recognized = False
    explicit = (
        found[0].get("isScratched")
        if len(found) == 1 and type(found[0].get("isScratched")) is bool else None
    )
    return {
        "starts_get": start_meta, "scratches_get": scratch_meta,
        "selected_in_startlist_rows": len(found),
        "selected_is_scratched_in_startlist": explicit,
        "scratched_list_shape_recognized": all_scratch_rows_recognized,
        "selected_on_scratched_list": (
            selection in scratch_markers if all_scratch_rows_recognized else None
        ),
        "race_startlist_row_count": (
            len(start_items) if isinstance(start_items, list) else None
        ),
        "start_participation_certified": False,
        "bookkeeping_authority": False,
    }


def probe(*, client, raceday_key, race_number, selected, cached_winner=None,
          corroborate_starts=False):
    if not isinstance(raceday_key, str) or not raceday_key.startswith("S4_NR_"):
        raise ValueError("Only explicit S4_NR_ raceday source investigation allowed")
    if type(race_number) is not int or race_number < 1:
        raise ValueError("Race number must be positive integer")
    if not isinstance(selected, str) or not selected.isdigit():
        raise ValueError("Selected runner number must be digits")
    # Both are explicitly documented GET-only provider endpoints.
    raceday = client.raceday_results(raceday_key)
    complete = client.complete_results(raceday_key, race_number)
    day_meta = fetch_summary(raceday)
    complete_meta = fetch_summary(complete)
    official = bool(
        day_meta["https_official_origin"] and complete_meta["https_official_origin"]
        and day_meta["http_success"] and complete_meta["http_success"]
        and day_meta["response_sha256"] and complete_meta["response_sha256"]
        and day_meta["http_status"] == 200 and complete_meta["http_status"] == 200
    )
    ticket = {
        "ticket_id": "SOURCE_PROBE_ONLY_NOT_A_PAPER_SETTLEMENT",
        "product": "V", "status": "SHADOW_BET",
        "selections_json": json.dumps([selected]),
        "provider_raceday_key": raceday_key, "race_number": race_number,
    }
    complete_payload = client.result_object(complete) if complete.success else None
    day_payload = client.result_object(raceday) if raceday.success else None
    details = participant_evidence(complete_payload, day_payload, race_number, selected)
    review = assess_winner_settlement(
        ticket=ticket,
        complete=complete_payload,
        raceday=day_payload,
        cached_winner=cached_winner,
        source_attested=official,
    )
    start_corroboration = (
        original_start_and_scratch_evidence(
            client, raceday_key, race_number, selected
        ) if corroborate_starts else None
    )
    return {
        "schema": "HBI_OFFICIAL_RESULT_READONLY_PROBE_V1",
        "scope": "ONE_PAPER_RACE_SOURCE_EVIDENCE_NO_SETTLEMENT",
        "raceday_key": raceday_key,
        "race_number": race_number,
        "selected": selected,
        "raceday_results": day_meta,
        "complete_results": complete_meta,
        "both_official_http_payloads_observed": official,
        "structurally_settlement_ready": review["structurally_settlement_ready"],
        "structural_reasons": review["reasons"],
        "winning_result": review["winning_result"],
        "public_selected_participant_fields": details,
        "anonymous_result_code_distribution": race_result_status_distribution(complete_payload),
        "official_start_and_scratch_corroboration": start_corroboration,
        "bookkeeping_authority": False,
        "p0_status": "BLOCKED_PENDING_INDEPENDENT_ADJUDICATION",
        "real_money_authority": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raceday-key", required=True)
    parser.add_argument("--race-number", type=int, required=True)
    parser.add_argument("--selection", required=True)
    parser.add_argument("--cached-winner")
    parser.add_argument("--probe-start-status", action="store_true",
                        help="Also perform two GETs for official starts/scratches")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--execute-public-get", action="store_true",
        help="Explicit authorization for two public HTTP GETs; no account access",
    )
    args = parser.parse_args()
    if not args.execute_public_get:
        parser.error("Explicit --execute-public-get required; no silent network access")
    from hbi.providers.rikstoto import RikstotoClient

    report = probe(
        client=RikstotoClient(timeout=12.0),
        raceday_key=args.raceday_key,
        race_number=args.race_number,
        selected=args.selection,
        cached_winner=args.cached_winner,
        corroborate_starts=args.probe_start_status,
    )
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "raceday_results_http": report["raceday_results"]["http_status"],
        "complete_results_http": report["complete_results"]["http_status"],
        "both_official_http_payloads_observed": report["both_official_http_payloads_observed"],
        "structural_reasons": report["structural_reasons"],
        "p0_status": report["p0_status"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
