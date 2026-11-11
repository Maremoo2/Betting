"""Permanent horse identity supplied by an independently verified source adapter."""
from dataclasses import dataclass


@dataclass(frozen=True)
class AttestedHorseIdentity:
    """Race entry bound to a registry identity by a verified source adapter."""

    race_id: str
    selection_id: str
    horse_id: str
    source: str
    source_version: str


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
