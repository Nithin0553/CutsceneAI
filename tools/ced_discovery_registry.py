"""Register new/unknown CED observations from an existing preflight JSON report.

Usage:
  python tools/ced_discovery_registry.py --report REPORT.json --registry LOCAL.jsonl
  python tools/ced_discovery_registry.py --report REPORT.json --registry LOCAL.jsonl --dry-run

No engine, network, CED taxonomy, mapping or GitHub issue is modified.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIO = ROOT / "packages" / "studio"
if str(STUDIO) not in sys.path:
    sys.path.insert(0, str(STUDIO))

import ced_discovery_registry


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = json.loads(args.report.read_text(encoding="utf-8-sig"))
        result = ced_discovery_registry.record(
            report, args.registry, dry_run=args.dry_run
        )
        print("[CutSceneAI] CED discovery registry:")
        print("  New semantic signatures:", result["new_feature_signatures"])
        print("  New source observations:", result["new_observations"])
        print("  Previously recorded:", result["already_recorded"])
        print("  No CED edits, Unreal changes or remote notifications.")
        return 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print("[CutSceneAI] CED registry BLOCKED: "
              f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
