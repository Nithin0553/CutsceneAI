"""Compile a reviewed Unity skeletal pose-bake without launching either editor.

Reads source CSIR, its exact CineTwin capture, and an operator-approved rest
pose/bone map; writes an immutable, SHA-bound native-key staging plan. It does
NOT import or modify Unreal assets. A separate native writer and independent
post-reopen readback are mandatory.

Example:
  python tools/studio_compile_skeletal_pose.py --csir SOURCE.csir.json \
      --capture SOURCE.cinetwin.behavior.json --approval APPROVED-BONES.json \
      --output NEW-pose-bake.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for folder in ("packages/cinetwin", "packages/studio", "integrations/unreal"):
    sys.path.insert(0, str(ROOT / folder))

import skeletal_pose_bake as compiler


def _read(path: Path, max_size: int) -> tuple[dict, str]:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= max_size:
        raise compiler.PoseBakeError("Input file is missing, symlinked, empty or oversized: " + str(path))
    raw = path.read_bytes()
    try:
        obj = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as exc:
        raise compiler.PoseBakeError("Skeletal evidence is not a JSON object.") from exc
    if not isinstance(obj, dict):
        raise compiler.PoseBakeError("Skeletal evidence requires a JSON object.")
    return obj, hashlib.sha256(raw).hexdigest()


def compile_files(csir: Path, capture: Path, approval: Path, output: Path) -> dict:
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise compiler.PoseBakeError("Use a new, previously nonexistent output file in an existing directory.")
    source, source_hash = _read(csir, 64 * 1024 * 1024)
    observed, capture_hash = _read(capture, 64 * 1024 * 1024)
    reviewed, _ = _read(approval, 4 * 1024 * 1024)
    document = compiler.compile_baked_pose(
        source, observed, reviewed,
        csir_sha256=source_hash, capture_sha256=capture_hash,
    )
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    return document


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csir", type=Path, required=True)
    parser.add_argument("--capture", type=Path, required=True)
    parser.add_argument("--approval", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        document = compile_files(args.csir, args.capture, args.approval, args.output)
    except compiler.PoseBakeError as exc:
        parser.error(str(exc))
    print(json.dumps({
        "native_asset_generation_status": document["native_asset_generation_status"],
        "sampled_keys": document["sampled_keys"],
        "bone_count": len(document["bone_tracks"]),
        "target_asset_path": document["target"]["animation_asset_path"],
        "native_engine_fidelity_verified": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
