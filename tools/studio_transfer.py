"""CLI for immutable end-to-end Studio *preparation* and source-hash verification.

Unreal generation is deliberately separate and requires a live editor preflight.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for directory in (
    ROOT / "packages" / "studio", ROOT / "packages" / "learning",
    ROOT / "packages" / "cinetwin", ROOT / "integrations" / "unreal",
):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import prepared_transfer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CutSceneAI Studio verified transfer handoff")
    actions = parser.add_subparsers(dest="action", required=True)
    prepare = actions.add_parser("prepare", help="Prepare best-effort plan and evidence, no engine writes")
    prepare.add_argument("--csir", type=Path, required=True)
    prepare.add_argument("--mapping", type=Path, required=True)
    prepare.add_argument("--capture", type=Path)
    prepare.add_argument("--target-project", type=Path)
    prepare.add_argument("--case-store", type=Path)
    prepare.add_argument("--strict-ced", action="store_true")
    prepare.add_argument("--out", type=Path, required=True)
    verify = actions.add_parser("verify", help="Read-only verification of existing prepared handoff")
    verify.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "verify":
            record = prepared_transfer.verify(args.out)
            print("[CutSceneAI Studio] PREPARED HANDOFF: VERIFIED")
        else:
            record = prepared_transfer.prepare(
                args.csir, args.mapping, args.out, capture_path=args.capture,
                target_project=args.target_project, case_store=args.case_store,
                strict_ced=args.strict_ced,
            )
            print("[CutSceneAI Studio] PREPARED HANDOFF: GENERATED, NOT EXECUTED")
        print("[CutSceneAI Studio] Session:", record["session_id"])
        print("[CutSceneAI Studio] Stage:", record["stage"])
        print("[CutSceneAI Studio] Track coverage:", record["track_coverage"])
        print("[CutSceneAI Studio] Learning proposals only:", record["learning_case_count"])
        print("[CutSceneAI Studio] Target assets and engine untouched.")
        return 0
    except (prepared_transfer.PreparedTransferError, OSError, ValueError,
            TypeError, KeyError) as exc:
        print("[CutSceneAI Studio] BLOCKED:", str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
