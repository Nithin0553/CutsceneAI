"""One user-approved static CineCamera world-placement correction.

Checks independent Element 7/8 source/capture provenance, a newly staged
unparented camera, all native Sequencer track owners and the live actor base
position before a single bounded move. Rolls back failed native changes.
Saved properties are NOT a reopened CineTwin or rendered fidelity pass.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for folder in (ROOT / "packages/studio", ROOT / "integrations/unreal"):
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))

import studio_camera_position_evidence as evidence


class StaticCameraNativeRepairError(ValueError):
    """Source camera cannot be safely repositioned in this editor."""


def _load(path: Path) -> dict:
    return evidence.readback._safe_json(path)[0]


def _live_location(actor: Any) -> tuple[float, float, float]:
    loc = actor.get_actor_location()
    point = (float(loc.x), float(loc.y), float(loc.z))
    if not all(math.isfinite(x) and abs(x) < 10_000_000 for x in point):
        raise StaticCameraNativeRepairError("Native camera location is unbounded.")
    return point


def _static_transform_ownership(api: Any, sequence: Any) -> None:
    ext = getattr(api, "MovieSceneSequenceExtensions", None)
    if (not callable(getattr(ext, "get_tracks", None))
            or not callable(getattr(ext, "get_bindings", None))):
        raise StaticCameraNativeRepairError("Full native Sequencer track inspection missing.")
    try:
        root = list(ext.get_tracks(sequence))
        bindings = list(ext.get_bindings(sequence))
        if len(root) > 1000 or len(bindings) > 1000:
            raise StaticCameraNativeRepairError("Native Sequencer inventory exceeds limits.")
        for binding in bindings:
            tracks = list(binding.get_tracks())
            if len(tracks) > 1000:
                raise StaticCameraNativeRepairError("Native binding track count exceeds limits.")
            root.extend(tracks)
        if len(root) > 10000:
            raise StaticCameraNativeRepairError("Native track count exceeds limits.")
        allowed = {
            "MovieSceneCameraCutTrack",
            "MovieSceneSkeletalAnimationTrack",
            "MovieSceneVisibilityTrack",
            "MovieSceneAudioTrack",
        }
        for track in root:
            kind = str(track.get_class().get_name())
            # Unknown tracks (including scalar, double, parameter, attach,
            # control-rig, shot and custom plugin tracks) may drive placement.
            # Reject rather than trying to guess their hidden write targets.
            if kind not in allowed:
                raise StaticCameraNativeRepairError(
                    "Sequencer transform/property ownership is not a static camera."
                )
    except StaticCameraNativeRepairError:
        raise
    except (AttributeError, TypeError, ValueError, RuntimeError) as exc:
        raise StaticCameraNativeRepairError(
            "Native Sequencer property ownership could not be verified."
        ) from exc


def attempt(api: Any, workspace: Path, job: dict, request: dict) -> dict:
    candidate = Path(job["candidate_dir"]).resolve()
    if request.get("strategy") != "restore_static_camera_position":
        raise StaticCameraNativeRepairError("Wrong camera-placement adapter.")
    feedback_id = str(request.get("feedback_id") or "")
    if re.fullmatch(r"[a-f0-9]{32}", feedback_id) is None:
        raise StaticCameraNativeRepairError("A current explicit user request is required.")
    active = _load(candidate / ("user-feedback-active-" + job["job_id"] + ".json"))
    feedback = _load(candidate / ("user-feedback-" + feedback_id + ".json"))
    if (active.get("feedback_id") != feedback_id
            or active.get("job_id") != job["job_id"]
            or active.get("candidate_id") != job["candidate_id"]
            or feedback.get("kind") != "cutsceneai.studio.user_feedback"
            or feedback.get("feedback_id") != feedback_id
            or feedback.get("job_id") != job["job_id"]
            or feedback.get("candidate_id") != job["candidate_id"]
            or not evidence.message_requests_position(feedback.get("message"))):
        raise StaticCameraNativeRepairError("Missing explicit camera-placement consent.")
    proof = evidence.build(workspace, job)
    if (request.get("camera_position_repair_sha256")
            != proof["camera_position_repair_sha256"]
            or request.get("source_camera_occurrence_id")
            != proof["source_camera_occurrence_id"]):
        raise StaticCameraNativeRepairError("The source-bound position proof changed.")
    setup_path = Path(str(job.get("setup_receipt_file") or "")).resolve()
    if setup_path.is_symlink() or setup_path.parent != candidate or not setup_path.is_file():
        raise StaticCameraNativeRepairError("Exact staged native camera receipt is missing.")
    created = [
        row for row in _load(setup_path).get("actors_created", [])
        if isinstance(row, dict)
        and row.get("kind") == "entity.camera"
        and row.get("name") == proof["source_camera_name"]
        and row.get("label") == proof["target_actor_label"]
    ]
    if len(created) != 1:
        raise StaticCameraNativeRepairError("Camera is not uniquely newly staged.")
    sequence = api.load_asset(job["sequence_path"])
    if sequence is None:
        raise StaticCameraNativeRepairError("Exact generated sequence is missing.")
    _static_transform_ownership(api, sequence)
    scene = api.get_editor_subsystem(api.EditorActorSubsystem)
    all_actors = list(scene.get_all_level_actors())
    matches = [actor for actor in all_actors
               if str(actor.get_actor_label()) == proof["target_actor_label"]]
    if len(matches) != 1:
        raise StaticCameraNativeRepairError("Camera actor label is not unique.")
    actor = matches[0]
    if actor.get_attach_parent_actor() is not None:
        raise StaticCameraNativeRepairError("An attached camera requires a rig-aware repair.")
    if any(
        other is not actor and other.get_attach_parent_actor() is actor
        for other in all_actors
    ):
        raise StaticCameraNativeRepairError("Camera owns attached actors; do not move.")
    component = getattr(actor, "get_cine_camera_component", None)
    if not callable(component) or component() is None:
        raise StaticCameraNativeRepairError("Source target is not a native CineCameraActor.")
    old = _live_location(actor)
    expected = tuple(proof["native_world_before_cm"])
    if math.dist(old, expected) > 0.1:
        raise StaticCameraNativeRepairError(
            "Live camera base transform differs from independently sampled position."
        )
    delta = tuple(proof["unreal_offset_cm"])
    corrected = tuple(a + d for a, d in zip(old, delta))
    changed = False
    saved = False
    try:
        # Set rollback intent *before* calling Unreal; the native setter can
        # change an object and then fail in an editor notification hook.
        changed = True
        actor.set_actor_location(api.Vector(*corrected), False, True)
        if math.dist(_live_location(actor), corrected) > 0.1:
            raise StaticCameraNativeRepairError(
                "Live native camera did not reach source-aligned location."
            )
        import studio_auto_scene
        studio_auto_scene._save_level(api, job["expected_level"])
        saved = True
        return {
            "status": "CAMERA_STATIC_POSITION_SAVED_REOPENED_CINETWIN_PENDING",
            "source_camera_occurrence_id": proof["source_camera_occurrence_id"],
            "camera_position_repair_sha256": proof["camera_position_repair_sha256"],
            "changes": 1,
            "native_position_error_before_cm": proof["max_world_offset_cm"],
            "native_base_position_error_after_cm": math.dist(
                _live_location(actor), corrected,
            ),
            "native_base_property_readback_verified": True,
            "persistence_after_editor_restart_verified": False,
            "cinetwin_reopened_time_grid_verified_after_repair": False,
            "rendered_framing_verified": False,
            "full_cutscene_fidelity_verified": False,
        }
    finally:
        if changed and not saved:
            actor.set_actor_location(api.Vector(*old), False, True)
