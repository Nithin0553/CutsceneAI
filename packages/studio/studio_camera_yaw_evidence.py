"""Source-bound static CineCamera yaw-only orientation recovery (read-only).

This is NOT general animated camera rotation, retargeting or roll/pitch repair.
One source camera must have an unchanged, position-matched, scale-matched,
upright-or-tilted constant world transform and native physical lens/cut parity.
Only a constant *Unreal yaw* discrepancy may be considered, with Unreal
pitch/roll already matching in each independent source/native sample.

Every numeric edit target is derived using the existing CSIR -> Unreal
orientation conversion; user text and model output never supply degrees.
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
integrations = str(ROOT / "integrations/unreal")
if integrations not in sys.path:
    sys.path.insert(0, integrations)

import csir_plan
import studio_camera_position_evidence as position
import studio_element7_readback as readback
import studio_element8_repair as repair
import studio_element9_outcome as outcome

KIND = "cutsceneai.studio.static_camera_yaw_review"
MIN_YAW_CORRECTION_DEGREES = 2.0
MAX_YAW_CORRECTION_DEGREES = 90.0
STATIC_ROTATION_DRIFT_DEGREES = 0.2
STATIC_POSITION_DRIFT_CM = 0.1
POSITION_MATCH_CM = 1.0
ROLL_PITCH_MATCH_DEGREES = 0.25
MAX_YAW_DRIFT_DEGREES = 0.2
MAX_PITCH_DEGREES = 75.0
_FIX = re.compile(r"\b(?:fix|repair|correct|restore|align|adjust|rotate|turn)\b", re.I)
_CAMERA = re.compile(r"\b(?:camera|cinecamera)\b", re.I)
_FACING = re.compile(r"\b(?:rotation|yaw|orientation|direction|facing|angle)\b", re.I)
_UNSAFE = re.compile(
    r"\b(?:cut|cuts|shot|shots|switch|lens|zoom|fov|focus|exposure|"
    r"position|placement|translation|offset|move|moving|animated|"
    r"animation|keyframe|pan|tilt|dolly|tracking|rig|parent|"
    r"roll|pitch|character|skeletal|multiple|all|every|blend|"
    r"sequence|insert|delete|scale)\b", re.I,
)
_NEGATION = re.compile(r"\b(?:do not|don't|dont|without|never|avoid)\b", re.I)


class StaticCameraYawError(ValueError):
    """Static source/native camera yaw is not independently proven."""


def message_requests_yaw(message: Any) -> bool:
    return bool(
        isinstance(message, str) and 0 < len(message) <= 1200
        and _FIX.search(message) and _CAMERA.search(message)
        and _FACING.search(message) and not _UNSAFE.search(message)
        and not _NEGATION.search(message)
        and all(ord(c) >= 32 or c in "\n\t" for c in message)
    )


def _vec(data: Any, name: str, count: int) -> tuple[float, ...]:
    try:
        vector = data[name]
    except (TypeError, KeyError) as exc:
        raise StaticCameraYawError("Invalid source/native " + name) from exc
    if (not isinstance(vector, (list, tuple))
            or len(vector) != count
            or any(type(v) not in (int, float) for v in vector)
            or any(not math.isfinite(v) or abs(v) > 100000 for v in vector)):
        raise StaticCameraYawError("Invalid source/native " + name)
    return tuple(float(v) for v in vector)


def _qangle(a: Any, b: Any) -> float:
    q1, q2 = tuple(a), tuple(b)
    if any(abs(sum(v*v for v in q) - 1) > 0.01 for q in (q1, q2)):
        raise StaticCameraYawError("Unnormalized camera quaternion.")
    return math.degrees(2 * math.acos(min(1, abs(sum(
        u*v for u,v in zip(q1,q2)
    )))))


def _wrap(a: float) -> float:
    return (a + 180) % 360 - 180


def _rpy(q: tuple[float, ...]) -> tuple[float, float, float]:
    try:
        return csir_plan.canonical_quat_to_unreal_rotator(q)
    except (csir_plan.PlanError, ValueError, TypeError) as exc:
        raise StaticCameraYawError(
            "Source/native quaternion has no valid Unreal actor orientation."
        ) from exc


def _one(frame: Any, entity: str, *, label: str | None = None) -> dict:
    if not isinstance(frame, dict) or not isinstance(frame.get("entities"), list):
        raise StaticCameraYawError("Source/native camera sample frame is absent.")
    rows = [v for v in frame["entities"]
            if isinstance(v, dict) and v.get("entity_id") == entity]
    if (len(rows) != 1
            or (label is not None and rows[0].get("actor_label") != label)):
        raise StaticCameraYawError("A source-mapped camera disappeared or is ambiguous.")
    transform = rows[0].get("world_transform")
    if not isinstance(transform, dict):
        raise StaticCameraYawError("Camera world transform was not sampled.")
    return transform


def build(workspace: Path, job: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(job, dict):
        raise StaticCameraYawError("Native job is missing.")
    try:
        root, candidate, canonical, csir, mapping, compiled = outcome._context(
            workspace, job.get("job_id"),
        )
        if canonical != job:
            raise StaticCameraYawError("Current native camera job changed.")
        folders = outcome.discover(root, job["job_id"])
        if not folders:
            raise StaticCameraYawError("Independent reopened native camera capture missing.")
        bounded = repair.build(root, job["job_id"], folders)
        native = readback.build(root, job["job_id"], folders[-1])
        source, _ = readback._safe_json(Path(job["capture"]))
        target, _ = readback._safe_json(folders[-1] / "target-behavior.json")
    except StaticCameraYawError:
        raise
    except (outcome.OutcomeError, repair.BoundedRepairError,
            readback.Element7ReadbackError, OSError, ValueError,
            KeyError, TypeError) as exc:
        raise StaticCameraYawError(
            "Independent original camera rotation evidence is stale or incomplete."
        ) from exc
    if (bounded.get("status") in {
            "STOP_MEASURED_REGRESSION_OR_NO_PROGRESS",
            "STOP_REMEASUREMENT_BUDGET_EXHAUSTED",
        }
            or native.get("native_attempt", {}).get("native_builder_completed") is not True
            or native.get("distinct_reopened_editor_observed") is not True
            or native.get("camera_lens_status") != "PASS"
            or native.get("camera_cuts_status") not in {"PASS", "NOT_APPLICABLE"}
            or not isinstance(bounded.get("per_occurrence"), list)):
        raise StaticCameraYawError(
            "Source/native original readback, camera lens, cuts or budget not verified."
        )
    cameras = [e for e in csir.get("entities", [])
               if isinstance(e, dict) and e.get("ced_type") == "entity.camera"]
    if len(cameras) != 1:
        raise StaticCameraYawError("Exactly one source camera is eligible.")
    camera = cameras[0]
    name, ident = camera.get("name"), camera.get("entity_id")
    mapped = (mapping.get("entities") or {}).get(name)
    label = mapped.get("actor_label") if isinstance(mapped, dict) else None
    if (not isinstance(name, str) or not name or len(name) > 128
            or not isinstance(ident, str) or not ident
            or not isinstance(label, str) or not label or len(label) > 256):
        raise StaticCameraYawError("Source CineCamera identity is ambiguous.")
    # Constant sampled motion does not excuse an authored curve. Unknown
    # camera property writers, unbound transform masters and nested scenes
    # must be rejected instead of inferring static ownership from a few ticks.
    if any(
        t.get("binding_entity_id") == ident
        and t.get("ced_type") != "camera.cut"
        for t in csir.get("tracks", []) if isinstance(t, dict)
    ) or any(
        t.get("binding_entity_id") is None
        and t.get("ced_type") in {"transform.track", "animation.track",
                                  "camera.animation", "camera.rotation"}
        for t in csir.get("tracks", []) if isinstance(t, dict)
    ) or any(
        a.get("kind") in {"transform", "actor_transform", "camera_transform",
                          "property_float", "camera_fov", "camera_rotation",
                          "rotate_actor"}
        for a in compiled.get("actions", []) if isinstance(a, dict)
    ):
        raise StaticCameraYawError(
            "Source/compiled camera animation may own actor orientation."
        )
    src_frames, dst_frames = source.get("samples"), target.get("samples")
    if (not isinstance(src_frames, list) or not isinstance(dst_frames, list)
            or len(src_frames) != len(dst_frames) or len(src_frames) < 2
            or len(src_frames) > 100001):
        raise StaticCameraYawError("Complete bounded source/native frame grid missing.")
    first_src = first_dst = None
    expected_rpy = observed_rpy = None
    deltas = []
    previous = None
    for src_frame, dst_frame in zip(src_frames, dst_frames):
        t, u = src_frame.get("time_seconds"), dst_frame.get("time_seconds")
        if (type(t) not in (int, float) or type(u) not in (int, float)
                or not math.isfinite(t) or not math.isfinite(u)
                or abs(t-u) > 1e-7
                or (previous is not None and t <= previous)):
            raise StaticCameraYawError("Reopened full camera sample times changed.")
        previous = t
        a = _one(src_frame, ident)
        b = _one(dst_frame, ident, label=label)
        ap, bp = _vec(a, "position_m", 3), _vec(b, "position_m", 3)
        aq, bq = _vec(a, "rotation_xyzw", 4), _vec(b, "rotation_xyzw", 4)
        ass, bss = _vec(a, "scale_xyz", 3), _vec(b, "scale_xyz", 3)
        if (math.dist(ap, bp)*100 > POSITION_MATCH_CM
                or any(abs(scale-1) > 0.01 for scale in (*ass,*bss))):
            raise StaticCameraYawError(
                "Actor position or non-unit scale is a competing camera discrepancy."
            )
        erpy, nrpy = _rpy(aq), _rpy(bq)
        if (abs(erpy[1]) > MAX_PITCH_DEGREES
                or abs(nrpy[1]) > MAX_PITCH_DEGREES
                or abs(_wrap(erpy[0]-nrpy[0])) > ROLL_PITCH_MATCH_DEGREES
                or abs(_wrap(erpy[1]-nrpy[1])) > ROLL_PITCH_MATCH_DEGREES):
            raise StaticCameraYawError(
                "Pitch/roll or gimbal ambiguity cannot be repaired by actor yaw."
            )
        delta = _wrap(erpy[2]-nrpy[2])
        if first_src is None:
            first_src, first_dst = (ap, aq), (bp, bq)
            expected_rpy, observed_rpy = erpy, nrpy
        elif (math.dist(ap, first_src[0])*100 > STATIC_POSITION_DRIFT_CM
              or math.dist(bp, first_dst[0])*100 > STATIC_POSITION_DRIFT_CM
              or _qangle(aq, first_src[1]) > STATIC_ROTATION_DRIFT_DEGREES
              or _qangle(bq, first_dst[1]) > STATIC_ROTATION_DRIFT_DEGREES):
            raise StaticCameraYawError(
                "Animated/rotating camera requires source track-aware reconstruction."
            )
        deltas.append(delta)
    delta = deltas[0]
    if (not MIN_YAW_CORRECTION_DEGREES <= abs(delta) <= MAX_YAW_CORRECTION_DEGREES
            or max(abs(_wrap(x-delta)) for x in deltas) > MAX_YAW_DRIFT_DEGREES):
        raise StaticCameraYawError(
            "Camera yaw is aligned, varies over time or exceeds safe correction."
        )
    workflow = repair._snapshot(candidate)
    if workflow is None:
        raise StaticCameraYawError("Source occurrence workflow is missing.")
    occurrences = [x.get("occurrence_id")
                   for x in workflow["element_plan"]["elements"]
                   if x.get("source_kind") == "entities"
                   and x.get("source_location") ==
                   "entities[" + str(csir["entities"].index(camera)) + "]"]
    rows = [x for x in bounded["per_occurrence"]
            if x.get("occurrence_id") in occurrences]
    if (len(occurrences) != 1 or len(rows) != 1
            or rows[0].get("latest_status") != "DIRECT_MEASURED_DIFFERENCE"
            or rows[0].get("latest_discrepancy_flags")
            != ["WORLD_ROTATION_OUTSIDE_TOLERANCE"]):
        raise StaticCameraYawError(
            "CineTwin did not attribute an isolated static yaw discrepancy to this camera."
        )
    report = {
        "kind": KIND, "eligible": True,
        "source_camera_name": name, "source_entity_id": ident,
        "source_camera_occurrence_id": occurrences[0],
        "target_actor_label": label,
        "native_rotation_rpy_before_degrees": [round(x, 6) for x in observed_rpy],
        "source_aligned_rotation_rpy_degrees": [round(x, 6) for x in expected_rpy],
        "native_position_before_cm": [
            round(x,6) for x in (
                -first_dst[0][2]*100,first_dst[0][0]*100,first_dst[0][1]*100
            )
        ],
        "native_yaw_delta_degrees": round(delta, 6),
        "max_yaw_variation_degrees":
            round(max(abs(_wrap(x-delta)) for x in deltas), 6),
        "element7_readback_sha256": native["readback_sha256"],
        "element8_repair_sha256": bounded["repair_plan_sha256"],
        "sample_count": len(src_frames),
        "native_edit_authorized": False,
        "rendered_camera_facing_verified": False,
        "cinetwin_reopened_verified_after_repair": False,
        "full_cutscene_fidelity_verified": False,
    }
    report["camera_yaw_repair_sha256"] = position._hash(report)
    return report
