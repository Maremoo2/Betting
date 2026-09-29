from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EnrichmentCandidate:
    provider: str
    reason: str


def enrichment_candidates(
    *,
    country: str,
    discipline: str,
) -> tuple[EnrichmentCandidate, ...]:
    """Return read-only providers worth probing for one race.

    Provider order is only a probing priority. A candidate never makes a race
    executable by itself: one provider must safely match and completely enrich every
    active runner before its data is exposed to the model.
    """
    country_code = (country or "").upper()
    race_type = (discipline or "").lower()
    if not country_code or race_type not in {"trot", "gallop"}:
        return ()

    atg = EnrichmentCandidate(
        provider="atg",
        reason="public_racing_info_runtime_capability_probe",
    )
    pmu = EnrichmentCandidate(
        provider="pmu",
        reason="public_turfinfo_runtime_capability_probe",
    )

    if country_code == "FR":
        return (pmu, atg)
    if country_code in {"SE", "DK"}:
        return (atg, pmu)
    return (atg, pmu)
