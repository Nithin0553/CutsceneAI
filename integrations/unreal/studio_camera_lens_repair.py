"""Guarded, user-scoped static CineCamera focal-length native repair.

The native actor/component must be a newly created exact-source CineCamera.
No camera zoom animation, unknown float-key tracks, arbitrary focal values or
model-supplied Unreal commands. The only edit is a source-derived focal length
for a constant Unity vertical FOV, followed by native property re-read, save,
and deferred independently reopened CineTwin verification.

This module cannot verify actual editor behavior until a real engine test.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
STUDIO = str(ROOT / "packages" / "studio")
CINETWIN = str(ROOT / "packages" / "cinetwin")
for directory in (STUDIO, CINETWIN):
    if directory not in sys.path:
        sys.path.insert(0, directory)

import studio_camera_lens_evidence as evidence
from camera_optics import observe_native_camera


class CameraLensRepairError(ValueError):
    """The current editor is not safe for one static lens correction."""


def _load(path: Path) -> dict:
    return evidence.readback._safe_json(path)[0]


def _float(value: Any) -> float:
    if type(value) not in (float, int) or not math.isfinite(value):
        raise CameraLensRepairError("Native lens field is not finite.")
    return float(value)


def _no_animated_float_keys(api: Any, sequence: Any) -> None:
    """Reject any unknown float control before touching a base camera lens.

    This is intentionally stricter than inspecting a guessed track name:
    any float/property key anywhere in the sequence could be related to
    camera filmback/FOV and may override a static focal length later.
    """
    extensions = getattr(api, "MovieSceneSequenceExtensions", None)
    get_bindings = getattr(extensions, "get_bindings", None)
    if not callable(get_bindings):
        raise CameraLensRepairError("Cannot inspect native Sequencer float keys.")
    try:
        bindings = list(get_bindings(sequence))
        if len(bindings) > 10000:
            raise CameraLensRepairError("Native Sequencer binding list is unbounded.")
        for binding in bindings:
            tracks = list(binding.get_tracks())
            if len(tracks) > 10000:
                raise CameraLensRepairError("Native Sequencer track list is unbounded.")
            for track in tracks:
                kind = str(track.get_class().get_name())
                # A float property or arbitrary property track can override
                # a CineCamera focal length at any frame.
                if ("Float" in kind or "Property" in kind
                        or "Camera" in kind and "Cut" not in kind):
                    raise CameraLensRepairError(
                        "Animated/unknown property controls may own the lens; "
                        "static CineCamera correction is blocked."
                    )
    except CameraLensRepairError:
        raise
    except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
        raise CameraLensRepairError(
            "Native Sequencer key ownership could not be inspected."
        ) from exc


def attempt(api: Any, workspace: Path, job: dict, request: dict) -> dict:
    candidate = Path(job["candidate_dir"]).resolve()
    if (request.get("strategy") != "restore_static_camera_lens"
            or request.get("feedback_id") is None):
        raise CameraLensRepairError("No exact camera repair intent was authorized.")
    feedback_id = str(request.get("feedback_id"))
    if not re.fullmatch(r"[a-f0-9]{32}", feedback_id):
        raise CameraLensRepairError("Camera repair requires an explicit user feedback ID.")
    active = _load(candidate / ("user-feedback-active-" + job["job_id"] + ".json"))
    feedback = _load(candidate / ("user-feedback-" + feedback_id + ".json"))
    if (active.get("feedback_id") != feedback_id
            or active.get("job_id") != job["job_id"]
            or active.get("candidate_id") != job["candidate_id"]
            or feedback.get("kind") != "cutsceneai.studio.user_feedback"
            or feedback.get("feedback_id") != feedback_id
            or feedback.get("job_id") != job["job_id"]
            or feedback.get("candidate_id") != job["candidate_id"]
            or not evidence.message_requests_lens(feedback.get("message"))):
        raise CameraLensRepairError(
            "No current explicit camera-lens request from this user/job."
        )
    original = evidence.build(workspace, job)
    if (request.get("camera_repair_sha256") != original["camera_repair_sha256"]
            or request.get("source_camera_occurrence_id")
            != original["source_camera_occurrence_id"]):
        raise CameraLensRepairError(
            "Original camera evidence changed after the agent selected its repair."
        )
    setup_path = Path(str(job.get("setup_receipt_file") or "")).resolve()
    if (setup_path.parent != candidate or setup_path.is_symlink()
            or not setup_path.is_file()):
        raise CameraLensRepairError("Native newly staged camera receipt is unavailable.")
    setup = _load(setup_path)
    created = [
        row for row in setup.get("actors_created", [])
        if isinstance(row, dict)
        and row.get("kind") == "entity.camera"
        and row.get("name") == original["source_camera_name"]
        and row.get("label") == original["target_actor_label"]
    ]
    if len(created) != 1:
        raise CameraLensRepairError(
            "Only one exact source-provenanced newly staged CineCamera may be changed."
        )
    scene = api.get_editor_subsystem(api.EditorActorSubsystem)
    matches = [
        actor for actor in scene.get_all_level_actors()
        if str(actor.get_actor_label()) == original["target_actor_label"]
    ]
    if len(matches) != 1:
        raise CameraLensRepairError("Native camera actor identity is no longer unique.")
    actor = matches[0]
    if actor.get_attach_parent_actor() is not None:
        raise CameraLensRepairError("Attached cameras require separate rig/transform review.")
    component_getter = getattr(actor, "get_cine_camera_component", None)
    component = component_getter() if callable(component_getter) else None
    if component is None:
        raise CameraLensRepairError("The source camera is not a native CineCameraActor.")
    sequence = api.load_asset(job["sequence_path"])
    if sequence is None:
        raise CameraLensRepairError("Generated Level Sequence is missing.")
    _no_animated_float_keys(api, sequence)
    old = observe_native_camera(actor)
    if old.get("status") != "OBSERVED":
        raise CameraLensRepairError("Native physical lens readback is unavailable.")
    source_height = _float(original["native_sensor_height_mm"])
    old_height = _float(old["sensor_height_mm"])
    source_focal = _float(original["native_focal_before_mm"])
    old_focal = _float(old["focal_length_mm"])
    new_focal = _float(original["native_focal_after_mm"])
    if (abs(old_height - source_height) > 0.01
            or abs(old_focal - source_focal) > 0.05):
        raise CameraLensRepairError(
            "Native camera was modified since the independently sampled baseline."
        )
    # Source frame math alone does not prove this focal length falls inside
    # the REAL CineCameraComponent's lens hardware constraints.
    settings = component.get_editor_property("lens_settings")
    lower = _float(settings.get_editor_property("min_focal_length"))
    upper = _float(settings.get_editor_property("max_focal_length"))
    if not 0 < lower <= new_focal <= upper <= 10000:
        raise CameraLensRepairError(
            "The source physical FOV exceeds the native camera lens constraints."
        )
    # Live source evidence is recomputed BEFORE the edit, not taken from
    # model-chosen numeric parameters or a stale cached user interface.
    if not evidence.message_requests_lens(feedback["message"]):
        raise CameraLensRepairError("User feedback no longer authorizes lens editing.")
    changed = False
    saved = False
    try:
        component.set_editor_property("current_focal_length", new_focal)
        changed = True
        after = observe_native_camera(actor)
        if (after.get("status") != "OBSERVED"
                or abs(_float(after["sensor_height_mm"]) - old_height) > 0.01
                or abs(_float(after["focal_length_mm"]) - new_focal) > 0.05
                or abs(_float(after["vertical_fov_degrees"])
                       - _float(original["target_source_fov_degrees"]))
                > evidence.TOLERANCE_DEGREES):
            raise CameraLensRepairError(
                "Native CineCamera property did not reach the source FOV tolerance."
            )
        import studio_auto_scene
        studio_auto_scene._save_level(api, job["expected_level"])
        saved = True
        return {
            "status": "CAMERA_STATIC_LENS_PROPERTY_SAVED_REOPENED_CINETWIN_PENDING",
            "target_entity": original["source_camera_name"],
            "camera_repair_sha256": original["camera_repair_sha256"],
            "source_camera_occurrence_id": original["source_camera_occurrence_id"],
            "changes": 1,
            "native_fov_error_before_degrees":
                original["measured_native_fov_error_degrees"],
            "native_property_fov_error_after_degrees":
                abs(_float(after["vertical_fov_degrees"])
                    - _float(original["target_source_fov_degrees"])),
            "native_property_readback_verified": True,
            "persistence_after_editor_restart_verified": False,
            "cinetwin_reopened_time_grid_verified_after_repair": False,
            "full_cutscene_fidelity_verified": False,
        }
    finally:
        if changed and not saved:
            # No failed or unmeasured change remains in the open editor.
            component.set_editor_property("current_focal_length", old_focal)
