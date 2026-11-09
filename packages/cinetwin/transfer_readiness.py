"""Read-only semantic coverage audit for arbitrary Unity CSIR transfers.

No engine imports and no asset/scene mutations. Supported means "a generator
action exists", NOT equivalent rendering or runtime behavior.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any
import json
import sys

ROOT = Path(__file__).resolve().parents[2]
UNREAL = ROOT / "integrations" / "unreal"
if str(UNREAL) not in sys.path:
    sys.path.insert(0, str(UNREAL))

import csir_plan


def _curves(section: dict[str, Any]) -> list[dict[str, Any]]:
    return list(section.get("payload", {}).get("animation", {}).get("curves", []))


def _track_diagnostics(
    track: dict[str, Any],
    entity: dict[str, Any] | None,
    asset_index: dict[str, dict[str, Any]],
    mapping: dict[str, Any],
) -> tuple[str, list[str]]:
    """Classify one source track without relying on benchmark-specific names."""
    kind = str(track.get("ced_type", ""))
    sections = track.get("sections") or []
    if track.get("muted") is True or not sections:
        return "SKIPPED", ["Muted track or no active sections"]
    if kind == "audio.track":
        missing = [
            str(section.get("payload", {}).get("asset_id", "<missing source asset>"))
            for section in sections
            if not (
                (asset := asset_index.get(section.get("payload", {}).get("asset_id")))
                and mapping.get("assets", {}).get(asset.get("name"))
            )
        ]
        return ("BLOCKED", ["Missing mapped Unreal audio assets: " + ", ".join(missing)]) if missing else ("COVERED", [])

    if kind == "event.trigger":
        # A marked frame is not an executable event and cannot deliver payloads.
        return "PARTIAL", ["Signal preserved as a timeline marker; executable event/payload not transferred"]
    if kind not in {"animation.track", "camera.transform", "camera.cut", "light.animation"}:
        return "BLOCKED", [f"No Unreal adapter for source track kind {kind!r}"]

    if entity is None:
        return "BLOCKED", ["Source binding entity not found in CSIR"]

    name = str(entity.get("name", ""))
    if not mapping.get("entities", {}).get(name, {}).get("actor_label"):
        return "BLOCKED", [f"No mapped Unreal actor for {name!r}"]

    if kind == "camera.cut":
        return "COVERED", []

    if kind == "animation.track" and entity.get("ced_type") == "entity.character":
        missing = []
        for section in sections:
            source_asset = asset_index.get(section.get("payload", {}).get("asset_id"))
            if not source_asset or not mapping.get("assets", {}).get(source_asset.get("name")):
                missing.append(str(section.get("section_id", "<unnamed section>")))
        if missing:
            return "BLOCKED", ["Skeletal source clips without mapped target assets: " + ", ".join(missing)]
        return "PARTIAL", [
            "Skeletal animation sections can be generated, but imported rig/bone pose "
            "equivalence and animation blending require runtime comparison"
        ]

    if kind == "light.animation":
        all_props = {
            str(c.get("canonical_semantic") or c.get("property_name", "")).lower()
            for s in sections for c in _curves(s)
        }
        has_intensity = bool({"light.intensity", "m_intensity", "intensity"} & all_props)
        if not has_intensity:
            return "BLOCKED", ["No supported light intensity curve found"]
        ignored = sorted(all_props - {"light.intensity", "m_intensity", "intensity"})
        if ignored:
            return "PARTIAL", ["Light intensity mapped; additional animated properties not supported: "
                               + ", ".join(ignored)]
        return "PARTIAL", ["Intensity keys reconstructed; photometric/radiometric parity unverified"]

    supported = False
    unknown: set[str] = set()
    for section in sections:
        for c in _curves(section):
            semantic = str(c.get("canonical_semantic", ""))
            native = str(c.get("property_name", ""))
            if (semantic.startswith("transform.position.")
                or semantic.startswith("transform.rotation.")
                or native.lower().startswith(("localeuleranglesraw.", "m_localeulerangleshint."))):
                supported = True
            elif semantic.startswith("transform.") and "offset." in semantic:
                # Static Timeline offsets are handled as part of transform planning.
                continue
            elif kind == "camera.transform" and (
                semantic == "camera.vertical_fov_degrees" or native.lower() == "field of view"
            ):
                supported = True
            else:
                unknown.add(semantic or native or "<unidentified curve>")

    if not supported:
        return "BLOCKED", ["No supported animated transform/camera property in track"]
    if unknown:
        return "PARTIAL", ["Unsupported animation channels: " + ", ".join(sorted(unknown))]
    return "COVERED", []


def audit(csir: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    """Return structured non-mutating readiness plus a full active-track ledger."""
    entities = {e["entity_id"]: e for e in csir.get("entities", [])}
    assets = {a["asset_id"]: a for a in csir.get("assets", [])}
    entries: list[dict[str, Any]] = []

    for index, track in enumerate(csir.get("tracks", [])):
        entity = entities.get(track.get("binding_entity_id", ""))
        state, reasons = _track_diagnostics(track, entity, assets, mapping)
        entries.append({
            "track_index": index,
            "track_id": str(track.get("track_id", f"track:{index}")),
            "track_name": str(track.get("name", "")),
            "track_kind": str(track.get("ced_type", "")),
            "entity_name": entity.get("name", "") if entity else "",
            "sections": len(track.get("sections", [])),
            "state": state,
            "reasons": reasons,
        })

    blockers = [r for r in entries if r["state"] == "BLOCKED"]
    partial = [r for r in entries if r["state"] == "PARTIAL"]
    plan = None
    plan_error = None
    if not blockers:
        try:
            plan = csir_plan.build_plan(csir, mapping)
        except (ValueError, KeyError, TypeError, IndexError, ZeroDivisionError) as exc:
            plan_error = f"{type(exc).__name__}: {exc}"

    # The report states two different truths: whether generation is plausible,
    # and whether the result meets strict fidelity requirements.
    generation = "BLOCKED" if blockers or plan_error else "READY_FOR_ENGINE_PREFLIGHT"
    fidelity = "NOT_ESTABLISHED" if generation != "BLOCKED" else "BLOCKED"
    return {
        "report_kind": "cutsceneai.transfer_readiness",
        "schema_version": "0.1.0",
        "generation": generation,
        "fidelity": fidelity,
        "counts": dict(Counter(row["state"] for row in entries)),
        "source_track_count": len(entries),
        "unaccounted_track_count": 0,  # every input track has an explicit entry
        "target_sequence": mapping.get("sequence_asset_path", ""),
        "overwrite_sequence": bool(mapping.get("overwrite_sequence", False)),
        "plan_error": plan_error,
        "planned_actions": (
            dict(Counter(a["kind"] for a in plan["actions"])) if plan else {}
        ),
        "unverified_behavior_count": len(partial),
        "tracks": entries,
    }


def audit_files(csir_path: str | Path, mapping_path: str | Path) -> dict[str, Any]:
    # utf-8-sig also accepts JSON written by Windows PowerShell.
    source = json.loads(Path(csir_path).read_text(encoding="utf-8-sig"))
    mapping = json.loads(Path(mapping_path).read_text(encoding="utf-8-sig"))
    return audit(source, mapping)
