"""Read-only Unity CSIR asset dependency discovery and native-import staging plan.

An importer can only transfer supported *source files*, not Unity-native serialized
animation, shaders, playable assets or skeletons. Every referenced asset is accounted
for. This module never imports Unreal or writes to the source project.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

VERSION = "0.1.0"
WAV_TYPES = frozenset({"audio.asset"})
SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_]+$")


class AssetStagingError(ValueError):
    """Unsafe, ambiguous, or stale asset staging request."""


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: str | Path) -> dict[str, Any]:
    result = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(result, dict):
        raise AssetStagingError("Expected one JSON object.")
    return result


def _content_folder(folder: str) -> str:
    if (not isinstance(folder, str) or not folder.startswith("/Game/")
        or folder.endswith("/") or any(not SAFE_COMPONENT.fullmatch(part)
            for part in folder.split("/")[2:])):
        raise AssetStagingError("Target content folder must be a safe /Game/... path.")
    return folder


def _source_file(source_root: Path, source_path: str) -> tuple[Path | None, str]:
    # Unity-local files only. Packages, machine-local paths and traversal are
    # untrusted; never turn them into importable files.
    normalized = source_path.replace("\\", "/")
    segments = normalized.split("/")
    if (len(segments) < 2 or segments[0] != "Assets"
        or any(part in {"", ".", ".."} for part in segments)
        or ":" in normalized):
        return None, "Only Unity Assets/... project-local paths are transferable."
    candidate = source_root.joinpath(*segments)
    root = source_root.resolve()
    resolved = candidate.resolve()
    if not resolved.is_relative_to(root / "Assets"):
        return None, "Asset escapes the Unity Assets directory (possibly a symlink)."
    if not resolved.is_file():
        return None, "Source file missing or not readable."
    return resolved, ""


def _references(csir: dict[str, Any]) -> set[str]:
    ids = set()
    for entity in csir.get("entities", []):
        if entity.get("asset_id"):
            ids.add(str(entity["asset_id"]))
    for track in csir.get("tracks", []):
        if track.get("muted") is True:
            continue
        for section in track.get("sections", []):
            payload = section.get("payload") or {}
            if payload.get("asset_id"):
                ids.add(str(payload["asset_id"]))
            signal = payload.get("signal") or {}
            if signal.get("signal_asset_id"):
                ids.add(str(signal["signal_asset_id"]))
    return ids


def discover(
    csir: dict[str, Any],
    mapping: dict[str, Any],
    *,
    source_project: str | Path,
    target_folder: str,
    csir_sha256: str,
    mapping_sha256: str,
) -> dict[str, Any]:
    """Enumerate transitive references; never infer semantics from an asset name."""
    if csir.get("schema_version") != VERSION or csir.get("source", {}).get("engine") != "unity":
        raise AssetStagingError("Expected Unity CSIR v0.1.0.")
    if mapping.get("overwrite_sequence") is True:
        raise AssetStagingError("Unsafe target mapping: overwrite_sequence=true.")
    folder = _content_folder(target_folder)
    root = Path(source_project).resolve()
    if not (root / "Assets").is_dir():
        raise AssetStagingError("Unity source project has no Assets directory.")
    by_id = {}
    by_name: dict[str, list[str]] = defaultdict(list)
    for asset in csir.get("assets", []):
        aid = str(asset.get("asset_id", ""))
        if not aid or aid in by_id:
            raise AssetStagingError("Missing or duplicate source asset_id.")
        by_id[aid] = asset
        by_name[str(asset.get("name", ""))].append(aid)

    references = _references(csir)
    # Metadata may supply exporter-discovered dependency IDs; include closure.
    pending = sorted(references)
    while pending:
        aid = pending.pop()
        asset = by_id.get(aid)
        if asset is None:
            continue
        dependencies = (asset.get("metadata") or {}).get("dependency_asset_ids") or []
        if not isinstance(dependencies, list) or any(not isinstance(x, str) for x in dependencies):
            raise AssetStagingError(f"Invalid source dependency list for {aid}.")
        for dep in dependencies:
            if dep not in references:
                references.add(dep)
                pending.append(dep)

    rows = []
    for aid in sorted(references):
        asset = by_id.get(aid)
        if asset is None:
            rows.append({"asset_id": aid, "status": "MISSING_CSIR_RECORD",
                         "reason": "Referenced asset not present in CSIR assets.",
                         "source_sha256": None, "target_asset_path": None})
            continue
        name = str(asset.get("name", ""))
        kind = str(asset.get("ced_type", ""))
        metadata = asset.get("metadata") or {}
        path = str(metadata.get("asset_path") or "")
        dependencies = sorted(set(metadata.get("dependency_asset_ids") or []))
        source_file, file_reason = _source_file(root, path)
        status = "UNSUPPORTED_FORMAT"
        reason = "Only Unity AudioClip with a project-local WAV is currently importable."
        target = None
        source_hash = digest(source_file) if source_file is not None else None
        if len(by_name[name]) > 1 or not name:
            status, reason = "AMBIGUOUS_SOURCE_NAME", "Mapping keyed by name cannot distinguish assets."
        elif mapping.get("assets", {}).get(name):
            status, reason = "EXISTING_MAPPING_UNVERIFIED", "Existing target mapping requires editor class check."
            target = mapping["assets"][name]
        elif kind == "audio.asset" and Path(path).suffix.lower() == ".wav":
            if source_file is None:
                status, reason = "MISSING_SOURCE_FILE", file_reason
            elif source_file.open("rb").read(12)[:4] != b"RIFF" or source_file.open("rb").read(12)[8:12] != b"WAVE":
                status, reason = "UNSUPPORTED_WAV_CONTAINER", "Expected a native RIFF/WAVE header."
            else:
                status, reason = "READY_WAV_IMPORT", "Requires explicit rights confirmation and editor check."
                stem = re.sub(r"[^A-Za-z0-9_]", "_", Path(path).stem).strip("_")[:40] or "Audio"
                token = hashlib.sha256(aid.encode("utf-8")).hexdigest()[:12]
                target = f"{folder}/CSAI_{stem}_{token}"
        elif source_file is None:
            # For native Unity .anim etc, absent files do not become importable;
            # report the underlying unsupported semantics explicitly.
            reason += " " + file_reason
        rows.append({
            "asset_id": aid, "name": name, "ced_type": kind,
            "source_path": path, "source_file": str(source_file) if source_file else None,
            "source_sha256": source_hash,
            "dependency_asset_ids": dependencies, "status": status,
            "reason": reason, "target_asset_path": target,
            "expected_target_class": "SoundWave" if kind == "audio.asset" else None,
        })
    statuses = dict(sorted(Counter(row["status"] for row in rows).items()))
    return {
        "kind": "cutsceneai.studio.asset_import_manifest",
        "schema_version": VERSION, "cutscene_id": csir.get("cutscene_id"),
        "source_project": str(root), "source_project_fingerprint":
            csir.get("source", {}).get("project_fingerprint"),
        "source_csir_sha256": csir_sha256, "mapping_sha256": mapping_sha256,
        "target_folder": folder, "rights_confirmed": False,
        "status_counts": statuses, "assets": rows, "engine_import_executed": False,
        "coverage_warning": "Only READY_WAV_IMPORT files are importable; others remain partial.",
    }


def compose_files(
    csir_path: str | Path, mapping_path: str | Path, *,
    source_project: str | Path, target_folder: str,
) -> dict[str, Any]:
    src, mapping = Path(csir_path), Path(mapping_path)
    return discover(
        read_json(src), read_json(mapping), source_project=source_project,
        target_folder=target_folder, csir_sha256=digest(src),
        mapping_sha256=digest(mapping),
    )


def verify_files(manifest: dict[str, Any], csir_path: str | Path, mapping_path: str | Path) -> None:
    """Verify original CSIR and every importable file before any target mutation."""
    expected = compose_files(
        csir_path, mapping_path, source_project=manifest["source_project"],
        target_folder=manifest["target_folder"],
    )
    if manifest != expected:
        raise AssetStagingError("Asset manifest or source content changed; re-plan in a fresh folder.")


def write_new(path: str | Path, obj: dict[str, Any]) -> None:
    path = Path(path)
    if path.exists() or path.is_symlink():
        raise AssetStagingError(f"Refusing to overwrite: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as output:
        json.dump(obj, output, indent=2, sort_keys=True, ensure_ascii=False)
        output.write("\n")
