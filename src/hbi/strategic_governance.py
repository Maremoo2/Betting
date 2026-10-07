from __future__ import annotations

from dataclasses import asdict, dataclass
from collections.abc import Mapping, Sequence

STRATEGIC_FOCUS_SCHEMA_VERSION = "HBI_STRATEGIC_FOCUS_V1"

_P0_ORDER = (
    "temporal_integrity",
    "provider_integrity",
    "runtime_replay_parity",
    "settlement_integrity",
)
_SEVERITY = {"FAIL": 0, "WARN": 1, "NO_EVIDENCE": 2, "PASS": 3}


@dataclass(frozen=True)
class StrategicFocus:
    schema_version: str
    diagnosis: str
    guiding_policy: str
    selected_chain_link: str
    proximate_objective: str
    coherent_actions: tuple[str, ...]
    defer: tuple[str, ...]
    empirical_test: tuple[str, ...]
    re_diagnose_when: str
    execution_authority: bool = False

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _integrity_focus(gate: str, status: str) -> StrategicFocus:
    labels = {
        "temporal_integrity": (
            "point-in-time integrity",
            "Restore point-in-time correctness before interpreting any model result.",
            (
                "locate every temporal-integrity failure",
                "repair provenance/timestamp logic",
                "re-run mutation and stored-row checks",
            ),
            (
                "temporal integrity is PASS",
                "future-mutation invariance remains PASS",
            ),
        ),
        "provider_integrity": (
            "provider/data integrity",
            "Restore complete, source-grounded provider evidence before increasing model complexity.",
            (
                "identify failing provider/race contracts",
                "preserve full-field fail-closed behavior",
                "verify repaired collection prospectively",
            ),
            (
                "provider integrity is PASS",
                "no repaired race relies on fabricated or post-race data",
            ),
        ),
        "runtime_replay_parity": (
            "runtime replay parity",
            "Make frozen decisions reproducible before trusting retrospective evaluation.",
            (
                "isolate replay mismatches",
                "align runtime and replay code paths",
                "replay the affected frozen decisions",
            ),
            (
                "runtime replay parity is PASS",
                "frozen decisions reproduce probabilities and decision status",
            ),
        ),
        "settlement_integrity": (
            "settlement integrity",
            "Repair official-outcome and shadow-settlement reconciliation before using P/L or CLV as evidence.",
            (
                "identify overdue or contradictory settlements",
                "repair settlement semantics without rewriting frozen decisions",
                "reconcile the backlog and rerun integrity",
            ),
            (
                "settlement integrity is PASS",
                "no overdue contradictory shadow ticket remains",
            ),
        ),
    }
    label, policy, actions, tests = labels[gate]
    return StrategicFocus(
        schema_version=STRATEGIC_FOCUS_SCHEMA_VERSION,
        diagnosis=(
            f"The weakest critical chain link is {label}: current status is {status}."
        ),
        guiding_policy=policy,
        selected_chain_link=gate,
        proximate_objective=(
            f"Move {gate} from {status} to PASS without changing the frozen betting strategy."
        ),
        coherent_actions=actions,
        defer=(
            "new Champion weights or probability formula",
            "new bet products",
            "staking/Kelly production rules",
            "real-money execution",
        ),
        empirical_test=tests,
        re_diagnose_when=(
            f"Re-run the strategy diagnosis after {gate} reaches PASS or new harder evidence appears."
        ),
    )


def build_strategic_focus(
    *,
    p0_statuses: Mapping[str, str],
    evaluated_rows: int,
    challenger_clocks: Sequence[Mapping[str, object]] = (),
) -> StrategicFocus:
    """Select one evidence-driven proximate objective for the current HBI state.

    This is a governance aid, not a betting model. It cannot alter probabilities,
    thresholds, Champion identity, staking, or execution authority.
    """
    problems = []
    for order, gate in enumerate(_P0_ORDER):
        status = str(p0_statuses.get(gate, "NO_EVIDENCE"))
        if status != "PASS":
            problems.append((_SEVERITY.get(status, -1), order, gate, status))
    if problems:
        _, _, gate, status = min(problems)
        return _integrity_focus(gate, status)

    if evaluated_rows < 100:
        return StrategicFocus(
            schema_version=STRATEGIC_FOCUS_SCHEMA_VERSION,
            diagnosis=(
                f"Integrity gates pass, but only {evaluated_rows} frozen races have outcome "
                "evaluation; the limiting factor is prospective evidence, not model complexity."
            ),
            guiding_policy=(
                "Keep the Champion frozen and improve reliable race/data capture while "
                "accumulating a clean, chronological paired sample."
            ),
            selected_chain_link="prospective_evidence",
            proximate_objective=(
                "Reach the first 100 clean paired evaluations with stable provenance and no "
                "P0 regression."
            ),
            coherent_actions=(
                "keep collecting frozen full-field decisions and official outcomes",
                "reduce documented coverage/timing/settlement gaps without weakening fail-closed gates",
                "report Champion, market and combined metrics on the same races",
            ),
            defer=(
                "Challenger promotion claims",
                "new Champion weights or probability formula",
                "bet-product expansion",
                "real-money execution",
            ),
            empirical_test=(
                "at least 100 clean paired evaluations exist",
                "all P0 integrity gates remain PASS",
                "the cohort is reproducible and point-in-time valid",
            ),
            re_diagnose_when=(
                "Re-diagnose at 100 paired evaluations or immediately after any P0 regression."
            ),
        )

    active = [
        clock
        for clock in challenger_clocks
        if str(clock.get("status")) in {"COLLECTING", "FORWARD_TESTING"}
    ]
    incomplete = [
        clock
        for clock in active
        if int(clock.get("eligible_races") or clock.get("forward_n") or 0)
        < int(clock.get("minimum_races") or clock.get("minimum_n") or 500)
    ]
    if incomplete:
        return StrategicFocus(
            schema_version=STRATEGIC_FOCUS_SCHEMA_VERSION,
            diagnosis=(
                "A registered Challenger is already in forward testing; its untouched evidence "
                "clock is the binding research constraint."
            ),
            guiding_policy=(
                "Do not redesign the Challenger on its evaluation sample; accumulate its "
                "preregistered forward evidence and preserve the Champion."
            ),
            selected_chain_link="challenger_forward_evidence",
            proximate_objective=(
                "Complete the registered Challenger's untouched forward sample without "
                "contaminating its discovery cutoff."
            ),
            coherent_actions=(
                "continue eligible forward-event collection",
                "compare Challenger, Champion and market on identical races",
                "monitor calibration and preregistered slices without adaptive switching",
            ),
            defer=(
                "mid-sample Challenger redesign",
                "automatic promotion",
                "production staking changes",
                "real-money execution",
            ),
            empirical_test=(
                "the Challenger reaches its preregistered minimum forward sample",
                "P0 integrity remains PASS",
                "promotion metrics are computed only on untouched forward races",
            ),
            re_diagnose_when=(
                "Re-diagnose when the Challenger forward clock completes or an integrity gate regresses."
            ),
        )

    if evaluated_rows < 500:
        return StrategicFocus(
            schema_version=STRATEGIC_FOCUS_SCHEMA_VERSION,
            diagnosis=(
                f"The system has {evaluated_rows} clean paired evaluations: enough for "
                "diagnostics, but still below the project's serious validation starting point."
            ),
            guiding_policy=(
                "Use the sample to diagnose data/model weaknesses and preregister hypotheses, "
                "not to declare an edge or tune the Champion."
            ),
            selected_chain_link="prospective_validation",
            proximate_objective=(
                "Grow the untouched paired cohort toward 500 while using 100-300 race "
                "diagnostics only for hypothesis generation."
            ),
            coherent_actions=(
                "run calibration and Champion-vs-market slice diagnostics",
                "record anomalies and candidate mechanisms as Challenger hypotheses",
                "continue improving PIT data coverage and market-path density",
            ),
            defer=(
                "claiming durable profitability",
                "tuning the frozen Champion on the evaluation cohort",
                "automatic promotion",
                "real-money execution",
            ),
            empirical_test=(
                "paired sample reaches 500 or a preregistered Challenger begins its own forward clock",
                "diagnostic findings are reproducible across relevant slices",
                "P0 integrity remains PASS",
            ),
            re_diagnose_when=(
                "Re-diagnose at 500 paired evaluations, Challenger registration, or any P0 regression."
            ),
        )

    return StrategicFocus(
        schema_version=STRATEGIC_FOCUS_SCHEMA_VERSION,
        diagnosis=(
            "Core integrity and the initial serious evidence threshold are satisfied; the next "
            "constraint is a falsifiable Challenger hypothesis, not more roadmap breadth."
        ),
        guiding_policy=(
            "Choose one high-value hypothesis, try to destroy it with confounder/ablation checks, "
            "then preregister a Challenger if it survives."
        ),
        selected_chain_link="challenger_hypothesis",
        proximate_objective=(
            "Advance at most one evidence-backed Challenger hypothesis into a locked forward test."
        ),
        coherent_actions=(
            "state the mechanism and expected incremental information beyond the market",
            "run point-in-time ablation and confounder checks on discovery data",
            "record a discovery cutoff and untouched forward-validation plan before registration",
        ),
        defer=(
            "multiple simultaneous feature families without ablation",
            "automatic promotion",
            "bet-product expansion before Win evidence is resolved",
            "real-money execution",
        ),
        empirical_test=(
            "the hypothesis has a concrete falsifier",
            "discovery data are separated from the future promotion sample",
            "the registered Challenger receives its own forward clock",
        ),
        re_diagnose_when=(
            "Re-diagnose after Challenger registration or if no candidate survives the destroy phase."
        ),
    )


def validate_hypothesis(payload: Mapping[str, object]) -> tuple[str, ...]:
    """Create/destroy gate for research ideas before Challenger registration."""
    required_text = (
        "name",
        "diagnosis",
        "mechanism",
        "expected_observation",
        "falsifier",
        "candidate_change",
        "discovery_cutoff_utc",
        "oos_plan",
    )
    errors = [
        f"missing:{key}"
        for key in required_text
        if not str(payload.get(key) or "").strip()
    ]
    confounders = payload.get("confounders")
    if not isinstance(confounders, list) or not confounders:
        errors.append("missing:confounders")
    if payload.get("production_authority") is not False:
        errors.append("production_authority_must_be_false")
    if payload.get("status") != "CHALLENGER_ONLY":
        errors.append("status_must_be_challenger_only")
    return tuple(errors)
