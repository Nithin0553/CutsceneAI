"""CutSceneAI fresh-target asset preparation: read-only, source-verified, fail-closed.

Plan 2 skeletal character FBX models and deduplicated PNGs for a new Unreal
project. Animation FBX, MP3, Unity events and Timeline are explicitly deferred.
Never invent skeleton compatibility, auto-retarget, or cutscene fidelity.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

KIND = "cutsceneai.studio.fresh_target_asset_plan"
VERSION = "0.1.0"
SAFE = re.compile(r"^[A-Za-z0-9_]+$")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class FreshTargetError(ValueError):
    """Unsafe source, ambiguous destination or stale plan."""


def _digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _canonical_json(value: dict) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def _read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise FreshTargetError("Expected a JSON object: " + str(path))
    return value


def _scope(root: Path, relative_scope: str) -> Path:
    norm = relative_scope.replace("\\", "/").strip("/")
    parts = norm.split("/")
    if len(parts) < 2 or parts[0] != "Assets" or any(
        part in ("", ".", "..") for part in parts
    ) or ":" in norm:
        raise FreshTargetError("Scope must be a safe Assets/... subtree.")
    resolved = root.joinpath(*parts).resolve()
    if not resolved.is_relative_to((root / "Assets").resolve()):
        raise FreshTargetError("Scope escapes Unity Assets; symlinks are not allowed.")
    if not resolved.is_dir():
        raise FreshTargetError("Scope directory missing: " + str(resolved))
    return resolved


def _target_folder(path: str) -> str:
    parts = path.split("/")
    if len(parts) < 3 or parts[:2] != ["", "Game"] or any(
        not SAFE.fullmatch(p) for p in parts[2:]
    ):
        raise FreshTargetError("Destination must be a fresh /Game/... asset folder.")
    return path


def _unique_asset_name(stem: str, digest: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_]", "_", stem).strip("_")[:52] or "Asset"
    return "CSAI_" + safe + "_" + digest[:10]


def compose(*, csir: str | Path, source_project: str | Path,
            scope: str, target_project: str | Path,
            target_folder: str) -> dict:
    source = Path(source_project).resolve()
    project = Path(target_project).resolve()
    csir_path = Path(csir).resolve()
    if not (source / "Assets").is_dir():
        raise FreshTargetError("Unity project has no Assets directory.")
    if not project.is_file() or project.suffix.lower() != ".uproject":
        raise FreshTargetError("Target Unreal .uproject not found.")
    folder = _target_folder(target_folder)
    subset = _scope(source, scope)
    doc = _read_json(csir_path)
    if doc.get("source", {}).get("engine") != "unity" or doc.get("schema_version") != VERSION:
        raise FreshTargetError("Expected Unity CSIR v0.1.0.")
    characters = {str(e.get("name")) for e in doc.get("entities", [])
                  if e.get("ced_type") == "entity.character"}
    expected_model_names = {name.casefold() for name in characters}

    files = sorted((p for p in subset.rglob("*") if p.is_file() and
                    p.suffix.lower() in {".fbx", ".png", ".mp3"}),
                   key=lambda p: str(p).casefold())
    if not files:
        raise FreshTargetError("No FBX, PNG or MP3 files found inside scope.")
    rows = []
    texture_hashes: dict[str, str] = {}
    claimed_targets: set[str] = set()
    for file in files:
        resolved = file.resolve()
        if not resolved.is_relative_to(subset):
            raise FreshTargetError("Source symlink escapes the selected scope: " + str(file))
        rel = resolved.relative_to(source).as_posix()
        rel_under_scope = resolved.relative_to(subset).parts
        sha = _digest(resolved)
        suffix = file.suffix.lower()
        role = "OTHER"
        status = "DEFERRED_UNCLASSIFIED"
        dest = None
        duplicate_of = None
        if suffix == ".fbx" and len(rel_under_scope) >= 2:
            if rel_under_scope[0].casefold() == "characters" and file.stem.casefold() in expected_model_names:
                if file.stat().st_size <= 0:
                    status = "BLOCKED_EMPTY_FILE"
                else:
                    status = "CANDIDATE_SKELETAL_MODEL_UNVERIFIED"
                    role = "CHARACTER_MODEL"
                    dest = folder + "/Characters/" + _unique_asset_name(file.stem, sha)
            elif rel_under_scope[0].casefold() == "animations":
                role, status = "ANIMATION_FBX", "DEFERRED_SKELETON_COMPATIBILITY"
        elif suffix == ".png":
            role = "CHARACTER_TEXTURE" if len(rel_under_scope) >= 2 and rel_under_scope[0].casefold() == "characters" else "OTHER_TEXTURE"
            if file.open("rb").read(8) != PNG_SIGNATURE:
                status = "BLOCKED_INVALID_PNG"
            elif sha in texture_hashes:
                status, duplicate_of = "DUPLICATE_CONTENT", texture_hashes[sha]
            elif role == "CHARACTER_TEXTURE":
                status = "CANDIDATE_TEXTURE_UNVERIFIED"
                dest = folder + "/Textures/" + _unique_asset_name(file.stem, sha)
                texture_hashes[sha] = rel
            else:
                status = "DEFERRED_UNRELATED_TEXTURE"
        elif suffix == ".mp3":
            role, status = "AUDIO_MP3", "DEFERRED_MP3_TO_WAV"
        if dest:
            if dest.casefold() in claimed_targets:
                raise FreshTargetError("Asset name collision in planned destination: " + dest)
            claimed_targets.add(dest.casefold())
        rows.append({"source_path": rel, "source_file": str(resolved), "sha256": sha,
                     "bytes": file.stat().st_size, "role": role, "status": status,
                     "target_asset_path": dest, "duplicate_of": duplicate_of})
    models = [row for row in rows if row["role"] == "CHARACTER_MODEL"]
    represented = {Path(row["source_file"]).stem.casefold() for row in models}
    warnings = ["Only candidate skeletal FBX models and deduplicated PNG textures are planned for stage-one import.",
                "FBX files have not been validated for rig/skeleton compatibility; Unreal must report actual imported classes.",
                "Animation FBX, MP3 conversion, materials, actor creation and cutscene parity are not performed."]
    if not models:
        warnings.append("No character FBX basename matched a CSIR character entity in the selected scope.")
    return {"kind": KIND, "schema_version": VERSION, "source_csir": str(csir_path),
            "source_csir_sha256": _digest(csir_path), "source_project": str(source),
            "source_scope": scope.replace("\\", "/").strip("/"),
            "target_project": str(project), "target_project_sha256": _digest(project),
            "target_folder": folder, "source_character_names": sorted(characters),
            "matched_character_models": sorted(represented),
            "status_counts": dict(sorted(Counter(x["status"] for x in rows).items())),
            "files": rows, "warnings": warnings, "engine_import_executed": False,
            "rig_compatibility_verified": False, "transfer_fidelity_verified": False}


def verify(manifest: str | Path) -> dict:
    file = Path(manifest)
    saved = _read_json(file)
    if saved.get("kind") != KIND or saved.get("schema_version") != VERSION:
        raise FreshTargetError("Unknown stage-one asset plan schema.")
    expected = compose(csir=saved["source_csir"],
                       source_project=saved["source_project"],
                       scope=saved["source_scope"],
                       target_project=saved["target_project"],
                       target_folder=saved["target_folder"])
    if saved != expected:
        raise FreshTargetError("Source, target project or plan changed; prepare a fresh plan.")
    return saved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only fresh Unreal target import preparation")
    sub = parser.add_subparsers(dest="action", required=True)
    prepare = sub.add_parser("plan")
    prepare.add_argument("--csir", required=True)
    prepare.add_argument("--source-project", required=True)
    prepare.add_argument("--scope", required=True)
    prepare.add_argument("--target-project", required=True)
    prepare.add_argument("--target-folder", required=True)
    prepare.add_argument("--out", required=True)
    check = sub.add_parser("verify")
    check.add_argument("--manifest", required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "plan":
            out = Path(args.out)
            if out.exists() or out.is_symlink():
                raise FreshTargetError("Refusing to overwrite an existing import plan.")
            obj = compose(csir=args.csir, source_project=args.source_project,
                          scope=args.scope, target_project=args.target_project,
                          target_folder=args.target_folder)
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(_canonical_json(obj))
            print("[CutSceneAI] FRESH TARGET PLAN:", out)
        else:
            obj = verify(args.manifest)
            print("[CutSceneAI] FRESH TARGET PLAN VERIFIED")
        print("[CutSceneAI] Status counts:", obj["status_counts"])
        print("[CutSceneAI] Target scene not modified; skeletal compatibility UNVERIFIED.")
        return 0
    except (FreshTargetError, OSError, json.JSONDecodeError, KeyError) as err:
        print("[CutSceneAI] BLOCKED:", err, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
