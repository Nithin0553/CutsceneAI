"""Read-only proof for ONE isolated source-sampled animated CineCamera position key.

This is deliberately not a general camera animation rewrite: only an original,
CineTwin-authenticated Unity actor-world trajectory, exactly one deviating
sample on exactly one native XYZ position channel, and no other discrepancies
can be offered for the separately guarded Unreal key edit.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
UNREAL = str(ROOT / "integrations/unreal")
if UNREAL not in sys.path:
    sys.path.insert(0, UNREAL)

import csir_plan
import studio_camera_motion_contract as contract
import studio_camera_yaw_evidence as yaw
import studio_camera_position_evidence as position
import studio_element7_readback as readback
import studio_element8_repair as repair
import studio_element9_outcome as outcome

KIND = "cutsceneai.studio.single_animated_camera_position_key_review"
STRATEGY = "restore_single_animated_camera_position_key"
MIN_CM = 3.0
MAX_CM = 30.0
OTHER_POSITION_CM = 0.15
SOURCE_PLAN_CM = 0.1
OTHER_ROTATION_DEGREES = 0.2
_MAX_FRAMES = 1001
_FIX = re.compile(r"\b(?:fix|repair|correct|restore|align)\b", re.I)
_CAM = re.compile(r"\b(?:camera|cinecamera)\b", re.I)
_KEY = re.compile(r"\b(?:keyframe|key[ -]?frame|keyed[ -]?frame)\b", re.I)
_POS = re.compile(r"\b(?:position|translation|location)\b", re.I)
_MOTION = re.compile(r"\b(?:animated|animation|moving|motion)\b", re.I)
_FORBID = re.compile(
    r"\b(?:all|every|multiple|many|several|whole|entire|curve|curves|"
    r"rotation|rotations|yaw|pitch|roll|facing|pan|tilt|scale|zoom|lens|fov|"
    r"cut|cuts|switch|shot|shots|blend|blending|rig|parent|skeletal|"
    r"character|dolly|physics|event|delete|insert|timewarp|"
    r"do not|don't|dont|never|avoid)\b", re.I,
)


class AnimatedCameraKeyError(ValueError):
    """Exact original camera, native sample or user intent is not proven."""


def message_requests_key(message: Any) -> bool:
    return bool(
        isinstance(message, str) and 8 <= len(message) <= 1200
        and all(ord(c) >= 32 or c in "\n\t" for c in message)
        and all(pattern.search(message)
                for pattern in (_FIX, _CAM, _KEY, _POS, _MOTION))
        and not _FORBID.search(message)
    )


def _unique_sample(capture: dict, entity_id: str, label: str | None,
                   moment: float) -> dict:
    matches = [
        sample for sample in capture.get("samples", [])
        if isinstance(sample, dict)
        and type(sample.get("time_seconds")) in (int, float)
        and math.isfinite(sample["time_seconds"])
        and abs(float(sample["time_seconds"])-moment) < 1e-7
    ]
    if len(matches) != 1:
        raise AnimatedCameraKeyError("Original camera capture frame is missing/duplicated.")
    entities = matches[0].get("entities")
    if not isinstance(entities, list):
        raise AnimatedCameraKeyError("Missing native camera actor observation.")
    rows = [row for row in entities
            if isinstance(row, dict) and row.get("entity_id") == entity_id]
    if (len(rows) != 1
            or (label is not None and rows[0].get("actor_label") != label)
            or not isinstance(rows[0].get("world_transform"), dict)):
        raise AnimatedCameraKeyError("Source/native camera occurrence is not unique.")
    return rows[0]["world_transform"]


def _vec(transform: dict, field: str, count: int) -> tuple[float, ...]:
    value = transform.get(field)
    if (not isinstance(value, list) or len(value) != count
            or any(type(v) not in (int, float) or not math.isfinite(v)
                   or abs(v) > 100000 for v in value)):
        raise AnimatedCameraKeyError("Missing bounded camera " + field)
    return tuple(float(v) for v in value)


def _analyze_grid(source: dict, target: dict, entity: dict,
                  label: str, action: dict, plan: dict,
                  csir: dict) -> dict:
    """Pure comparison of ORIGINAL source, target and compiled source keys."""
    if (action.get("source_behavior_strategy") != contract.CAPTURE_STRATEGY
            or action.get("baked_source_curves") is not True):
        raise AnimatedCameraKeyError(
            "Only independently evaluated source-world camera keys are eligible."
        )
    contract.validate_action(action,duration_frames=plan["duration_frames"])
    rate = plan.get("display_rate") or {}
    fps_n, fps_d = rate.get("numerator"), rate.get("denominator")
    if (type(fps_n) is not int or type(fps_d) is not int
            or fps_n <= 0 or fps_d <= 0 or
            csir.get("timing", {}).get("source_rate") != rate
            or len(action["keys"]) > _MAX_FRAMES
            or csir_plan.rational_seconds(
                csir.get("timing", {}).get("playback_start", {
                    "value":0,"rate":{"numerator":1,"denominator":1},
                })
            ) != 0):
        raise AnimatedCameraKeyError("Camera source frame-rate/origin unsupported.")
    if (len(source.get("samples", [])) < len(action["keys"])
            or len(target.get("samples", [])) < len(action["keys"])):
        raise AnimatedCameraKeyError("Original complete native camera grid absent.")

    differing = []
    all_source_positions = []
    for key in action["keys"]:
        frame = key["frame"]
        t = frame * fps_d / fps_n
        original = _unique_sample(source, entity["entity_id"], None, t)
        native = _unique_sample(target, entity["entity_id"], label, t)
        original_position = _vec(original,"position_m",3)
        native_position = _vec(native,"position_m",3)
        original_rotation = _vec(original,"rotation_xyzw",4)
        native_rotation = _vec(native,"rotation_xyzw",4)
        original_scale = _vec(original,"scale_xyz",3)
        native_scale = _vec(native,"scale_xyz",3)
        if any(abs(x-1.) > 0.01 for x in (*original_scale,*native_scale)):
            raise AnimatedCameraKeyError("Camera scale has a competing discrepancy.")
        if yaw._qangle(original_rotation,native_rotation) > OTHER_ROTATION_DEGREES:
            raise AnimatedCameraKeyError("Camera orientation is also discrepant.")
        source_cm = csir_plan.canonical_position_to_unreal_cm(original_position)
        observed_cm = csir_plan.canonical_position_to_unreal_cm(native_position)
        if math.dist(source_cm, key["location_cm"]) > SOURCE_PLAN_CM:
            raise AnimatedCameraKeyError(
                "Original Unity evaluated world pose differs from compiled camera."
            )
        planned_rotation = csir_plan.canonical_quat_to_unreal_rotator(
            original_rotation
        )
        # Compare physical rotations, not Euler wrap conventions. The exact
        # Unreal channel values are checked independently just before edit.
        if any(not math.isfinite(v) for v in planned_rotation):
            raise AnimatedCameraKeyError("Original camera rotation is invalid.")
        if any(abs(x-1.) > 0.01 for x in original_scale):
            raise AnimatedCameraKeyError("Original camera source scale changed.")
        all_source_positions.append(source_cm)
        for axis in range(3):
            drift = observed_cm[axis] - source_cm[axis]
            if abs(drift) > OTHER_POSITION_CM:
                differing.append((frame,axis,drift,observed_cm[axis],source_cm[axis]))
    if max(math.dist(v,all_source_positions[0])
           for v in all_source_positions) < 10.:
        raise AnimatedCameraKeyError(
            "Camera is not moving; static-camera adapters own that scenario."
        )
    if len(differing) != 1:
        raise AnimatedCameraKeyError(
            "Camera needs exactly one isolated positional source/native key correction."
        )
    frame,axis,drift,observed,expected = differing[0]
    if (frame in (0,plan["duration_frames"])
            or not MIN_CM <= abs(drift) <= MAX_CM):
        raise AnimatedCameraKeyError(
            "Camera error is a boundary key or exceeds safe single-key correction."
        )
    return {
        "source_key_frame":frame,"native_channel_index":axis,
        "native_key_value_before_cm":round(observed,6),
        "source_key_value_cm":round(expected,6),
        "native_source_position_error_cm":round(abs(drift),6),
        "sample_count":len(action["keys"]),
    }


def build(workspace: Path, job: dict[str,Any]) -> dict[str,Any]:
    if not isinstance(job,dict):
        raise AnimatedCameraKeyError("Native camera job missing.")
    try:
        root,candidate,canonical,csir,mapping,compiled = outcome._context(
            workspace,job.get("job_id"),
        )
        if canonical != job:
            raise AnimatedCameraKeyError("Current camera job changed.")
        folders = outcome.discover(root,job["job_id"])
        if len(folders) != 1:
            raise AnimatedCameraKeyError(
                "Camera requires one original reopened baseline, no prior remeasurements."
            )
        native = readback.build(root,job["job_id"],folders[0])
        bounded = repair.build(root,job["job_id"],folders)
        source,_ = readback._safe_json(Path(job["capture"]))
        target,_ = readback._safe_json(folders[0]/"target-behavior.json")
    except AnimatedCameraKeyError:
        raise
    except (outcome.OutcomeError,readback.Element7ReadbackError,
            repair.BoundedRepairError,OSError,ValueError,TypeError,
            KeyError,IndexError) as exc:
        raise AnimatedCameraKeyError(
            "Independent native camera capture/source/action chain is incomplete."
        ) from exc
    if (native.get("native_attempt",{}).get("native_builder_completed") is not True
            or native.get("distinct_reopened_editor_observed") is not True
            or native.get("native_structure_status") != "PASS"
            or native.get("camera_lens_status") not in {"PASS","NOT_APPLICABLE"}
            or native.get("camera_cuts_status") not in {"PASS","NOT_APPLICABLE"}
            or native.get("native_persistence_status")
            != "STRUCTURAL_READBACK_PASS_DIFFERENT_EDITOR_PROCESS"
            or bounded.get("status") in {
                "STOP_MEASURED_REGRESSION_OR_NO_PROGRESS",
                "STOP_REMEASUREMENT_BUDGET_EXHAUSTED",
            }):
        raise AnimatedCameraKeyError("Reopened camera native verification failed.")

    cameras = [item for item in csir.get("entities",[])
               if isinstance(item,dict) and item.get("ced_type")=="entity.camera"]
    if len(cameras)!=1:
        raise AnimatedCameraKeyError("Only one source CineCamera is eligible.")
    camera=cameras[0]
    name,ident=camera.get("name"),camera.get("entity_id")
    mapping_row=(mapping.get("entities") or {}).get(name)
    label=mapping_row.get("actor_label") if isinstance(mapping_row,dict) else None
    if (not all(isinstance(x,str) and 0<len(x)<=256
                for x in (name,ident,label))):
        raise AnimatedCameraKeyError("Mapped source camera identity missing.")
    camera_tracks = [track for track in csir.get("tracks",[])
                     if isinstance(track,dict)
                     and track.get("muted") is not True
                     and track.get("binding_entity_id")==ident
                     and track.get("ced_type")!="camera.cut"]
    if (len(camera_tracks)!=1
            or camera_tracks[0].get("ced_type")!="camera.transform"
            or camera.get("parent_entity_id")
            or any(track.get("ced_type") in {
                "camera.animation","transform.track","time.warp",
                "cinematic.shot","camera.blend",
            } for track in csir.get("tracks",[]) if isinstance(track,dict))):
        raise AnimatedCameraKeyError(
            "Animated camera has competing curve, parent or shot ownership."
        )
    actions=[a for a in compiled.get("actions",[])
             if isinstance(a,dict) and a.get("entity_name")==name
             and a.get("kind")=="transform"]
    if (len(actions)!=1 or actions[0].get("actor_label")!=label
            or actions[0].get("source_behavior_strategy")
            !=contract.CAPTURE_STRATEGY):
        raise AnimatedCameraKeyError(
            "Original compiled camera action is not evaluated CineTwin motion."
        )
    grid=_analyze_grid(source,target,camera,label,actions[0],compiled,csir)
    workflow=repair._snapshot(candidate)
    if workflow is None:
        raise AnimatedCameraKeyError("Source occurrence plan missing.")
    idx=csir["entities"].index(camera)
    matches=[x.get("occurrence_id")
             for x in workflow["element_plan"]["elements"]
             if x.get("source_kind")=="entities"
             and x.get("source_location")==f"entities[{idx}]"]
    rows=[x for x in bounded["per_occurrence"]
          if x.get("occurrence_id") in matches]
    if (len(matches)!=1 or len(rows)!=1
            or rows[0].get("latest_status")!="DIRECT_MEASURED_DIFFERENCE"
            or rows[0].get("latest_discrepancy_flags")
            !=["WORLD_POSITION_OUTSIDE_TOLERANCE"]):
        raise AnimatedCameraKeyError(
            "One exact camera source occurrence was not separately measured discrepant."
        )
    result={
        "kind":KIND,"eligible":True,
        "source_camera_name":name,"source_entity_id":ident,
        "source_camera_occurrence_id":matches[0],
        "target_actor_label":label,
        "source_camera_action_sha256":position._hash(actions[0]),
        "element7_readback_sha256":native["readback_sha256"],
        "element8_repair_sha256":bounded["repair_plan_sha256"],
        **grid,
        "native_edit_authorized":False,
        "cinetwin_reopened_after_repair_verified":False,
        "rendered_camera_motion_verified":False,
        "full_cutscene_fidelity_verified":False,
    }
    result["animated_camera_key_repair_sha256"]=position._hash(result)
    return result
