"""Read-only source-bound Element 8 recovery triage for an existing Studio job.

Examples:
    python tools/studio_element8_repair.py --workspace ... --job-id ... \
        --evidence .../native-acceptance-0001
    python tools/studio_element8_repair.py --workspace ... --job-id ... \
        --evidence .../native-acceptance-0001 .../native-acceptance-0002 --save

This command never starts Unreal, applies a correction or retries native work.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = str(ROOT / "packages" / "studio")
if STUDIO not in sys.path:
    sys.path.insert(0, STUDIO)

import studio_element8_repair


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument(
        "--evidence", type=Path, nargs="+", required=True,
        help="Ordered baseline and up to two candidate-local native-acceptance folders.",
    )
    parser.add_argument(
        "--save", action="store_true",
        help="Write the immutable candidate-local Element 8 review, without any engine action.",
    )
    opts = parser.parse_args()
    try:
        if opts.save:
            path, report = studio_element8_repair.save_once(
                opts.workspace, opts.job_id, opts.evidence,
            )
        else:
            path = None
            report = studio_element8_repair.build(
                opts.workspace, opts.job_id, opts.evidence,
            )
    except (studio_element8_repair.BoundedRepairError, OSError,
            ValueError, KeyError, TypeError) as exc:
        parser.error("Element 8 verification stopped: " + type(exc).__name__)
    summary = {
        "kind": report["kind"],
        "status": report["status"],
        "repair_plan_sha256": report["repair_plan_sha256"],
        "remeasurement_attempts": report["remeasurement_attempts"],
        "remaining_manual_observation_budget":
            report["remaining_manual_observation_budget"],
        "source_occurrence_count": report["source_occurrence_count"],
        "native_repair_adapter_available_for_review":
            report["native_repair_adapter_available_for_review"],
        "native_repair_authorized": False,
        "automatic_native_retry_authorized": False,
        "full_cutscene_fidelity_verified": False,
        "saved": bool(path),
    }
    print(json.dumps(summary, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
