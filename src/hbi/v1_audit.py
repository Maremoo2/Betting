from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from .challenger import sync_forward_events_from_evaluations
from .governance import load_governance, validate_governance
from .learning import build_learning_rows, learning_dataset_summary
from .provider_integrity import run_provider_integrity
from .replay_validation import run_runtime_replay_parity
from .research_integrity import run_research_integrity_check
from .settlement_integrity import run_settlement_integrity
from .storage import SQLiteStore

ROOT = Path(__file__).parents[2]
SCHEMA = ROOT / "db" / "schema.sql"
MIGRATIONS = ROOT / "db" / "migrations"
GOVERNANCE = ROOT / "docs" / "research_governance.json"


def _write_learning_csv(rows: list[dict[str, object]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _render_markdown(report: dict[str, object]) -> str:
    governance = report["governance"]
    temporal = report["temporal_integrity"]
    provider = report["provider_integrity"]
    replay = report["runtime_replay_parity"]
    settlement = report["settlement_integrity"]
    learning = report["learning_dataset"]
    lines = [
        "# HBI V1 System Audit",
        "",
        f"- Generated: {report['generated_at_utc']}",
        f"- Engineering status: **{report['engineering_status']}**",
        f"- V1 engineering complete: **{report['v1_engineering_complete']}**",
        f"- Current P0 evidence: **{report['current_p0_evidence_status']}**",
        f"- Strategic validity: **{governance['strategic_validity']}**",
        f"- Operational validity: **{governance['operational_validity']}**",
        "",
        "## P0 integrity",
        "",
        (
            f"- Temporal integrity: **{temporal['status']}** "
            f"({temporal['database']['checked_rows']} stored rows checked)"
        ),
        (
            f"- Provider integrity: **{provider['status']}** "
            f"({provider['checked_decisions']} decisions checked)"
        ),
        (
            f"- Runtime replay parity: **{replay['status']}** "
            f"({replay['checked_decisions']} decisions replayed)"
        ),
        (
            f"- Settlement integrity: **{settlement['status']}** "
            f"({settlement['checked_rows']} records checked)"
        ),
        "",
        "## Learning plane",
        "",
        f"- Frozen learning rows: {learning['rows']}",
        f"- Evaluated rows: {learning['evaluated_rows']}",
        f"- Settled rows: {learning['settled_rows']}",
        f"- Data quality: {learning['data_quality']}",
        "",
        "## Governance",
        "",
        f"- Governance valid: {report['governance_validation']['valid']}",
        f"- Automatic promotion: {governance['auto_promotion_enabled']}",
        f"- Adaptive switching: {governance['adaptive_switching_enabled']}",
        f"- Real-money execution: {governance['real_money_execution']}",
        f"- Manual approval required: {governance['manual_approval_required']}",
        "",
        (
            "Engineering completion does not imply a proven betting edge. "
            "Strategic validation requires prospective evidence and the configured "
            "P0/P1 gates."
        ),
        "",
    ]
    return "\n".join(lines)


def run_v1_audit(
    store: SQLiteStore,
    *,
    output_dir: str | Path | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    generated = now or datetime.now(UTC)
    governance = load_governance(GOVERNANCE)
    governance_validation = validate_governance(governance)
    temporal = run_research_integrity_check(store)
    replay = run_runtime_replay_parity(store)
    provider = run_provider_integrity(store)
    settlement = run_settlement_integrity(store, now=generated)
    learning_rows = build_learning_rows(store)
    learning_summary = learning_dataset_summary(learning_rows)

    challenger_clocks: list[dict[str, object]] = []
    for challenger in store.fetch_table("challenger_registry"):
        clock = sync_forward_events_from_evaluations(
            store,
            str(challenger["challenger_id"]),
        )
        challenger_clocks.append(
            {
                "challenger_id": clock.challenger_id,
                "eligible_races": clock.eligible_races,
                "minimum_races": clock.minimum_races,
                "status": clock.status,
                "forward_start_utc": clock.forward_start_utc,
            }
        )

    actual_p0 = {
        "temporal_integrity": str(temporal["status"]),
        "provider_integrity": str(provider["status"]),
        "runtime_replay_parity": str(replay["status"]),
        "settlement_integrity": str(settlement["status"]),
    }
    hard_fail = (
        not governance_validation.valid
        or any(status == "FAIL" for status in actual_p0.values())
    )
    evidence_pending = any(
        status in {"NO_EVIDENCE", "WARN"} for status in actual_p0.values()
    )
    engineering_status = (
        "FAIL"
        if hard_fail
        else "PASS_WITH_EVIDENCE_PENDING"
        if evidence_pending
        else "PASS"
    )
    current_p0_evidence_status = (
        "FAIL"
        if hard_fail
        else "EVIDENCE_PENDING"
        if evidence_pending
        else "PASS"
    )

    report: dict[str, object] = {
        "schema_version": "HBI_V1_SYSTEM_AUDIT_V1",
        "generated_at_utc": generated.isoformat(),
        "engineering_status": engineering_status,
        "v1_engineering_complete": engineering_status == "PASS",
        "current_p0_evidence_status": current_p0_evidence_status,
        "current_p0_evidence": actual_p0,
        "governance": governance,
        "governance_validation": {
            "valid": governance_validation.valid,
            "errors": list(governance_validation.errors),
            "warnings": list(governance_validation.warnings),
        },
        "temporal_integrity": temporal,
        "provider_integrity": provider,
        "runtime_replay_parity": replay,
        "settlement_integrity": settlement,
        "learning_dataset": learning_summary,
        "challenger_forward_clocks": challenger_clocks,
        "interpretation": (
            "V1 engineering completion is determined by the implemented control plane "
            "and current audit evidence. Strategic validity remains a separate research "
            "claim and stays governed by untouched prospective evidence."
        ),
    }
    report["markdown"] = _render_markdown(report)

    if output_dir is not None:
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        (output / "v1-system-audit.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (output / "v1-system-audit.md").write_text(
            str(report["markdown"]),
            encoding="utf-8",
        )
        (output / "research-learning-dataset.json").write_text(
            json.dumps(learning_rows, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        _write_learning_csv(
            learning_rows,
            output / "research-learning-dataset.csv",
        )

    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="data/hbi.sqlite")
    parser.add_argument("--output-dir", default="research-v1")
    args = parser.parse_args()

    store = SQLiteStore(args.db)
    store.initialize(SCHEMA)
    if MIGRATIONS.exists():
        store.apply_migrations(MIGRATIONS)
    report = run_v1_audit(store, output_dir=args.output_dir)
    store.checkpoint()
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["engineering_status"] == "FAIL":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
