"""CutSceneAI Studio CLI — prepare reproducible, read-only conversion sessions.

Actual engine generation stays gated behind explicit user action, source-coverage
check, editor runtime preflight and staging-project backup.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for directory in (
    ROOT / "packages" / "studio",
    ROOT / "packages" / "learning",
    ROOT / "packages" / "cinetwin",
    ROOT / "integrations" / "unreal",
):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import case_memory
import session


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CutSceneAI Studio conversion orchestrator")
    actions = parser.add_subparsers(dest="action", required=True)
    prepare = actions.add_parser("prepare", help="Source-only coverage, planning and suggestions")
    prepare.add_argument("--csir", type=Path, required=True)
    prepare.add_argument("--mapping", type=Path, required=True)
    prepare.add_argument("--out", type=Path, required=True)
    prepare.add_argument("--target-project", type=Path)
    prepare.add_argument("--case-store", type=Path)

    args = parser.parse_args(argv)
    try:
        library = case_memory.list_cases(args.case_store) if args.case_store else []
        record = session.prepare(
            args.csir, args.mapping, args.out,
            target_project=args.target_project,
            verified_cases=library,
        )
        print("[CutSceneAI Studio] Session:", record["session_id"])
        print("[CutSceneAI Studio] Status:", record["stage"])
        print("[CutSceneAI Studio] Source feature coverage:", record["source_coverage"])
        print("[CutSceneAI Studio] Candidate learning cases:", record["proposed_mapping_cases"])
        print("[CutSceneAI Studio] Data:", args.out)
        print("[CutSceneAI Studio] No target engine was invoked or modified.")
        return 2 if record["stage"].startswith("BLOCKED") else 0
    except (session.StudioError, OSError, ValueError, TypeError, KeyError) as exc:
        print("[CutSceneAI Studio] BLOCKED:", str(exc), file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
