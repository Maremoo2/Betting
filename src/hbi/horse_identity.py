"""Permanent horse identity supplied by an independently verified source adapter."""
import re
from dataclasses import dataclass
from datetime import datetime


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
    if any(
        item.observed_at.utcoffset() is None
        or item.observed_at > cutoff
        or not item.original_uri.strip()
        or re.fullmatch(r"[0-9a-f]{64}", item.original_sha256) is None
        or not item.history_original_uri.strip()
        or re.fullmatch(r"[0-9a-f]{64}", item.history_original_sha256) is None
        or item.history_completed_at.utcoffset() is None
        or item.history_completed_at > cutoff
        for item in evidence
    ):
        return None, "IDENTITY_UNRESOLVED"
    if not isinstance(atg, dict) or type(atg.get("horseId")) is not int or any(
        type(item.atg_horse_id) is not int
        or item.atg_horse_id <= 0
        or item.atg_horse_id != atg["horseId"]
        or not item.snapshot_id
        or item.snapshot_id != row.get("snapshot_id")
        for item in evidence
    ):
        return None, "HISTORY_HORSE_IDENTITY_MISMATCH"
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
