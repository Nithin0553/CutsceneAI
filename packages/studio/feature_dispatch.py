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
import math
import re
from collections import Counter
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    "skeletal_world_root_lock", "actor_visibility", "property_float",
    "property_bool", "collider_primitive_shape",
})
COMPONENT_ACTIONS = frozenset({"property_bool", "property_float", "collider_primitive_shape"})
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
    "event.state": ("actor_visibility",),
    "scene.visibility": ("actor_visibility",),
    "camera.postprocess": ("property_float",),
    "light.shadow": ("property_bool",),
    "metadata.property_descriptor": ("property_float", "property_bool"),
    "physics.collider": ("collider_primitive_shape",),
}
LOSSY_ACTION_SEMANTICS = frozenset({
    "event.trigger", "event.state", "light.animation", "audio.track", "audio.section",
})

FEATURE_STATES = frozenset({
    "NOT_ENCOUNTERED", "SOURCE_RECORDED_ADAPTER_MISSING",
    "NATIVE_ACTION_PLANNED_UNVERIFIED", "LOSSY_ACTION_PLANNED_UNVERIFIED",
    "NATIVE_ACTION_HANDLER_MISSING", "CUSTOM_HANDLER_REGISTERED_UNVERIFIED",
    "REGISTERED_ADAPTER_NOT_EXECUTED",
})
VALID_STAGE = frozenset({"SOURCE", "PLAN", "NATIVE_READBACK", "BEHAVIOR"})
SOURCE_KINDS = frozenset({"assets", "entities", "tracks", "sections", "curves",
                          "relationships"})
_NATIVE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_SOURCE_LOCATION = re.compile(
    r"^(assets|entities|tracks|relationships)\[(\d+)\]"
    r"(?:\.sections\[(\d+)\](?:\.payload\.animation\.curves\[(\d+)\])?)?$"
)


class FeatureDispatchError(ValueError):
    pass


class ComponentEvidenceError(ValueError):
    """An installed adapter cannot use this particular source occurrence."""


@dataclass(frozen=True)
class ComponentAdapter:
    adapter_id: str
    version: str
    source_type: str
    source_assembly: str
    semantic: str
    source_versions: tuple[str, ...]
    target_versions: tuple[str, ...]
    target_classes: tuple[str, ...]
    action_kind: str
    strategy: str
    required_fields: tuple[str, ...]
    dependency_fields: tuple[str, ...]
    preflight: str
    readback: str
    behavior: str
    unsupported_properties: tuple[str, ...]
    planner: Callable[..., dict[str, Any]]
    source_package: str = ""
    source_package_versions: tuple[str, ...] = ()

    def describe(self) -> dict[str, Any]:
        """Data-only capabilities for reports and agent discovery."""
        return {
            "adapter_id": self.adapter_id, "version": self.version,
            "source_type": self.source_type, "source_assembly": self.source_assembly,
            "source_package": self.source_package,
            "source_package_versions": list(self.source_package_versions),
            "semantic": self.semantic, "source_unity_versions": list(self.source_versions),
            "target_unreal_versions": list(self.target_versions),
            "target_classes": list(self.target_classes), "action_kind": self.action_kind,
            "strategy": self.strategy, "required_fields": list(self.required_fields),
            "dependency_fields": list(self.dependency_fields),
            "permission": "existing_guarded_studio_transfer",
            "preflight": self.preflight,
            "failure_policy": "report_without_substitution",
            "readback": self.readback, "behavior": self.behavior,
            "unsupported_properties": list(self.unsupported_properties),
        }


def engine_version_family(version: str) -> str:
    """Read major.minor from Unity and Unreal version strings with build suffixes."""
    match = re.match(r"^(\d+\.\d+)(?:[.a-zA-Z+\-]|$)", version)
    return match[1] if match else ""


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



def verify_executable_actions(plan: Mapping[str, Any]) -> None:
    """Reject unknown builder actions before an Unreal Editor mutation starts."""
    actions = plan.get("actions")
    if not isinstance(actions, list):
        raise FeatureDispatchError("Transfer plan requires a list of native actions.")
    for position, row in enumerate(actions):
        if not isinstance(row, dict):
            raise FeatureDispatchError("Invalid native action at index " + str(position))
        kind = row.get("kind")
        if kind not in BUILDER_ACTIONS:
            raise FeatureDispatchError(
                "No executable Unreal builder handler for action " + str(kind) +
                " at index " + str(position) +
                "; register/implement its target adapter before generation."
            )


def _validate_scalar_adapter_action(
    action: Mapping[str, Any], mapping: Mapping[str, Any], semantic: str,
) -> None:
    """Validate a plugin's existing Unreal scalar builder contract before handoff."""
    if action.get("source_semantic") != semantic:
        raise FeatureDispatchError("Scalar CED adapter must preserve its source semantic.")
    if action.get("target_scope") not in {"actor", "component"}:
        raise FeatureDispatchError("Scalar CED adapter requires actor/component target scope.")
    if any(not isinstance(action.get(key), str) or
           not _NATIVE_IDENTIFIER.fullmatch(action[key])
           for key in ("target_class", "target_property_name")):
        raise FeatureDispatchError("Scalar CED adapter requires native target identifiers.")
    if action.get("target_property_path") != action["target_property_name"]:
        raise FeatureDispatchError("Nested Unreal scalar properties need a distinct adapter.")
    native = action.get("native_property_name")
    if native is not None and (not isinstance(native, str) or not _NATIVE_IDENTIFIER.fullmatch(native)):
        raise FeatureDispatchError("Scalar CED adapter native property name must be an identifier.")
    entity = mapping.get("entities", {}).get(action.get("entity_name"))
    if (not isinstance(entity, dict) or not entity.get("actor_label")
        or entity["actor_label"] != action.get("actor_label")):
        raise FeatureDispatchError("Scalar CED adapter target actor is not source mapped.")
    keys = action.get("keys")
    if not isinstance(keys, list) or not keys:
        raise FeatureDispatchError("Scalar CED adapter needs source-derived native keys.")
    previous = -1
    for key in keys:
        if not isinstance(key, dict) or type(key.get("frame")) is not int:
            raise FeatureDispatchError("Scalar CED adapter frame is not an integer.")
        frame = key["frame"]
        if frame <= previous:
            raise FeatureDispatchError("Scalar CED adapter frames must increase from zero.")
        previous = frame
        value = key.get("value")
        if action["kind"] == "property_bool":
            if type(value) is not bool:
                raise FeatureDispatchError("Scalar Boolean CED adapter needs Boolean values.")
        else:
            try:
                finite = type(value) in {int, float} and math.isfinite(value)
            except OverflowError:
                finite = False
            if not finite:
                raise FeatureDispatchError("Scalar float CED adapter needs finite numeric values.")


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
                "source_name": str(obj.get("name") or ""),
                "ced": semantic,
                "source_native_type": str(native.get("native_type") or
                                          native.get("asset_type") or ""),
                "kind": collection,
                "_source_payload": obj,
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
                    "source_name": str(obj.get("name") or ""),
                    "ced": str(section.get("ced_type") or ""),
                    "source_native_type": str(
                        (section.get("native_payload") or {}).get("native_asset_type") or ""),
                    "kind": "sections",
                    "_source_payload": section,
                })
                for curve_index, curve in enumerate(
                    (section.get("payload") or {}).get("animation", {}).get("curves", [])
                ):
                    if not isinstance(curve, dict):
                        continue
                    rows.append({
                        "source_location": f"{sect_path}.payload.animation.curves[{curve_index}]",
                        "source_id": str(curve.get("curve_id") or ""),
                        "source_name": str(obj.get("name") or ""),
                        "ced": str(curve.get("canonical_semantic") or ""),
                        "source_native_type": str(curve.get("property_name") or ""),
                        "kind": "curves",
                        "_source_payload": curve,
                    })
    return rows


def _source_at_location(csir: Mapping[str, Any], kind: str, location: str) -> Any:
    match = _SOURCE_LOCATION.fullmatch(location)
    if match is None:
        raise FeatureDispatchError("Invalid source occurrence location for CED adapter.")
    collection, index, section_index, curve_index = match.groups()
    expected_kind = "curves" if curve_index is not None else (
        "sections" if section_index is not None else collection
    )
    if kind != expected_kind or (section_index is not None and collection != "tracks"):
        raise FeatureDispatchError("CED adapter source kind does not match source location.")
    try:
        source = csir[collection][int(index)]
        if section_index is not None:
            source = source["sections"][int(section_index)]
        if curve_index is not None:
            source = source["payload"]["animation"]["curves"][int(curve_index)]
    except (KeyError, IndexError, TypeError) as exc:
        raise FeatureDispatchError("CED adapter source occurrence is absent from CSIR.") from exc
    return source


class HandlerRegistry:
    """In-process engine adapter registration, with no dynamic code execution.

    Callers must explicitly register a callable and specify target proof
    requirements; a returned action still needs target native verification.
    External manifests cannot execute arbitrary Python via this registry.
    """

    def __init__(self, features: Mapping[str, Any] | None = None):
        self.features = features if features is not None else catalog()
        self.handlers: dict[str, dict[str, Any]] = {}
        self._components: dict[str, ComponentAdapter] = {}

    def register_component(self, spec: ComponentAdapter) -> None:
        """Register trusted code for an exact native census class."""
        if spec.source_type in self._components or any(
            other.adapter_id == spec.adapter_id for other in self._components.values()
        ):
            raise FeatureDispatchError("Duplicate installed component adapter: " + spec.adapter_id)
        if (not spec.adapter_id or not spec.version or not spec.source_type
                or not spec.source_assembly or not spec.strategy or not callable(spec.planner)
                or not spec.preflight or not spec.readback or not spec.behavior):
            raise FeatureDispatchError("Component adapter metadata and evidence policies are required.")
        if not re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z0-9_]+", spec.semantic):
            raise FeatureDispatchError("Component adapter requires a namespaced CED semantic.")
        if spec.action_kind not in COMPONENT_ACTIONS:
            raise FeatureDispatchError("Component adapter requires an installed native component action.")
        if bool(spec.source_package) != bool(spec.source_package_versions):
            raise FeatureDispatchError("Package adapters require package identity and supported versions.")
        if (not spec.target_classes
                or not all(_NATIVE_IDENTIFIER.fullmatch(name) for name in spec.target_classes)
                or not spec.source_versions or not spec.target_versions
                or not all(re.fullmatch(r"\d+\.\d+", version)
                           for version in (*spec.source_versions, *spec.target_versions))):
            raise FeatureDispatchError("Component adapter class and engine compatibility must be explicit.")
        self._components[spec.source_type] = spec

    def component_for(self, source_type: str) -> ComponentAdapter | None:
        return self._components.get(source_type)

    def component_capabilities(self) -> list[dict[str, Any]]:
        return [spec.describe() for _, spec in sorted(self._components.items())]

    def plan_component(
        self, spec: ComponentAdapter, *, csir: Mapping[str, Any],
        mapping: Mapping[str, Any], row: Mapping[str, Any], target: Mapping[str, Any],
        location: str, package_versions: Mapping[str, list[str]],
    ) -> dict[str, Any]:
        """Compile a source-audited occurrence into one allowlisted native action."""
        if self.component_for(str(row.get("component_type") or "")) is not spec:
            raise FeatureDispatchError("Source component adapter is not installed.")
        if row.get("component_assembly") != spec.source_assembly:
            raise ComponentEvidenceError("SOURCE_COMPONENT_ASSEMBLY_UNSUPPORTED")
        if spec.source_package and (
            row.get("component_package") != spec.source_package
            or row.get("component_package_version") not in spec.source_package_versions
        ):
            raise ComponentEvidenceError("SOURCE_COMPONENT_PACKAGE_OR_VERSION_UNSUPPORTED")
        if spec.source_package and package_versions.get(spec.source_package) != [
            row["component_package_version"]
        ]:
            raise ComponentEvidenceError("INSTALLED_SOURCE_PACKAGE_IDENTITY_REQUIRED")
        target_version = mapping.get("target_engine_version")
        if target_version and engine_version_family(str(target_version)) not in spec.target_versions:
            raise ComponentEvidenceError("TARGET_ENGINE_VERSION_UNSUPPORTED")
        if engine_version_family(str(csir["source"].get("engine_version") or "")) not in (
            spec.source_versions
        ):
            raise ComponentEvidenceError("SOURCE_ENGINE_VERSION_UNSUPPORTED")
        source_id = row.get("component_global_id")
        if (not isinstance(source_id, str) or not source_id.strip()
                or not target.get("native_ref")
                or row.get("global_object_id") != target["native_ref"]):
            raise ComponentEvidenceError("EXACT_SOURCE_COMPONENT_IDENTITY_REQUIRED")
        values = row.get("feature")
        if not isinstance(values, Mapping) or any(values.get(field) is None
                                                   for field in spec.required_fields):
            raise ComponentEvidenceError("REQUIRED_SOURCE_COMPONENT_FIELDS_MISSING")
        if any(not values.get(field) for field in spec.dependency_fields):
            raise ComponentEvidenceError("REQUIRED_SOURCE_COMPONENT_DEPENDENCY_MISSING")
        action = spec.planner(deepcopy(csir), deepcopy(mapping), deepcopy(row), deepcopy(target))
        if (not isinstance(action, dict) or action.get("kind") != spec.action_kind
                or action.get("target_class") not in spec.target_classes
                or action.get("source_behavior_strategy") != spec.strategy
                or action.get("entity_name") != target["name"]
                or action.get("actor_label") != target["actor_label"]):
            raise FeatureDispatchError("Component adapter emitted an undeclared native action.")
        if spec.action_kind in {"property_float", "property_bool"}:
            _validate_scalar_adapter_action(action, mapping, spec.semantic)
        fidelity = action.get("fidelity_status")
        if (not isinstance(fidelity, str) or not fidelity.endswith("_UNVERIFIED")
                or action.get("target_readback_verified") is True
                or action.get("behavior_fidelity_verified") is True):
            raise FeatureDispatchError("Component adapter cannot claim native or behavioral proof.")
        result = {
            **action, "source_component_type": spec.source_type,
            "source_component_id": source_id, "source_entity_id": target["entity_id"],
            "source_object_id": target["native_ref"],
            "source_ced": spec.semantic, "source_location": location,
            "adapter_name": spec.adapter_id, "adapter_version": spec.version,
            "target_engine_versions": list(spec.target_versions),
            "required_evidence_gates": ["SOURCE", "PLAN", "NATIVE_READBACK", "BEHAVIOR"],
            "target_readback_verified": False, "behavior_fidelity_verified": False,
            "release_eligible": False,
        }
        try:
            json.dumps(result, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise FeatureDispatchError("Component adapter emitted invalid JSON.") from exc
        return result

    def register(self, semantic: str, handler: Callable[..., Any], *,
                 name: str, version: str,
                 requires: tuple[str, ...] = ("SOURCE", "PLAN", "NATIVE_READBACK", "BEHAVIOR"),
                 source_kinds: tuple[str, ...] = (),
                 builder_actions: tuple[str, ...] = (),
                 ) -> None:
        # Plugins may introduce new namespaced CED semantics without requiring
        # a source-project dictionary rewrite. Registration is explicit,
        # never inferred from an arbitrary source payload.
        if not re.fullmatch(r"[a-z][a-z0-9_]*\.[a-z0-9_]+", semantic):
            raise FeatureDispatchError("Handler must use a namespaced CED semantic: " + semantic)
        if semantic in self.handlers:
            raise FeatureDispatchError("Duplicate handler for CED semantic: " + semantic)
        if not callable(handler) or not name.strip() or not version.strip():
            raise FeatureDispatchError("Handler must be callable with name and version.")
        if not requires or any(item not in VALID_STAGE for item in requires):
            raise FeatureDispatchError("Handler must declare valid evidence gates.")
        if "NATIVE_READBACK" not in requires or "BEHAVIOR" not in requires:
            raise FeatureDispatchError("Cannot declare an adapter without native-readback and behavior evidence proof.")
        if bool(source_kinds) != bool(builder_actions):
            raise FeatureDispatchError("Executable adapters require source kinds and builder actions.")
        if set(source_kinds) - SOURCE_KINDS or set(builder_actions) - BUILDER_ACTIONS:
            raise FeatureDispatchError("Adapter source kind or native builder action is not implemented.")
        if source_kinds and set(requires) != VALID_STAGE:
            raise FeatureDispatchError("Executable CED adapters require all four evidence gates.")
        self.handlers[semantic] = {
            "name": name, "version": version, "requires": list(requires),
            "handler": handler, "source_kinds": tuple(source_kinds),
            "builder_actions": tuple(builder_actions),
        }

    def plan_for(
        self, csir: Mapping[str, Any], mapping: Mapping[str, Any],
        source: Mapping[str, Any], *, kind: str, location: str,
    ) -> list[dict[str, Any]]:
        """Run one code-registered adapter and bind its actions to exact source evidence.

        Registration alone cannot mark a source converted. Only an explicit
        builder action emitted here reaches the normal Unreal preflight and
        immutable-plan checks. Source JSON never selects executable Python.
        """
        semantic = str((source.get("canonical_semantic") if kind == "curves"
                        else source.get("ced_type")) or "")
        spec = self.handlers.get(semantic)
        if spec is None or kind not in spec["source_kinds"]:
            return []
        if not location or kind not in SOURCE_KINDS:
            raise FeatureDispatchError("Adapter requires an exact source occurrence location.")
        if _source_at_location(csir, kind, location) != source:
            raise FeatureDispatchError("CED adapter source occurrence differs from CSIR.")
        identifier = {
            "assets": "asset_id", "entities": "entity_id", "tracks": "track_id",
            "sections": "section_id", "curves": "curve_id",
            "relationships": "relationship_id",
        }[kind]
        source_id = str(source.get(identifier) or "")
        # The implementation is trusted code installed with the planner. A
        # copy prevents a buggy adapter from changing the caller's source.
        try:
            proposed = spec["handler"](deepcopy(csir), deepcopy(mapping), deepcopy(source))
        except FeatureDispatchError:
            raise
        except Exception as exc:
            raise FeatureDispatchError(
                "CED adapter failed for " + semantic + " at " + location + ": " + str(exc)
            ) from exc
        if not isinstance(proposed, list):
            raise FeatureDispatchError("CED adapter must return a list of native actions.")
        actions = []
        for action in proposed:
            if not isinstance(action, dict) or action.get("kind") not in spec["builder_actions"]:
                raise FeatureDispatchError("CED adapter emitted an undeclared native action.")
            if not isinstance(action.get("source_behavior_strategy"), str) or not action[
                "source_behavior_strategy"
            ].strip():
                raise FeatureDispatchError("CED adapter must describe its source behavior strategy.")
            if action["kind"] in {"property_float", "property_bool"}:
                _validate_scalar_adapter_action(action, mapping, semantic)
            fidelity = action.get("fidelity_status", "NATIVE_READBACK_AND_BEHAVIOR_UNVERIFIED")
            if not isinstance(fidelity, str) or not fidelity.endswith("_UNVERIFIED"):
                raise FeatureDispatchError("CED adapter cannot claim fidelity before engine evidence.")
            if (action.get("source_location", location) != location
                or action.get("source_id", source_id) != source_id
                or action.get("source_ced", semantic) != semantic
                or action.get("target_readback_verified") is True
                or action.get("behavior_fidelity_verified") is True):
                raise FeatureDispatchError("CED adapter attempted to override source identity or verification.")
            covered_ids = action.get("covered_source_section_ids", [])
            if not isinstance(covered_ids, list) or any(
                not isinstance(item, str) or not item for item in covered_ids
            ):
                raise FeatureDispatchError("CED adapter section coverage must use source IDs.")
            covered_locations = []
            if covered_ids:
                if kind != "tracks" or len(set(covered_ids)) != len(covered_ids):
                    raise FeatureDispatchError("Ambiguous source section coverage declaration.")
                sections = source.get("sections") or []
                if not isinstance(sections, list):
                    raise FeatureDispatchError("Source track sections are malformed.")
                indexed = [(str(section.get("section_id") or ""), index)
                           for index, section in enumerate(sections)
                           if isinstance(section, dict) and section.get("ced_type") == semantic]
                if len({item for item, _ in indexed}) != len(indexed):
                    raise FeatureDispatchError("Duplicate source section ID cannot prove coverage.")
                by_id = dict(indexed)
                if set(covered_ids) - set(by_id):
                    raise FeatureDispatchError("CED adapter claimed an unknown source section.")
                covered_locations = [f"{location}.sections[{by_id[item]}]"
                                     for item in covered_ids]
            row = deepcopy(action)
            row.update({"source_location": location, "source_id": source_id,
                        "source_ced": semantic, "adapter_name": spec["name"],
                        "adapter_version": spec["version"],
                        "covered_source_locations": covered_locations,
                        "required_evidence_gates": list(spec["requires"]),
                        "fidelity_status": action.get(
                            "fidelity_status", "NATIVE_READBACK_AND_BEHAVIOR_UNVERIFIED"),
                        "target_readback_verified": False,
                        "behavior_fidelity_verified": False})
            try:
                json.dumps(row, allow_nan=False)
            except (TypeError, ValueError) as exc:
                raise FeatureDispatchError("CED adapter emitted non-JSON or nonfinite action.") from exc
            actions.append(row)
        return actions

    def plan_other_occurrences(
        self, csir: Mapping[str, Any], mapping: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        """Compile registered entity, asset, section, curve and relationship adapters."""
        actions = []
        for item in _source_rows(csir):
            if item["kind"] == "tracks":
                continue  # Track adapters run in the per-track outcome ledger.
            actions.extend(self.plan_for(
                csir, mapping, item["_source_payload"],
                kind=item["kind"], location=item["source_location"],
            ))
        verify_executable_actions({"actions": actions})
        return actions


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
    # Native actions are attributable only if they point to this source
    # track/entity. A camera cut in a completely different track cannot
    # make every same-CED source feature appear planned.
    attributed_actions: dict[str, set[str]] = {}
    executed_adapters: set[tuple[str, str, str]] = set()
    name_counts = Counter(
        (row["kind"], row["source_name"]) for row in _source_rows(csir)
        if row["kind"] in {"tracks", "entities"} and row["source_name"]
    )
    for action in actions:
        if not isinstance(action, dict):
            continue
        kind = str(action.get("kind") or "")
        exact = str(action.get("source_location") or "")
        if exact:
            for location in (exact, *(action.get("covered_source_locations") or [])):
                attributed_actions.setdefault(location, set()).add(kind)
                if action.get("adapter_name") and action.get("adapter_version"):
                    executed_adapters.add((location, str(action["adapter_name"]),
                                           str(action["adapter_version"])))
            continue
        for source_kind, key in (("entities", "entity_name"), ("tracks", "track_name")):
            name = str(action.get(key) or "")
            if name and name_counts[(source_kind, name)] == 1:
                attributed_actions.setdefault(source_kind + ":" + name, set()).add(kind)
    observed = _source_rows(csir)
    rows = []
    for item in observed:
        semantic = item["ced"]
        candidate = recipe(semantic, features=features)
        scope = item.get("source_name", "")
        applicable = attributed_actions.get(item["source_location"], set())
        if item["kind"] in {"entities", "tracks"} and scope:
            applicable |= attributed_actions.get(item["kind"] + ":" + scope, set())
        handler = handlers.handlers.get(semantic) if handlers is not None else None
        allowed_actions = set(candidate.get("potential_builder_actions", ()))
        if handler and item["kind"] in handler["source_kinds"]:
            allowed_actions.update(handler["builder_actions"])
        executable = sorted(allowed_actions & applicable)
        if handler and executable and (
            item["source_location"], handler["name"], handler["version"]
        ) in executed_adapters:
            state = "CUSTOM_HANDLER_REGISTERED_UNVERIFIED"
        elif handler:
            state = "REGISTERED_ADAPTER_NOT_EXECUTED"
        elif not candidate["registered"] or not candidate.get("potential_builder_actions"):
            state = "SOURCE_RECORDED_ADAPTER_MISSING"
        elif executable:
            state = ("LOSSY_ACTION_PLANNED_UNVERIFIED" if semantic in LOSSY_ACTION_SEMANTICS
                     else "NATIVE_ACTION_PLANNED_UNVERIFIED")
        else:
            state = "NATIVE_ACTION_HANDLER_MISSING"
        rows.append({
            **{key: value for key, value in item.items() if key != "_source_payload"},
            "state": state,
            "candidate_route": candidate["candidate_route"],
            "potential_builder_actions": sorted(allowed_actions),
            "matching_plan_action_kinds": executable,
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
            "SOURCE_RECORDED_ADAPTER_MISSING", "NATIVE_ACTION_HANDLER_MISSING",
            "REGISTERED_ADAPTER_NOT_EXECUTED"}),
        "unknown_action_kinds": unsupported_actions,
        "full_conversion_verified": False,
        "gates": list(features["evidence_gates"]),
        "note": (
            "CED presence and a proposed conversion route are not proof of a "
            "working adapter. Native actions are planned only; per-feature "
            "readback and source-aligned behavioral comparison remain required."
        ),
    }
