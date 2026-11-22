"""Explicit native animation source format routing for Unity to Unreal.

File extension is a *classification* signal, never proof of imported motion
or of permission to invoke another program. Only a hashed, uniquely resolved
FBX take enters the existing IK Retargeter path. Unity .anim can carry
Transform curves for non-skeletal actors; skeletal .anim needs a separate
native skeletal pose-bake codec and cannot masquerade as an FBX AnimSequence.
"""
from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any


class AnimationFormatError(ValueError):
    pass


CHARACTER_NATIVE = "APPROVED_FBX_IK_RETARGET_CANDIDATE"
ACTOR_CURVES = "CANONICAL_TRANSFORM_CURVES_OR_EVALUATED_WORLD_CAPTURE"
SKELETAL_BAKE = "SOURCE_SKELETAL_POSE_BAKE_REQUIRED"
UNKNOWN = "FORMAT_PROVENANCE_UNVERIFIED"
EXTERNAL = "EXTERNAL_DCC_OR_REGISTERED_IMPORT_ADAPTER_REQUIRED"


def classify(asset: dict[str, Any], *, skeletal: bool) -> dict[str, Any]:
    metadata = asset.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    raw = metadata.get("asset_path")
    if not isinstance(raw, str) or not raw.strip():
        return {"format": "unknown", "policy": UNKNOWN, "native_conversion_approved": False}
    path = raw.replace("\\", "/")
    parts = path.split("/")
    if (len(parts) < 2 or parts[0] != "Assets"
            or any(part in ("", ".", "..") for part in parts)):
        return {"format": "untrusted", "policy": UNKNOWN, "native_conversion_approved": False}
    extension = PurePosixPath(path).suffix.casefold()
    if extension == ".fbx":
        policy = CHARACTER_NATIVE if skeletal else ACTOR_CURVES
        next_step = (
            "Verify Unity FBX/meta hashes, exact clip subasset/default take, "
            "approved native reference rig and source/target IK Retargeter."
            if skeletal else "Convert root Transform curves or source-evaluated world actor motion."
        )
    elif extension == ".anim":
        policy = SKELETAL_BAKE if skeletal else ACTOR_CURVES
        next_step = (
            "Unity-native skeletal .anim requires a registered sampled-bone "
            "AnimSequence writer; do not pass .anim to Unreal FBX importer."
            if skeletal else "Use captured Unity root transform channels or evaluated world samples."
        )
    elif extension in {".bvh", ".gltf", ".glb", ".dae", ".usd", ".usdz", ".abc", ".blend"}:
        policy = EXTERNAL
        next_step = (
            "Create a reviewed source conversion/export adapter with native "
            "asset identity, geometry/skeleton validation and readback before transfer."
        )
    else:
        policy = UNKNOWN
        next_step = "Record source asset identity and register a verified import/baking adapter."
    return {
        "format": extension or "unknown",
        "policy": policy,
        "native_conversion_approved": False,
        "path": path,
        "next_step": next_step,
    }


def inventory(csir: dict[str, Any]) -> dict[str, Any]:
    assets = {a.get("asset_id"): a for a in csir.get("assets", [])}
    entities = {e.get("entity_id"): e for e in csir.get("entities", [])}
    entries: list[dict[str, Any]] = []
    for index, track in enumerate(csir.get("tracks", [])):
        if track.get("muted") is True or track.get("ced_type") != "animation.track":
            continue
        entity = entities.get(track.get("binding_entity_id"), {})
        skeletal = entity.get("ced_type") == "entity.character"
        for section in track.get("sections", []):
            identifier = (section.get("payload") or {}).get("asset_id")
            asset = assets.get(identifier)
            if not isinstance(asset, dict):
                decision = {"format": "unknown", "policy": UNKNOWN,
                            "native_conversion_approved": False,
                            "next_step": "Resolve source asset ID and exact native clip reference."}
            else:
                decision = classify(asset, skeletal=skeletal)
            entries.append({
                "track_index": index, "section_id": str(section.get("section_id") or ""),
                "source_entity_id": str(entity.get("entity_id") or ""),
                "source_asset_id": str(identifier or ""),
                "character_skeletal_animation": skeletal,
                **decision,
            })
    return {
        "kind": "cutsceneai.studio.animation_format_inventory",
        "schema_version": "1",
        "sections": entries,
        "source_clip_count": len(entries),
        "native_import_fidelity_verified": False,
    }
