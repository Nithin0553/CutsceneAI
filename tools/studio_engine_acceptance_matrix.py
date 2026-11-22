"""Review native Unreal acceptance evidence after workstation editor runs.

Usage:
  python tools/studio_engine_acceptance_matrix.py \
      --workspace path/to/studio/workspace \
      --manifest path/to/studio/acceptance-matrix.json \
      --output path/to/new-review.json

This tool does not start engines or certify visual/physics/audio fidelity.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "packages" / "studio"))

import engine_acceptance_matrix as acceptance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if not args.workspace.resolve().is_dir():
        parser.error("Selected Studio evidence workspace does not exist.")
    if args.output.exists() or args.output.is_symlink():
        parser.error("Refusing to overwrite a prior engine acceptance review.")
    manifest = acceptance._json_bound(args.manifest, args.workspace)
    try:
        result = acceptance.evaluate(manifest, args.workspace)
    except acceptance.MatrixError as error:
        parser.error(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, sort_keys=True, allow_nan=False)
        stream.write("\n")
    print(result["status"])
    print("Human editor/log/render review remains mandatory: " + str(args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
