"""Read-only inspection of original ATG game bytes for admission review."""

import hashlib
import json
from datetime import datetime

from .provider_capability import validate_lifetime
from .providers.atg import AtgClient


def verify_history_original(
    original: bytes,
    *,
    uri: str,
    sha256: str,
    completed_at: datetime,
    cutoff: datetime,
    provider_race_id: str,
) -> dict[int, tuple[int, int, int]]:
    """Extract verified ATG-local facts without granting registry or race attestation."""
    if uri != f"{AtgClient.GAME_API}/vinnare_{provider_race_id}":
        raise ValueError("ATG_HISTORY_SOURCE_MISMATCH")
    if hashlib.sha256(original).hexdigest() != sha256:
        raise ValueError("ATG_HISTORY_ORIGINAL_HASH_MISMATCH")
    if completed_at.utcoffset() is None or cutoff.utcoffset() is None or completed_at >= cutoff:
        raise ValueError("ATG_HISTORY_NOT_BEFORE_CUTOFF")
    game = json.loads(original)
    if not isinstance(game, dict) or game.get("id") != f"vinnare_{provider_race_id}":
        raise ValueError("ATG_HISTORY_GAME_MISMATCH")
    races = game.get("races")
    if not isinstance(races, list) or len(races) != 1 or not isinstance(races[0], dict):
        raise ValueError("ATG_HISTORY_RACE_MISMATCH")
    race = races[0]
    start = AtgClient._parse_time(race.get("startTime"))
    if race.get("id") != provider_race_id or race.get("sport") != "trot":
        raise ValueError("ATG_HISTORY_RACE_MISMATCH")
    if race.get("status") != "upcoming" or start is None or completed_at >= start or cutoff > start:
        raise ValueError("ATG_HISTORY_NOT_PRE_RACE")
    entries = race.get("starts")
    if not isinstance(entries, list) or not entries:
        raise ValueError("ATG_HISTORY_FIELD_MISSING")
    facts = {}
    numbers = set()
    horse_ids = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise TypeError("ATG_HISTORY_FIELD_INVALID")
        number = entry.get("number")
        if type(number) is not int or number < 1 or number in numbers:
            raise ValueError("ATG_HISTORY_FIELD_INVALID")
        numbers.add(number)
        scratched = entry.get("scratched", False)
        if type(scratched) is not bool:
            raise ValueError("ATG_HISTORY_FIELD_INVALID")
        if scratched:
            continue
        horse = entry.get("horse")
        horse_id = horse.get("id") if isinstance(horse, dict) else None
        if type(horse_id) is not int or horse_id < 1 or horse_id in horse_ids:
            raise ValueError("ATG_HISTORY_HORSE_ID_INVALID")
        horse_ids.add(horse_id)
        if validate_lifetime(horse) is not None:
            raise ValueError("ATG_HISTORY_LIFETIME_INVALID")
        life = horse["statistics"]["life"]
        facts[number] = (horse_id, life["starts"], life["placement"]["1"])
    if not facts:
        raise ValueError("ATG_HISTORY_FIELD_MISSING")
    return facts
