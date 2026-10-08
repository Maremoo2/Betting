from __future__ import annotations

from dataclasses import dataclass

from .provider_capability import capability


@dataclass(frozen=True)
class EnrichmentCandidate:
    provider: str
    reason: str


def enrichment_candidates(*, country: str, discipline: str) -> tuple[EnrichmentCandidate, ...]:
    """Return read-only providers worth probing for one race.

    Capability is verified at runtime. A provider being listed here never makes a
    race executable; the collector still requires safe identity matching and a
    complete market-free history vector for every active runner.
    """
    country_code = (country or "").upper()
    race_type = (discipline or "").lower()

    candidates: list[EnrichmentCandidate] = []
    if capability("atg", country_code, race_type)["status"] == "VERIFIED":
        candidates.append(
            EnrichmentCandidate(
                provider="atg",
                reason="reviewed_provider_with_runtime_full_field_gate",
            )
        )
    return tuple(candidates)
