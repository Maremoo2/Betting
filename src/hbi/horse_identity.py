"""Permanent horse identity supplied by an independently verified source adapter."""
from dataclasses import dataclass
from datetime import datetime

from .admission_originals import verified_original
from .atg_admission_source import verify_history_original


@dataclass(frozen=True)
class AttestedHorseIdentity:
    """Race entry bound to a registry identity by a verified source adapter."""

    race_id: str
    selection_id: str
    horse_id: str
    source: str
    source_version: str


@dataclass(frozen=True)
class ModelIdentityEvidence:
    """Output of a verified registry adapter linking an exact ATG history snapshot."""

    identity: AttestedHorseIdentity
    observed_at: datetime
    original_uri: str
    original_sha256: str
    atg_horse_id: int
    snapshot_id: str
    history_original_uri: str
    history_original_sha256: str
    history_completed_at: datetime
    original: bytes | None = None
    history_original: bytes | None = None


def resolve_model_identity(
    race_id: str,
    selection_id: str,
    row: dict[str, object],
    atg: object,
    evidence: tuple[ModelIdentityEvidence, ...],
    cutoff: datetime,
) -> tuple[str | None, str | None]:
    """Resolve a race-local runner from independently verified adapter evidence."""
    if not evidence:
        return None, "IDENTITY_UNRESOLVED"
    try:
        identity = identity_fields(race_id, selection_id, tuple(item.identity for item in evidence))
    except ValueError as exc:
        return None, str(exc)
    if len({item.atg_horse_id for item in evidence}) != 1:
        return None, "HORSE_IDENTITY_SOURCE_CONFLICT"
    if not isinstance(atg, dict) or type(atg.get("horseId")) is not int or any(
        type(item.atg_horse_id) is not int
        or item.atg_horse_id <= 0
        or item.atg_horse_id != atg["horseId"]
        or not item.snapshot_id
        or item.snapshot_id != row.get("snapshot_id")
        for item in evidence
    ):
        return None, "HISTORY_HORSE_IDENTITY_MISMATCH"
    for item in evidence:
        registry = verified_original(
            "REGISTRY_BINDING", item.original_uri, item.original_sha256, item.observed_at, item.original, cutoff,
        )
        history = verified_original(
            "ATG_HISTORY", item.history_original_uri, item.history_original_sha256,
            item.history_completed_at, item.history_original, cutoff,
        )
        if registry is None or history is None:
            return None, "IDENTITY_UNRESOLVED"
        game_id = history.get("id")
        if not isinstance(game_id, str) or not game_id.startswith("vinnare_"):
            return None, "HISTORY_ORIGINAL_MISMATCH"
        provider_race_id = game_id.removeprefix("vinnare_")
        if registry != {
            "schema": "VERIFIED_REGISTRY_BINDING_V1",
            "race_id": race_id,
            "selection_id": selection_id,
            "horse_id": item.identity.horse_id,
            "source": item.identity.source,
            "source_version": item.identity.source_version,
            "atg_horse_id": item.atg_horse_id,
            "snapshot_id": item.snapshot_id,
            "history_original_sha256": item.history_original_sha256,
            "atg_race_id": provider_race_id,
        }:
            return None, "REGISTRY_BINDING_MISMATCH"
        if item.history_original_uri != row.get("source_uri"):
            return None, "HISTORY_ORIGINAL_MISMATCH"
        try:
            facts = verify_history_original(
                item.history_original, uri=item.history_original_uri, sha256=item.history_original_sha256,
                completed_at=item.history_completed_at, cutoff=cutoff, provider_race_id=provider_race_id,
            )
            actual = facts.get(int(selection_id))
        except (ValueError, TypeError):
            return None, "HISTORY_ORIGINAL_MISMATCH"
        if actual != (item.atg_horse_id, atg.get("lifeStarts"), atg.get("lifeWins")):
            return None, "HISTORY_ORIGINAL_MISMATCH"
    return identity["horse_id"], None


def identity_fields(
    race_id: str,
    selection_id: str,
    attestations: tuple[AttestedHorseIdentity, ...] = (),
) -> dict[str, str | None]:
    """Accept only verified attestations, never raw/provisional provider matches."""
    if not attestations:
        return {
            "horse_id": None,
            "horse_id_source": None,
            "horse_id_source_version": None,
            "horse_identity_status": "UNATTESTED",
            "horse_identity_reason": "PERMANENT_HORSE_ID_UNATTESTED",
        }
    for attestation in attestations:
        if (attestation.race_id, attestation.selection_id) != (race_id, selection_id):
            raise ValueError("HORSE_IDENTITY_RACE_OR_SELECTION_MISMATCH")
        if not all(value and value == value.strip() for value in (
            attestation.horse_id, attestation.source, attestation.source_version,
        )):
            raise ValueError("HORSE_IDENTITY_ATTESTATION_INCOMPLETE")
    if len({item.horse_id for item in attestations}) != 1:
        raise ValueError("HORSE_IDENTITY_SOURCE_CONFLICT")
    first = attestations[0]
    return {
        "horse_id": first.horse_id,
        "horse_id_source": first.source,
        "horse_id_source_version": first.source_version,
        "horse_identity_status": "ATTESTED",
        "horse_identity_reason": None,
    }
