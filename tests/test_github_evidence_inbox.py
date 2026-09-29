import json

from hbi.github_evidence_inbox import ENVELOPE, parse_bridge_comment


def _row():
    return {
        "inbox_id": "x1",
        "observed_at_utc": "2026-09-29T17:00:00+00:00",
        "provider": "rikstoto",
        "provider_raceday_key": "VI_NR_2026-09-29",
        "race_number": 4,
        "selection_id": "1",
        "event_type": "TRAINER_COMMENT",
        "claim_text": "Verified comment.",
        "source_uri": "https://example.test/source",
        "source_type": "TRAINER_INTERVIEW",
        "source_timestamp_utc": "2026-09-29T16:55:00+00:00",
        "source_time_basis": "PUBLISHED",
        "confidence": 0.9,
        "materiality": "MEDIUM",
        "evidence_status": "VERIFIED",
        "policy_version": "V3.2-PW-1",
        "extractor": "chatgpt-prewatch",
    }


def test_parse_single_bridge_comment():
    row = _row()
    body = ENVELOPE + "\n" + json.dumps(row)
    assert parse_bridge_comment(body) == [row]


def test_parse_bridge_comment_json_array():
    rows = [_row(), {**_row(), "inbox_id": "x2"}]
    body = ENVELOPE + "\n" + json.dumps(rows)
    assert parse_bridge_comment(body) == rows


def test_parse_bridge_comment_ignores_other_comments():
    assert parse_bridge_comment("human discussion") == []


def test_parse_bridge_comment_accepts_fenced_json():
    row = _row()
    body = ENVELOPE + "\n```json\n" + json.dumps(row) + "\n```"
    assert parse_bridge_comment(body) == [row]


def test_parse_bridge_comment_ignores_invalid_json():
    assert parse_bridge_comment(ENVELOPE + "\n{broken") == []
