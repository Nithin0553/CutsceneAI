"""Evidence gate for one source-backed Unreal actor world-translation repair.

Pure analysis. This module NEVER mutates Unreal objects or accepts a model's
invented offset. Only a dense, unambiguous, independently sampled translation
shared by actor and skeletal root can be eligible for a native correction.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any

TOLERANCE_CM = 2.0
MAX_OFFSET_CM = 500.0


def _xyz(value: Any) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError("Missing measured three-axis world position.")
    coords = tuple(float(v) for v in value)
    if not all(math.isfinite(v) and abs(v) < 1_000_000 for v in coords):
        raise ValueError("Nonfinite or unbounded world position.")
    return coords


def _distance(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return math.dist(a, b)


def _offset(row: dict) -> tuple[float, ...]:
    source, target = _xyz(row["source_cm"]), _xyz(row["target_cm"])
    return tuple(a - b for a, b in zip(source, target))


def _measured_rows(report: dict, entity: str) -> tuple[list[dict], list[dict]]:
    frame_set = report["frames"][entity]
    actor, root = frame_set["actor"], frame_set["root_bone"]
    count = report["source"]["evaluated_playback_frames"]
    if (type(count) is not int or count < 2 or len(actor) != count
            or len(root) != count):
        raise ValueError("Actor/root frames do not cover the full active playback.")
    a = [r["frame"] for r in actor]
    b = [r["frame"] for r in root]
    if (a != b or len(set(a)) != count or
            any(type(f) is not int for f in a) or a != sorted(a)):
        raise ValueError("Actor/root measurements are not aligned to unique frames.")
    return actor, root


def review(report: dict[str, Any], entity: str) -> dict[str, Any]:
    """Report eligibility or a specific no-edit reason, never a blind fix."""
    result: dict[str, Any] = {
        "eligible": False, "entity": entity,
        "strategy": "restore_constant_actor_offset",
    }
    try:
        if (report.get("kind") != "cutsceneai.cinetwin.unreal_world_pose_diagnostic"
                or report.get("status") != "DIAGNOSTIC_NOT_FIDELITY_VERIFIED"
                or report.get("errors")):
            raise ValueError("Complete, error-free native CineTwin evidence is required.")
        source = report["source"]
        if source.get("missing_source_frames"):
            raise ValueError("Source frame capture is incomplete.")
        observed = report["entities"][entity]
        if observed.get("status") != "READY" or observed.get("actor_match_count") != 1:
            raise ValueError("Source-to-target actor identity is ambiguous.")
        info = observed["component_info_frame0"]
        if (info.get("mesh_component_count") != 1
                or info.get("parent_actor_label") is not None):
            raise ValueError("Expected one unparented skeletal character.")
        label = observed["target_actor_label"]
        tracks = [b for b in report["target"]["binding_tracks"]
                  if b.get("binding") == label]
        if len(tracks) != 1:
            raise ValueError("Could not identify exactly one native Sequencer binding.")
        for track in tracks[0]["tracks"]:
            kind = track.get("class")
            if kind == "MovieScene3DTransformTrack":
                raise ValueError("Sequencer transform tracks override actor placement.")
            if kind not in {"MovieSceneSkeletalAnimationTrack", "MovieSceneVisibilityTrack"}:
                raise ValueError("Another unsupported track may control actor placement.")
        actor, root = _measured_rows(report, entity)
        expected = _offset(actor[0])
        magnitude = math.dist(expected, (0.0, 0.0, 0.0))
        if not TOLERANCE_CM < magnitude <= MAX_OFFSET_CM:
            raise ValueError("Actor offset is zero, already within tolerance, or too large.")
        deviations = [_distance(_offset(row), expected) for row in actor]
        root_deviations = [_distance(_offset(row), expected) for row in root]
        max_motion_variance = max(deviations)
        max_root_variance = max(root_deviations)
        if max_motion_variance > TOLERANCE_CM:
            raise ValueError(
                f"Actor offset varies by {max_motion_variance:.3f} cm across playback; "
                "a single placement edit cannot fix animated motion."
            )
        if max_root_variance > TOLERANCE_CM:
            raise ValueError(
                f"Skeletal-root offset differs by {max_root_variance:.3f} cm from "
                "the actor offset; inspect root motion, hierarchy and retargeting."
            )
        result.update({
            "eligible": True, "reason": "One constant actor/root world offset with no transform track.",
            "target_actor_label": label,
            "offset_source_minus_target_cm": [round(v, 6) for v in expected],
            "offset_magnitude_cm": magnitude,
            "max_actor_offset_variation_cm": max_motion_variance,
            "max_root_offset_variation_cm": max_root_variance,
            "sample_count": len(actor),
        })
    except (KeyError, IndexError, TypeError, ValueError, OverflowError) as exc:
        result["reason"] = str(exc)[:350]
    return result


def within_tolerance(report: dict, entity: str) -> dict[str, Any]:
    """Check both actor and skeletal-root absolute positions after a proposed edit."""
    try:
        if (report.get("kind") != "cutsceneai.cinetwin.unreal_world_pose_diagnostic"
                or report.get("errors") or report["source"].get("missing_source_frames")):
            raise ValueError("Incomplete post-repair diagnostic.")
        actor, root = _measured_rows(report, entity)
        errors_a = [_distance(_xyz(r["source_cm"]), _xyz(r["target_cm"])) for r in actor]
        errors_r = [_distance(_xyz(r["source_cm"]), _xyz(r["target_cm"])) for r in root]
        max_actor, max_root = max(errors_a), max(errors_r)
        return {
            "passed": max(max_actor, max_root) <= TOLERANCE_CM,
            "max_actor_error_cm": max_actor,
            "max_root_error_cm": max_root,
            "sample_count": len(actor),
        }
    except (KeyError, IndexError, TypeError, ValueError, OverflowError) as exc:
        return {"passed": False, "reason": str(exc)[:350]}


def source_bound_report(job: dict, candidate: Path) -> dict:
    """Bind immutable native diagnostic to this job and current input bytes."""
    path = Path(str(job.get("diagnostic_file") or "")).resolve()
    if path.parent != candidate.resolve() or not path.is_file() or path.is_symlink():
        raise ValueError("Job-scoped original CineTwin diagnostic is unavailable.")
    result = json.loads(path.read_text(encoding="utf-8-sig"))
    origin = result.get("source") or {}
    for key, field in (("csir", "csir_sha256"),
                       ("mapping", "mapping_sha256"),
                       ("capture", "capture_sha256")):
        source_path = Path(str(job.get(key) or "")).resolve()
        if (not source_path.is_file() or
                origin.get(field) != hashlib.sha256(source_path.read_bytes()).hexdigest()):
            raise ValueError("CineTwin source provenance changed: " + key)
    target = result.get("target") or {}
    expected_project = os.path.normcase(str(Path(job["expected_project"]).resolve()))
    target_project = os.path.normcase(str(Path(str(target.get("project") or "")).resolve()))
    if (target_project != expected_project or
            target.get("sequence_path") != job.get("sequence_path")):
        raise ValueError("CineTwin diagnostic targets a different project or sequence.")
    return result
