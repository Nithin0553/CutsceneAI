"""Read-only CLI for source asset manifest preparation and verification."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "studio"))

import asset_staging


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="CutSceneAI supported asset dependency inventory")
    actions = parser.add_subparsers(dest="action", required=True)
    prepare = actions.add_parser("plan", help="Write new immutable import manifest; no engine writes")
    prepare.add_argument("--csir", type=Path, required=True)
    prepare.add_argument("--mapping", type=Path, required=True)
    prepare.add_argument("--source-project", type=Path, required=True)
    prepare.add_argument("--target-folder", required=True,
                         help="Fresh isolated /Game/... namespace")
    prepare.add_argument("--out", type=Path, required=True)
    verify = actions.add_parser("verify", help="Check source and import manifest integrity")
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--csir", type=Path, required=True)
    verify.add_argument("--mapping", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "plan":
            manifest = asset_staging.compose_files(
                args.csir, args.mapping,
                source_project=args.source_project, target_folder=args.target_folder,
            )
            asset_staging.write_new(args.out, manifest)
        else:
            manifest = asset_staging.read_json(args.manifest)
            asset_staging.verify_files(manifest, args.csir, args.mapping)
            print("[CutSceneAI] ASSET MANIFEST: VERIFIED")
        print("[CutSceneAI] Source asset coverage:", manifest["status_counts"])
        print("[CutSceneAI] Unreal Editor not invoked; source project unchanged.")
        return 0
    except (asset_staging.AssetStagingError, OSError, ValueError, TypeError, KeyError) as exc:
        print("[CutSceneAI] BLOCKED:", str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
