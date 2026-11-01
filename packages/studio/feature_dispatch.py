"""CED v0.2 conversion-path dispatcher and exhaustive feature-accounting contract.

Every canonical CED semantic gets a defined *route*, not an invented target
implementation. The only executable Unreal actions are those implemented by
build_level_sequence.py. A new engine/plugin adapter must explicitly register
its handler, version, required evidence, and native readback policy.

This module is pure Python and never mutates source or destination projects.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Mapping

CATALOG_PATH = (Path(__file__).resolve().parents[1] / "contracts"
                / "dictionary" / "cutscene-elements-v0.2.json")

# A candidate conversion route is NOT executable conversion support.
# Category-level routes keep the dictionary exhaustive without false claims.
ROUTES = {
    "timeline_native": frozenset({
        "sequence", "timeline", "time", "curve", "binding", "camera", "light",
        "animation", "audio", "event", "subtitle", "dialogue", "media",
    }),
    "asset_import": frozenset({
        "mesh", "geometry", "texture", "material", "asset", "dependency",
        "format", "sprite", "prefab",
    }),
    "scene_reconstruction": frozenset({
        "project", "world", "object", "entity", "scene", "transform",
        "relationship", "constraint", "character", "rig", "terrain",
        "environment",
    }),
    "evaluated_cache_or_adapter": frozenset({
        "facial", "vfx", "physics", "simulation", "cloth", "hair", "fluid",
        "destruction", "postprocess", "shadow", "render", "procedural",
    }),
    "runtime_plugin_adapter": frozenset({
        "script", "gameplay", "interaction", "ui", "input", "xr", "mocap",
        "navigation", "ai", "network", "platform", "shader", "plugin",
    }),
    "source_metadata_preservation": frozenset({
        "metadata", "localization", "delivery", "provenance",
    }),
}

# The existing native builder creates ONLY these actions; must not be
# conflated with feature-specific semantic or playback verification.
BUILDER_ACTIONS = frozenset({
    "camera_setup", "camera_cut", "camera_fov", "transform",
    "skeletal_animation", "light_intensity", "audio", "marker",
    "skeletal_world_root_lock",
})
# Each association is a source-track/Sequencer building *candidate*, not
# a guaranteed semantic equivalent (event -> marker is deliberately lossy).
EXPLICIT_ACTIONS = {
    "sequence.root": ("camera_cut", "transform", "skeletal_animation", "audio"),
    "entity.camera": ("camera_setup",),
    "entity.character": ("skeletal_animation",),
    "entity.light": ("light_intensity",),
    "camera.transform": ("transform",),
    "camera.cut": ("camera_cut",),
    "camera.fov": ("camera_fov",),
    "animation.track": ("transform", "skeletal_animation"),
    "animation.section": ("skeletal_animation", "transform"),
    "transform.position": ("transform",),
    "transform.rotation": ("transform",),
    "light.intensity": ("light_intensity",),
    "light.animation": ("light_intensity",),
    "audio.track": ("audio",),
    "audio.section": ("audio",),
    "event.trigger": ("marker",),
}
LOSSY_ACTION_SEMANTICS = frozenset({"event.trigger", "light.animation", "audio.track", "audio.section"})

FEATURE_STATES = frozenset({
    "NOT_ENCOUNTERED", "SOURCE_RECORDED_ADAPTER_MISSING",
    "NATIVE_ACTION_PLANNED_UNVERIFIED", "LOSSY_ACTION_PLANNED_UNVERIFIED",
    "NATIVE_ACTION_HANDLER_MISSING", "CUSTOM_HANDLER_REGISTERED_UNVERIFIED",
})
VALID_STAGE = frozenset({"SOURCE", "PLAN", "NATIVE_READBACK", "BEHAVIOR"})


class FeatureDispatchError(ValueError):
    pass


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def catalog(catalog_path: Path = CATALOG_PATH) -> dict[str, Any]:
    value = json.loads(catalog_path.read_text(encoding="utf-8-sig"))
    if value.get("version") != "0.2.0":
        raise FeatureDispatchError("Expected CED v0.2.0 feature catalog.")
    categories = value.get("categories")
    if not isinstance(categories, dict):
        raise FeatureDispatchError("CED v0.2 categories missing.")
    seen = set()
    domain_for = {}
    for prefix, concepts in categories.items():
        if not isinstance(concepts, list):
            raise FeatureDispatchError("Invalid CED concept list: " + str(prefix))
        for semantic in concepts:
            if not isinstance(semantic, str) or semantic in seen:
                raise FeatureDispatchError("Duplicate/invalid CED semantic: " + str(semantic))
            if not re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z0-9_]+", semantic):
                raise FeatureDispatchError("Invalid CED canonical semantic: " + semantic)
            seen.add(semantic)
            domain_for[semantic] = prefix
    routes = {key: route for route, domains in ROUTES.items() for key in domains}
    if set(categories) - set(routes):
        raise FeatureDispatchError("No route for CED domains: " +
                                   ", ".join(sorted(set(categories) - set(routes))))
    families = value.get("feature_families", [])
    if len(families) != 39:
        raise FeatureDispatchError("Expected 39 documented game-engine feature families.")
    used_domains = {item for row in families for item in row["ced_domains"]}
    if set(categories) - used_domains:
        raise FeatureDispatchError("Uncategorized CED domains: " +
                                   ", ".join(sorted(set(categories) - used_domains)))
    value["_domain_for"] = domain_for
    value["_route_for"] = routes
    value["_sha256"] = _sha(catalog_path)
    return value


def recipe(semantic: str, *, features: Mapping[str, Any] | None = None) -> dict[str, Any]:
    value = features if features is not None else catalog()
    prefix = value["_domain_for"].get(semantic)
    if prefix is None:
        return {
            "ced": semantic, "registered": False, "candidate_route": "plugin_required",
            "executable_handler": None, "fidelity_verified": False,
            "evidence_gates": list(value["evidence_gates"]),
            "preserve_source_native_payload": True,
        }
    actions = list(EXPLICIT_ACTIONS.get(semantic, ()))
    return {
        "ced": semantic, "registered": True, "candidate_route": value["_route_for"][prefix],
        "potential_builder_actions": actions,
        "executable_handler": None,
        "fidelity_verified": False, "evidence_gates": list(value["evidence_gates"]),
        "preserve_source_native_payload": True,
    }


def _source_rows(csir: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Inventory assets, entities, tracks, sections, channels, relationships.

    Each source occurrence is distinct even when its CED concept repeats.
    Source metadata and plugin-native types are retained as native descriptors
    so unrecognized extension classes are not silently discarded.
    """
    rows = []
    for collection, identifier in (
        ("assets", "asset_id"), ("entities", "entity_id"),
        ("tracks", "track_id"), ("relationships", "relationship_id"),
    ):
        for index, obj in enumerate(csir.get(collection, [])):
            if not isinstance(obj, dict):
                continue
            semantic = str(obj.get("ced_type") or "")
            native = obj.get("metadata") or {}
            row = {
                "source_location": f"{collection}[{index}]",
                "source_id": str(obj.get(identifier) or ""),
                "ced": semantic,
                "source_native_type": str(native.get("native_type") or
                                          native.get("asset_type") or ""),
                "kind": collection,
            }
            rows.append(row)
            if collection != "tracks":
                continue
            for section_index, section in enumerate(obj.get("sections", [])):
                if not isinstance(section, dict):
                    continue
                sect_path = f"tracks[{index}].sections[{section_index}]"
                rows.append({
                    "source_location": sect_path,
                    "source_id": str(section.get("section_id") or ""),
                    "ced": str(section.get("ced_type") or ""),
                    "source_native_type": str(
                        (section.get("native_payload") or {}).get("native_asset_type") or ""),
                    "kind": "sections",
                })
                for curve_index, curve in enumerate(
                    (section.get("payload") or {}).get("animation", {}).get("curves", [])
                ):
                    if not isinstance(curve, dict):
                        continue
                    rows.append({
                        "source_location": f"{sect_path}.payload.animation.curves[{curve_index}]",
                        "source_id": str(curve.get("curve_id") or ""),
                        "ced": str(curve.get("canonical_semantic") or ""),
                        "source_native_type": str(curve.get("property_name") or ""),
                        "kind": "curves",
                    })
    return rows


class HandlerRegistry:
    """In-process engine adapter registration, with no dynamic code execution.

    Callers must explicitly register a callable and specify target proof
    requirements; a returned action still needs target native verification.
    External manifests cannot execute arbitrary Python via this registry.
    """

    def __init__(self, features: Mapping[str, Any] | None = None):
        self.features = features if features is not None else catalog()
        self.handlers: dict[str, dict[str, Any]] = {}

    def register(self, semantic: str, handler: Callable[..., Any], *,
                 name: str, version: str,
                 requires: tuple[str, ...] = ("SOURCE", "PLAN", "NATIVE_READBACK", "BEHAVIOR")
                 ) -> None:
        if semantic not in self.features["_domain_for"]:
            raise FeatureDispatchError("Register CED semantic before an engine handler: " + semantic)
        if semantic in self.handlers:
            raise FeatureDispatchError("Duplicate handler for CED semantic: " + semantic)
        if not callable(handler) or not name.strip() or not version.strip():
            raise FeatureDispatchError("Handler must be callable with name and version.")
        if not requires or any(item not in VALID_STAGE for item in requires):
            raise FeatureDispatchError("Handler must declare valid evidence gates.")
        if "NATIVE_READBACK" not in requires or "BEHAVIOR" not in requires:
            raise FeatureDispatchError("Cannot declare an adapter without native and behavior proof.")
        self.handlers[semantic] = {
            "name": name, "version": version, "requires": list(requires),
            "handler": handler,
        }


def audit(csir: Mapping[str, Any], plan: Mapping[str, Any] | None = None, *,
          features: Mapping[str, Any] | None = None,
          handlers: HandlerRegistry | None = None) -> dict[str, Any]:
    """No silent feature loss: every extracted semantic remains in the ledger.

    A planned native action only marks a construction candidate. This routine
    NEVER mutates Unreal nor awards real-engine success.
    """
    features = features if features is not None else catalog()
    actions = plan.get("actions", []) if plan is not None else []
    if not isinstance(actions, list):
        raise FeatureDispatchError("Expected list of actions.")
    planned = {str(a.get("kind") or "") for a in actions if isinstance(a, dict)}
    unsupported_actions = sorted(planned - BUILDER_ACTIONS)
    observed = _source_rows(csir)
    rows = []
    for item in observed:
        semantic = item["ced"]
        candidate = recipe(semantic, features=features)
        executable = list(set(candidate.get("potential_builder_actions", ())) & planned)
        handler = handlers.handlers.get(semantic) if handlers is not None else None
        if handler:
            state = "CUSTOM_HANDLER_REGISTERED_UNVERIFIED"
        elif not candidate["registered"] or not candidate.get("potential_builder_actions"):
            state = "SOURCE_RECORDED_ADAPTER_MISSING"
        elif executable:
            state = ("LOSSY_ACTION_PLANNED_UNVERIFIED" if semantic in LOSSY_ACTION_SEMANTICS
                     else "NATIVE_ACTION_PLANNED_UNVERIFIED")
        else:
            state = "NATIVE_ACTION_HANDLER_MISSING"
        rows.append({
            **item,
            "state": state,
            "candidate_route": candidate["candidate_route"],
            "potential_builder_actions": candidate.get("potential_builder_actions", []),
            "matching_plan_action_kinds": sorted(executable),
            "custom_handler": {"name": handler["name"], "version": handler["version"]}
                              if handler else None,
            "target_readback_verified": False,
            "behavior_fidelity_verified": False,
            "source_payload_preserved": True,
        })
    states = Counter(row["state"] for row in rows)
    return {
        "kind": "cutsceneai.studio.feature_dispatch",
        "catalog_version": features["version"],
        "catalog_sha256": features["_sha256"],
        "catalog_semantic_count": len(features["_domain_for"]),
        "catalog_family_count": len(features["feature_families"]),
        "source_occurrence_count": len(rows),
        "accounted_occurrence_count": len(rows),
        "source_occurrences": rows,
        "states": dict(sorted(states.items())),
        "missing_adapter_count": sum(1 for row in rows if row["state"] in {
            "SOURCE_RECORDED_ADAPTER_MISSING", "NATIVE_ACTION_HANDLER_MISSING"}),
        "unknown_action_kinds": unsupported_actions,
        "full_conversion_verified": False,
        "gates": list(features["evidence_gates"]),
        "note": (
            "CED presence and a proposed conversion route are not proof of a "
            "working adapter. Native actions are planned only; per-feature "
            "readback and source-aligned behavioral comparison remain required."
        ),
    }
