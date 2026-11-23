"""Unchanged literal result decoding reused from HIST_FORM_001; no new parser.

Source core SHA-256 is pinned in the P1-015 artifact manifest. Unknowns stay unknown.
"""
import re

CODE_PROFILE = "RIKSTOTO_MINIMAL_LITERAL_CODES_V1_NOT_FULL_OFFICIAL_CODEBOOK"

def native(value):
    return bool(isinstance(value, str) and value and not value.upper().startswith("TMP")
                and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*", value))

def result_code(row, scratched):
    """Preserve place/order and literal codes; zero place never invents DQ/gallop."""
    raw = row.get("kmTime")
    raw = raw.strip() if isinstance(raw, str) else ""
    compact = re.sub(r"\s+", "", raw.lower())
    pos = row.get("place")
    reasons = []
    if type(pos) is not int or pos < 0:
        reasons.append("INVALID_FINISH_POSITION")
    seconds = None
    number = re.fullmatch(r"(\d+)[,.](\d+)([av]?)(g?)", compact)
    status, gallop, dq = "UNKNOWN", None, None
    if scratched:
        status = "SCRATCHED"
        if type(pos) is int and pos > 0:
            reasons.append("SCRATCHED_WITH_POSITIVE_FINISH")
    elif number:
        minute_seconds = float(number[1] + "." + number[2])
        if 0 < minute_seconds < 60:
            seconds = 60 + minute_seconds
        else:
            reasons.append("INVALID_KM_TIME")
        if number[4] == "g":
            status, gallop = "GALLOP_SOURCE_CODE_G", True
        else:
            status = "PLACED" if type(pos) is int and pos > 0 else "UNORDERED_RESULT"
    elif re.fullmatch(r"dg[av]?", compact):
        status, gallop, dq = "DISQUALIFIED_SOURCE_CODE_DG", True, True
        if type(pos) is int and pos > 0:
            reasons.append("DQ_WITH_POSITIVE_FINISH")
    elif re.fullmatch(r"br(?:[av]?g?)?", compact):
        status = "DID_NOT_FINISH_SOURCE_CODE_BR"
    elif re.fullmatch(r"dist(?:[av]?g?)?", compact):
        status = "DISTANCED_SOURCE_CODE_DIST"
    elif not compact:
        status = "PLACED" if type(pos) is int and pos > 0 else "UNORDERED_RESULT"
    else:
        status = "UNKNOWN_RESULT_CODE"
        reasons.append("UNSUPPORTED_RESULT_CODE")
    # No missing code or unplaced rank becomes false/zero status.
    return {"finish_position": pos if type(pos) is int and pos > 0 else None,
            "finish_position_raw": row.get("place"), "finish_order_raw": row.get("order"),
            "race_time": {"value": seconds, "unit": "SECONDS_PER_KM", "raw": raw or None},
            "result_status": status, "gallop_status": gallop, "disqualified": dq,
            "result_code_profile": CODE_PROFILE, "code_exclusions": reasons}
