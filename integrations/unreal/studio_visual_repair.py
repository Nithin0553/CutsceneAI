"""Bounded, source-backed post-generation material repair for fresh Studio actors.

This is one strictly scoped iterative strategy. It never changes existing
non-default materials, imported audio, camera tracks, animation or source data.
Full cinematic, URP shader and render parity are NOT established.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import studio_material_restore


class VisualRepairError(RuntimeError):
    """The source-backed repair must stop without guessing."""


def attempt(job: dict[str, Any], setup: dict[str, Any], api: Any) -> dict[str, Any]:
    """Restore exact, GUID-provenanced albedo on *newly staged* fallback slots."""
    if not job.get("automatic_setup") or not setup:
        return {"status": "NOT_APPLICABLE", "changed": 0, "slots": []}
    # Recheck source files and manifest against the same immutable transfer plan
    # before modifying even an already generated staging actor.
    import studio_auto_assets

    candidate = Path(job["candidate_dir"])
    manifest = studio_auto_assets.verify(
        job["automatic_setup_manifest"], job["csir"], job["mapping"],
        candidate / "transfer-plan.json",
    )
    sources = manifest.get("source_albedo_material_candidates") or []
    if not sources:
        return {"status": "NO_SOURCE_BACKED_ALBEDO", "changed": 0, "slots": []}
    imported_actors = {item["name"] for item in setup.get("actors_created") or []}
    if not imported_actors:
        return {"status": "NO_NEW_ACTORS", "changed": 0, "slots": []}
    # Only reuse a material created by the verified initial import, not any
    # unrelated/user-created asset with a coincidental Unreal package path.
    cache = {}
    candidate_paths = {row["target_material"]: row for row in sources}
    for row in setup.get("material_restoration") or []:
        path = row.get("target_material")
        source = candidate_paths.get(path)
        if (row.get("status") != "SOURCE_ALBEDO_ASSIGNED_RENDER_PARITY_UNVERIFIED"
                or not source or row.get("source_material_sha256") != source["source_material_sha256"]):
            continue
        native = api.load_asset(path)
        if native is None or native.get_class().get_name() != "Material":
            raise VisualRepairError("Verified staged material missing/wrong class: " + path)
        cache[path] = native
    by_label = {}
    subsystem = api.get_editor_subsystem(api.EditorActorSubsystem)
    for actor in subsystem.get_all_level_actors():
        by_label.setdefault(str(actor.get_actor_label()), []).append(actor)
    slots = []
    for row in manifest["actors"]:
        if row["name"] not in imported_actors or row["kind"] not in {"entity.character", "entity.prop"}:
            continue
        matches = by_label.get(row["label"], [])
        if len(matches) != 1:
            raise VisualRepairError("New staged actor mapping no longer unique: " + row["label"])
        for item in studio_material_restore.restore(api, matches[0], sources, existing_assets=cache):
            slots.append({**item, "actor": row["name"]})
    changed = sum(item["status"] == "SOURCE_ALBEDO_ASSIGNED_RENDER_PARITY_UNVERIFIED" for item in slots)
    return {"status": "SOURCE_ALBEDO_REASSIGNED_FIDELITY_UNVERIFIED" if changed else "NO_SAFE_REPAIR",
            "changed": changed, "slots": slots}
