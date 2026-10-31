"""Prepare a unique Studio trial: safe mapping copy plus immutable transfer handoff.

No Unreal Editor calls. Original mapping and cutscene remain unchanged.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for part in ("packages/studio", "packages/learning", "packages/cinetwin", "integrations/unreal"):
    path = ROOT / part
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import prepared_transfer


def prepare_candidate(
    csir_path: Path,
    mapping_path: Path,
    capture_path: Path,
    sequence_path: str,
    output_folder: Path,
    *,
    skeletal_root_world_lock: bool = False,
) -> tuple[Path, dict]:
    """Write fresh mapping next to new output and source-verified prepared artifacts."""
    mapping_file = output_folder.with_suffix(".mapping.json")
    if output_folder.exists() or output_folder.is_symlink():
        raise ValueError("Refusing to reuse an existing candidate directory.")
    if mapping_file.exists() or mapping_file.is_symlink():
        raise ValueError("Refusing to replace candidate mapping.")
    if not sequence_path.startswith("/Game/") or not sequence_path.rsplit("/", 1)[-1]:
        raise ValueError("Sequence must be a named Unreal /Game asset.")
    previous = json.loads(mapping_path.read_text(encoding="utf-8-sig"))
    if previous.get("sequence_asset_path") == sequence_path:
        raise ValueError("Candidate cannot overwrite the original Level Sequence path.")
    if previous.get("overwrite_sequence") is True:
        raise ValueError("Unsafe source mapping allows sequence overwrite.")
    if not capture_path.is_file():
        raise ValueError("Source CineTwin capture missing.")
    copy = dict(previous)
    copy["sequence_asset_path"] = sequence_path
    copy["overwrite_sequence"] = False
    if skeletal_root_world_lock:
        copy["enable_cinetwin_skeletal_world_lock"] = True
    mapping_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        with mapping_file.open("x", encoding="utf-8") as handle:
            json.dump(copy, handle, indent=2)
            handle.write("\n")
        session = prepared_transfer.prepare(
            csir_path, mapping_file, output_folder,
            capture_path=capture_path,
        )
    except Exception:
        # Never remove an existing output folder, even if preparation fails.
        # The new mapping copy is harmless evidence for a failed trial.
        raise
    return mapping_file, session


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safe new Studio transfer candidate")
    parser.add_argument("--csir", required=True, type=Path)
    parser.add_argument("--mapping", required=True, type=Path)
    parser.add_argument("--capture", required=True, type=Path)
    parser.add_argument("--sequence", required=True)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--skeletal-root-world-lock", action="store_true")
    args = parser.parse_args(argv)
    try:
        mapping_copy, session = prepare_candidate(
            args.csir, args.mapping, args.capture, args.sequence, args.out,
            skeletal_root_world_lock=args.skeletal_root_world_lock,
        )
    except (ValueError, OSError, KeyError, json.JSONDecodeError,
            prepared_transfer.PreparedTransferError) as exc:
        print("[CutSceneAI Studio] CANDIDATE BLOCKED:", str(exc), file=sys.stderr)
        return 2
    print("[CutSceneAI Studio] Prepared unique candidate:", args.out)
    print("[CutSceneAI Studio] Copied mapping:", mapping_copy)
    print("[CutSceneAI Studio] Source-track coverage:", session["track_coverage"])
    print("[CutSceneAI Studio] Engine generation NOT run; target fidelity UNVERIFIED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
