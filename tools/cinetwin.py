"""Create or verify CineTwin artifacts without modifying a source project."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "cinetwin"))

from sampling_plan import plan_file, validate_capture


def main() -> int:
    parser = argparse.ArgumentParser(description="CutSceneAI CineTwin capture preparation")
    sub = parser.add_subparsers(dest="command", required=True)

    make = sub.add_parser("plan", help="Create a source-derived behavior sampling plan")
    make.add_argument("csir", type=Path)
    make.add_argument("output", type=Path)

    check = sub.add_parser("verify", help="Check completeness of a Unity behavior capture")
    check.add_argument("plan", type=Path)
    check.add_argument("capture", type=Path)

    args = parser.parse_args()
    if args.command == "plan":
        plan = plan_file(args.csir, args.output)
        print(
            f"[CineTwin] Plan: {len(plan['samples'])} sample times, "
            f"{len(plan['entities'])} entities, {args.output}"
        )
        print(
            "[CineTwin] Not implemented yet: "
            + ", ".join(
                entry["layer"] for entry in plan["capabilities"]
                if entry["status"] == "NOT_IMPLEMENTED"
            )
        )
        return 0

    plan = json.loads(args.plan.read_text(encoding="utf-8-sig"))
    capture = json.loads(args.capture.read_text(encoding="utf-8-sig"))
    report = validate_capture(plan, capture)
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
