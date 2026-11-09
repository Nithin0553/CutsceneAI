"""Register and inspect authentic Unity CineTwin source datasets.

No game-engine invocation. No fake positive transfer labels.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for directory in (ROOT / "packages" / "dataset", ROOT / "packages" / "cinetwin"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CutSceneAI Studio dataset ingestion")
    commands = parser.add_subparsers(dest="action", required=True)

    collect = commands.add_parser("register", help="Validate and snapshot source artifacts")
    collect.add_argument("--root", type=Path, required=True)
    collect.add_argument("--project-id", required=True)
    collect.add_argument("--scene-id", required=True)
    collect.add_argument("--csir", type=Path, required=True)
    collect.add_argument("--plan", type=Path, required=True)
    collect.add_argument("--capture", type=Path, required=True)
    collect.add_argument("--profile", type=Path)

    audit = commands.add_parser("status", help="Validate registered checksums and group identities")
    audit.add_argument("--root", type=Path, required=True)
    audit.add_argument("--output", type=Path)

    args = parser.parse_args(argv)
    try:
        if args.action == "register":
            result = registry.register(
                args.root, args.project_id, args.scene_id,
                csir=args.csir, plan=args.plan, capture=args.capture,
                profile=args.profile,
            )
            print(f"[Studio Dataset] Registered {result['project_id']}/{result['scene_id']}")
            print(f"[Studio Dataset] Capture: {result['capture_status']}; "
                  f"samples={result['sampling_count']}; rigs={result['rig_count']}")
            print("[Studio Dataset] Transfer labels: UNLABELED (no training success claimed)")
        else:
            result = registry.dataset_report(args.root)
            print(json.dumps(result, indent=2))
            if args.output:
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return 0
    except (registry.DatasetError, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"[Studio Dataset] BLOCKED: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
