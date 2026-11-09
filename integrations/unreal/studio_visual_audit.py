"""Read-only visual completeness audit of a generated Studio Level Sequence.

Checks real Unreal material assignments, available illumination/environment,
native camera-cut tracks and skeletal animation tracks. This does NOT render
source-target comparable frames, check audible sound, or mutate the Editor.
"""
from __future__ import annotations

import json
import ntpath
import uuid
from collections import Counter
from pathlib import Path
from typing import Any


class VisualAuditError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    obj = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict):
        raise VisualAuditError("Expected JSON object: " + str(path))
    return obj


def _project(value: str) -> str:
    return ntpath.normcase(ntpath.normpath(str(value).replace("/", "\\")))


def _class(value: Any) -> str:
    try:
        return str(value.get_class().get_name())
    except Exception:
        return ""


def _components(actor: Any, api: Any, type_name: str) -> list[Any]:
    klass = getattr(api, type_name, None)
    getter = getattr(actor, "get_components_by_class", None)
    if klass is None or not callable(getter):
        return []
    try:
        return list(getter(klass) or [])
    except Exception:
        return []


def inspect_scene(
    api: Any, sequence: Any, planned_actor_labels: set[str],
    *, source_directional_light_required: bool | None = None,
) -> dict[str, Any]:
    """All counts are native Unreal observations; unknown API => unknown, not PASS."""
    actor_subsystem = api.get_editor_subsystem(api.EditorActorSubsystem)
    all_actors = list(actor_subsystem.get_all_level_actors())
    types = Counter(_class(a) for a in all_actors)
    actors: list[dict[str, Any]] = []
    material_slots = 0
    no_material_slots = 0
    default_material_slots = 0
    imported_or_custom_material_slots = 0
    editor_proxy_slots = 0
    editor_proxy_details: list[dict[str, Any]] = []
    character_material_slots = 0
    character_default_slots = 0
    character_empty_slots = 0
    character_nondefault_slots = 0
    for actor in all_actors:
        name = str(actor.get_actor_label())
        if name not in planned_actor_labels:
            continue
        renderer_list = (
            _components(actor, api, "SkeletalMeshComponent")
            + _components(actor, api, "StaticMeshComponent")
        )
        for component in renderer_list:
            # Unreal's CineCameraActor uses a CameraProxyMeshComponent for
            # editor visualization. Its MI_CineMat_* materials are NOT
            # transferred scene art and must not inflate fidelity counts.
            component_class = _class(component)
            if component_class == "CameraProxyMeshComponent" or (
                _class(actor) == "CineCameraActor"
                and component_class in {"StaticMeshComponent", "CameraProxyMeshComponent"}
            ):
                getter = getattr(component, "get_num_materials", None)
                slots = None
                if callable(getter):
                    try:
                        slots = int(getter())
                        editor_proxy_slots += slots
                    except Exception:
                        pass
                editor_proxy_details.append({
                    "actor_label": name,
                    "component_class": component_class,
                    "material_status": "EDITOR_CAMERA_PROXY_EXCLUDED_FROM_SCENE_MATERIAL_FIDELITY",
                    "material_slots": slots,
                })
                continue
            is_character = component_class == "SkeletalMeshComponent"
            getter = getattr(component, "get_num_materials", None)
            material_getter = getattr(component, "get_material", None)
            if not callable(getter) or not callable(material_getter):
                actors.append({
                    "actor_label": name, "component_class": _class(component),
                    "material_status": "NATIVE_MATERIAL_ENUMERATION_UNAVAILABLE",
                })
                continue
            try:
                slots = int(getter())
            except Exception:
                actors.append({
                    "actor_label": name, "component_class": _class(component),
                    "material_status": "NATIVE_MATERIAL_ENUMERATION_FAILED",
                })
                continue
            materials = []
            for index in range(slots):
                try:
                    obj = material_getter(index)
                    ref = str(obj.get_path_name()) if obj is not None else ""
                except Exception:
                    ref = ""
                material_slots += 1
                if is_character:
                    character_material_slots += 1
                if not ref:
                    no_material_slots += 1
                    if is_character:
                        character_empty_slots += 1
                    status = "MATERIAL_SLOT_EMPTY"
                elif any(token in ref.lower() for token in (
                    "/enginematerials/defaultmaterial",
                    "/enginematerials/worldgridmaterial",
                    "/enginematerials/default",
                )):
                    default_material_slots += 1
                    if is_character:
                        character_default_slots += 1
                    status = "ENGINE_FALLBACK_MATERIAL"
                else:
                    imported_or_custom_material_slots += 1
                    if is_character:
                        character_nondefault_slots += 1
                    status = "MATERIAL_PRESENT_APPEARANCE_UNVERIFIED"
                materials.append({"index": index, "asset": ref, "status": status})
            actors.append({
                "actor_label": name, "component_class": _class(component),
                "material_status": "SLOTS_INSPECTED",
                "materials": materials,
            })
    track_counts: dict[str, int] = {}
    sequence_class = _class(sequence) if sequence is not None else ""
    if sequence_class == "LevelSequence":
        getter = getattr(sequence, "get_tracks", None)
        extensions = getattr(api, "MovieSceneSequenceExtensions", None)
        if not callable(getter):
            getter = getattr(extensions, "get_tracks", None)
            if callable(getter):
                get_tracks = lambda: getter(sequence)
            else:
                get_tracks = None
        else:
            get_tracks = getter
        if get_tracks is not None:
            try:
                for track in get_tracks():
                    key = _class(track)
                    track_counts[key] = track_counts.get(key, 0) + 1
            except Exception:
                track_counts = {"NOT_ENUMERABLE": 0}
        bindings = getattr(sequence, "get_bindings", None)
        if not callable(bindings) and extensions is not None:
            extension = getattr(extensions, "get_bindings", None)
            if callable(extension):
                bindings = lambda: extension(sequence)
        if callable(bindings):
            try:
                for binding in bindings():
                    getter = getattr(binding, "get_tracks", None)
                    if callable(getter):
                        for track in getter():
                            key = _class(track)
                            track_counts[key] = track_counts.get(key, 0) + 1
            except Exception:
                track_counts["BINDING_TRACK_ENUMERATION_FAILED"] = 0
    environment_classes = (
        "SkyLight", "SkyAtmosphere", "DirectionalLight",
        "ExponentialHeightFog", "PostProcessVolume",
        "AtmosphericFog", "VolumetricCloud",
    )
    present_environment = {
        item: sum(1 for cls, count in types.items() if item in cls for _ in range(count))
        for item in environment_classes
    }
    issues = []
    if no_material_slots or default_material_slots:
        issues.append("RENDER_MATERIALS_MISSING_OR_ENGINE_DEFAULT")
    if not present_environment["SkyLight"] and not present_environment["SkyAtmosphere"]:
        issues.append("NO_SKYLIGHT_OR_SKY_ATMOSPHERE_FOUND")
    if not present_environment["DirectionalLight"]:
        issues.append("NO_DIRECTIONAL_LIGHT_FOUND")
    if sequence_class != "LevelSequence":
        issues.append("TARGET_SEQUENCE_MISSING_OR_WRONG_CLASS")
    if track_counts.get("MovieSceneCameraCutTrack", 0) == 0:
        issues.append("NATIVE_CAMERA_CUT_TRACK_NOT_ENUMERATED")
    if track_counts.get("MovieSceneSkeletalAnimationTrack", 0) == 0:
        issues.append("NATIVE_SKELETAL_ANIMATION_TRACK_NOT_ENUMERATED")
    return {
        "status": "VISUAL_COMPLETENESS_REVIEW_REQUIRED" if issues
                  else "NATIVE_VISUAL_PREREQUISITES_PRESENT_PARITY_UNVERIFIED",
        "actor_classes": dict(sorted(types.items())),
        "planned_renderers_inspected": len(actors),
        "renderer_details": actors,
        "editor_camera_proxy_material_slots_excluded": editor_proxy_slots,
        "editor_camera_proxy_details_excluded": editor_proxy_details,
        "character_material_slots": character_material_slots,
        "character_material_slots_engine_default": character_default_slots,
        "character_material_slots_empty": character_empty_slots,
        "character_material_slots_nondefault": character_nondefault_slots,
        "material_slots": material_slots,
        "material_slots_empty": no_material_slots,
        "material_slots_engine_default": default_material_slots,
        "material_slots_nondefault": imported_or_custom_material_slots,
        "environment_actor_counts": present_environment,
        "sequencer_track_counts": track_counts,
        "observed_sequence_class": sequence_class,
        "visual_issues": issues,
        # The Unity CSIR captures Light.type but not complete skybox/ambient
        # settings. Missing target environment actors are observations, not
        # proof that the source required their exact Unreal counterparts.
        "source_directional_light_required": source_directional_light_required,
        "source_sky_ambient_capture_available": False,
        "source_rendering_fidelity_verified": False,
        "skeletal_pose_fidelity_verified": False,
        "audio_fidelity_verified": False,
        "engine_generation_modified": False,
    }


def audit_latest(workspace: Path | None = None, api: Any | None = None) -> dict[str, Any]:
    """Evaluate the currently loaded project/level and persist unique evidence.

    No user-supplied paths inside active-job.json may redirect evidence outside
    the local candidate root. Repeated audits create new report files.
    """
    if api is None:
        import unreal
        api = unreal
    folder = (workspace or (Path.home() / ".cutsceneai-studio" / "runs")).resolve()
    active = _load(folder / "active-job.json")
    job_id = str(active.get("job_id") or "")
    if len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
        raise VisualAuditError("Active job ID is not a 32-character hexadecimal identifier.")
    job = _load(folder / "jobs" / (job_id + ".json"))
    if job.get("job_id") != job_id:
        raise VisualAuditError("Active and saved job identifiers differ.")
    candidate = Path(str(job.get("candidate_dir") or "")).resolve()
    if not candidate.is_relative_to((folder / "candidates").resolve()):
        raise VisualAuditError("Candidate report path is outside the Studio workspace.")
    level = str(api.get_editor_subsystem(
        api.UnrealEditorSubsystem).get_editor_world().get_path_name()).split(".")[0]
    project = str(api.Paths.get_project_file_path())
    tofull = getattr(api.Paths, "convert_relative_path_to_full", None)
    if callable(tofull):
        project = str(tofull(project))
    if level != job.get("expected_level") or _project(project) != _project(
        str(job.get("expected_project") or "")
    ):
        raise VisualAuditError("Loaded Unreal level/project differs from current candidate.")
    plan = _load(candidate / "transfer-plan.json")
    if plan.get("sequence_asset_path") != job.get("sequence_path"):
        raise VisualAuditError("Target sequence does not match the prepared source plan.")
    sequence = api.load_asset(str(job["sequence_path"]))
    # Still record native target observations if a legacy job lacks a
    # source capture; unavailable Unity lighting data means UNKNOWN, not PASS.
    source_path = Path(str(job.get("csir") or ""))
    try:
        source_data = _load(source_path) if source_path.is_file() else {}
    except (OSError, ValueError, TypeError):
        source_data = {}
    source_lights = [
        ((entity.get("metadata") or {}).get("light") or {}).get("light_type")
        for entity in source_data.get("entities", [])
        if isinstance(entity, dict) and entity.get("ced_type") == "entity.light"
    ]
    # An explicit Directional source creates a source-backed requirement.
    # Otherwise use "unknown" unless every source light type is captured.
    required_directional = (
        True if "Directional" in source_lights else
        False if source_lights and all(
            kind in {"Directional", "Point", "Spot"} for kind in source_lights
        ) else None
    )
    observation = inspect_scene(
        api, sequence, set(str(v) for v in (plan.get("bindings") or {}).values()),
        source_directional_light_required=required_directional,
    )
    report = {
        "kind": "cutsceneai.studio.visual_readback_audit",
        "schema_version": "0.1.0",
        "job_id": job_id,
        "candidate_id": job.get("candidate_id"),
        "target_project": project,
        "target_level": level,
        "target_sequence": job["sequence_path"],
        **observation,
    }
    path = candidate / ("visual-audit-" + job_id + "-" + uuid.uuid4().hex[:8] + ".json")
    with path.open("x", encoding="utf-8") as file:
        json.dump(report, file, indent=2)
        file.write("\n")
    log = getattr(api, "log", None)
    if callable(log):
        log(
            "[CutSceneAI Studio] VISUAL: " + report["status"]
            + " | material slots " + str(report["material_slots"])
            + ", default " + str(report["material_slots_engine_default"])
            + ", empty " + str(report["material_slots_empty"])
            + " | issues " + str(len(report["visual_issues"]))
        )
        for issue in report["visual_issues"]:
            log("[CutSceneAI Studio] Visual gap: " + issue)
        log("[CutSceneAI Studio] Visual report: " + str(path))
    return report
