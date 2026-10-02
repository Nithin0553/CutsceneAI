"""Deterministic project-aware CED mapping resolution.

Stable semantic layers:
- CED = engine-neutral meaning
- CSIR = source ground truth
- Project Intelligence Profiles = observed engine/version/project facts
- CSIR adaptive context = cutscene-specific semantic observations
- Resolved Mapping Dictionary = dynamic source/target decision artifact
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping


class MappingResolutionError(ValueError):
    pass


JsonObject = Mapping[str, Any]


def _engine(profile: JsonObject) -> str:
    engine = profile.get("engine", {})
    return str(engine.get("name", "") if isinstance(engine, Mapping) else "").strip().lower()


def _version(profile: JsonObject) -> str:
    engine = profile.get("engine", {})
    return str(engine.get("version", "") if isinstance(engine, Mapping) else "").strip()


def _profile_capabilities(profile: JsonObject) -> set[str]:
    result: set[str] = set()
    for item in profile.get("capabilities", []):
        if not isinstance(item, Mapping):
            continue
        if str(item.get("state", "")).upper() == "SUPPORTED":
            capability_id = str(item.get("id", "")).strip()
            if capability_id:
                result.add(capability_id)
    return result


def _context_capabilities(context: JsonObject | None) -> set[str]:
    if not context:
        return set()
    return {str(value) for value in context.get("observed_capabilities", [])}


def _effective_capabilities(profile: JsonObject, context: JsonObject | None) -> set[str]:
    return _profile_capabilities(profile) | _context_capabilities(context)


def _dotted_get(value: JsonObject, dotted_path: str) -> Any:
    current: Any = value
    for segment in dotted_path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            return None
        current = current[segment]
    return current


def _selector_matches(
    selector: JsonObject,
    profile: JsonObject,
    context: JsonObject | None,
) -> bool:
    engine = selector.get("engine")
    if engine is not None and _engine(profile) != str(engine).strip().lower():
        return False

    version_prefix = selector.get("version_prefix")
    if version_prefix is not None and not _version(profile).startswith(str(version_prefix)):
        return False

    required = {str(item) for item in selector.get("capabilities_all", [])}
    if not required <= _effective_capabilities(profile, context):
        return False

    settings_equals = selector.get("settings_equals", {})
    if isinstance(settings_equals, Mapping):
        settings = profile.get("settings", {})
        settings_map = settings if isinstance(settings, Mapping) else {}
        for path, expected in settings_equals.items():
            if _dotted_get(settings_map, str(path)) != expected:
                return False

    return True


def _selector_specificity(selector: JsonObject) -> int:
    score = 0
    if selector.get("engine") is not None:
        score += 100
    if selector.get("version_prefix") is not None:
        score += 20
    score += 5 * len(selector.get("capabilities_all", []))
    settings = selector.get("settings_equals", {})
    if isinstance(settings, Mapping):
        score += 3 * len(settings)
    return score


def _rule_score(rule: JsonObject) -> int:
    return (
        int(rule.get("priority", 0)) * 1000
        + _selector_specificity(rule.get("source", {}))
        + _selector_specificity(rule.get("target", {}))
    )


def _candidate_rules(
    ced_id: str,
    source_profile: JsonObject,
    target_profile: JsonObject,
    rules: Iterable[JsonObject],
    source_context: JsonObject | None,
    target_context: JsonObject | None,
) -> list[JsonObject]:
    candidates: list[JsonObject] = []
    for rule in rules:
        if str(rule.get("ced", "")) != ced_id:
            continue
        if not _selector_matches(rule.get("source", {}), source_profile, source_context):
            continue
        if not _selector_matches(rule.get("target", {}), target_profile, target_context):
            continue
        candidates.append(rule)
    return sorted(candidates, key=lambda item: (-_rule_score(item), str(item.get("rule_id", ""))))


def _profile_evidence_ids(profile: JsonObject) -> set[str]:
    result: set[str] = set()
    for item in profile.get("evidence", []):
        if isinstance(item, Mapping):
            evidence_id = str(item.get("evidence_id", "")).strip()
            if evidence_id:
                result.add(evidence_id)
    return result


def _context_evidence_ids(context: JsonObject | None) -> set[str]:
    if not context:
        return set()
    result: set[str] = set()
    for observation in context.get("semantic_observations", []):
        if not isinstance(observation, Mapping):
            continue
        for evidence_id in observation.get("evidence_ids", []):
            value = str(evidence_id).strip()
            if value:
                result.add(value)
    return result


def derive_source_context(csir: JsonObject, source_profile_id: str) -> dict[str, Any]:
    """Derive cutscene-specific capabilities/facts from an already-extracted CSIR."""

    observations: list[dict[str, Any]] = []
    observed_capabilities: set[str] = set()

    for entity in csir.get("entities", []):
        if not isinstance(entity, Mapping):
            continue
        if str(entity.get("ced_type", "")) != "entity.camera":
            continue
        metadata = entity.get("metadata", {})
        metadata_map = metadata if isinstance(metadata, Mapping) else {}
        camera = metadata_map.get("camera", {})
        camera_map = camera if isinstance(camera, Mapping) else {}
        transform = metadata_map.get("world_transform", {})
        transform_map = transform if isinstance(transform, Mapping) else {}
        observations.append(
            {
                "subject_id": str(entity.get("entity_id", "")),
                "ced": "camera.transform",
                "facts": {
                    "canonical_rotation": deepcopy(transform_map.get("rotation", {})),
                    "field_of_view_degrees": camera_map.get("field_of_view_degrees"),
                    "observed_aspect": camera_map.get("aspect"),
                    "fov_axis": "vertical",
                },
                "evidence_ids": ["source.camera_basis", "source.camera_fov_axis"],
            }
        )

    for track in csir.get("tracks", []):
        if not isinstance(track, Mapping):
            continue
        if str(track.get("ced_type", "")) != "animation.track":
            continue
        for section in track.get("sections", []):
            if not isinstance(section, Mapping):
                continue
            payload = section.get("payload", {})
            payload_map = payload if isinstance(payload, Mapping) else {}
            animation = payload_map.get("animation", {})
            animation_map = animation if isinstance(animation, Mapping) else {}
            curves = animation_map.get("curves", [])
            root_names = {
                str(curve.get("property_name", ""))
                for curve in curves
                if isinstance(curve, Mapping)
                and str(curve.get("property_name", "")).startswith("RootT.")
            }
            if {"RootT.x", "RootT.y", "RootT.z"} <= root_names:
                observed_capabilities.add("animation.root_motion_curves")
                observations.append(
                    {
                        "subject_id": str(section.get("section_id", "")),
                        "ced": "animation.root_motion",
                        "facts": {
                            "root_translation_curves": ["RootT.x", "RootT.y", "RootT.z"],
                            "source_offset": deepcopy(section.get("source_offset")),
                            "time_scale": section.get("time_scale", 1.0),
                        },
                        "evidence_ids": ["source.root_motion_delta", "source.section_range"],
                    }
                )

    source = csir.get("source", {})
    source_map = source if isinstance(source, Mapping) else {}
    provenance = csir.get("provenance", {})
    provenance_map = provenance if isinstance(provenance, Mapping) else {}

    return {
        "version": "0.1.0",
        "cutscene_id": str(csir.get("cutscene_id", "")),
        "source_project_profile_id": source_profile_id,
        "source_snapshot_hash": str(provenance_map.get("source_snapshot_hash", "")),
        "observed_capabilities": sorted(observed_capabilities),
        "semantic_observations": observations,
        "source_engine": str(source_map.get("engine", "")),
    }


def resolve_dictionary(
    ced_ids: Iterable[str],
    source_profile: JsonObject,
    target_profile: JsonObject,
    rule_set: JsonObject,
    *,
    source_context: JsonObject | None = None,
    target_context: JsonObject | None = None,
    ced_version: str = "0.1.0",
) -> dict[str, Any]:
    """Resolve CED concepts using project analysis plus cutscene-specific evidence."""

    rules = rule_set.get("rules", [])
    if not isinstance(rules, list):
        raise MappingResolutionError("rule_set.rules must be an array")

    known_evidence = (
        _profile_evidence_ids(source_profile)
        | _profile_evidence_ids(target_profile)
        | _context_evidence_ids(source_context)
        | _context_evidence_ids(target_context)
    )

    entries: list[dict[str, Any]] = []
    for ced_id in sorted({str(value) for value in ced_ids}):
        candidates = _candidate_rules(
            ced_id,
            source_profile,
            target_profile,
            rules,
            source_context,
            target_context,
        )
        if not candidates:
            entries.append(
                {
                    "ced": ced_id,
                    "status": "BLOCKED",
                    "outcome": "BLOCKED",
                    "resolver": "unresolved.no_matching_rule",
                    "parameters": {},
                    "evidence": [],
                    "confidence": 0.0,
                }
            )
            continue

        best = candidates[0]
        best_score = _rule_score(best)
        tied = [rule for rule in candidates if _rule_score(rule) == best_score]
        if len(tied) > 1:
            resolutions = {
                (
                    str(rule.get("resolution", {}).get("outcome", "")),
                    str(rule.get("resolution", {}).get("resolver", "")),
                    repr(rule.get("resolution", {}).get("parameters", {})),
                )
                for rule in tied
            }
            if len(resolutions) > 1:
                ids = ", ".join(str(rule.get("rule_id", "")) for rule in tied)
                raise MappingResolutionError(
                    f"Ambiguous adaptive mapping for {ced_id}: equal-specificity rules {ids}"
                )

        resolution = best.get("resolution", {})
        required_evidence = [str(item) for item in resolution.get("required_evidence", [])]
        observed_required = [item for item in required_evidence if item in known_evidence]
        missing_evidence = [item for item in required_evidence if item not in known_evidence]
        confidence = 1.0 if not required_evidence else len(observed_required) / len(required_evidence)

        outcome = str(resolution.get("outcome", "BLOCKED"))
        if outcome == "BLOCKED":
            status = "BLOCKED"
        elif missing_evidence:
            status = "NEEDS_EVIDENCE"
        else:
            status = "RESOLVED"

        parameters = deepcopy(resolution.get("parameters", {}))
        if missing_evidence:
            parameters["missing_evidence"] = missing_evidence

        entries.append(
            {
                "ced": ced_id,
                "status": status,
                "outcome": outcome,
                "resolver": str(resolution.get("resolver", "unresolved.invalid_rule")),
                "rule_id": str(best.get("rule_id", "")),
                "parameters": parameters,
                "evidence": observed_required,
                "confidence": confidence,
            }
        )

    return {
        "version": "0.1.0",
        "source_profile_id": str(source_profile.get("profile_id", "")),
        "target_profile_id": str(target_profile.get("profile_id", "")),
        "ced_version": ced_version,
        "entries": entries,
    }
