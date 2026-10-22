"""Classify source coverage before starting a Unity-to-Unreal transfer.

Run from any Python 3.11+ shell; DOES NOT import Unreal or touch level assets.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "cinetwin"))

from transfer_readiness import audit_files


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only CutSceneAI transfer readiness")
    parser.add_argument("csir", type=Path, help="Frozen Unity source CSIR")
    parser.add_argument("mapping", type=Path, help="Target mapping file")
    parser.add_argument("--output", type=Path, help="Optional JSON readiness report")
    args = parser.parse_args(argv)

    try:
        report = audit_files(args.csir, args.mapping)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"[CutSceneAI] Source preflight error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"[CutSceneAI] Generation: {report['generation']}")
    print(f"[CutSceneAI] Fidelity: {report['fidelity']}")
    print(f"[CutSceneAI] Source tracks: {report['source_track_count']}; "
          f"coverage: {report['counts']}")
    for row in report["tracks"]:
        if row["state"] not in ("COVERED", "SKIPPED"):
            print(f"  {row['state']} {row['track_name'] or row['track_id']}: "
                  + "; ".join(row["reasons"]))
    if report["plan_error"]:
        print(f"[CutSceneAI] Planner error: {report['plan_error']}", file=sys.stderr)
    if args.output:
        print(f"[CutSceneAI] Report: {args.output}")
    return 2 if report["generation"] == "BLOCKED" else 0


if __name__ == "__main__":
    raise SystemExit(main())
