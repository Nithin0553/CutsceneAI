"""CutSceneAI Studio: read-only audit of newly imported Unreal AnimSequence assets.

Run inside Unreal Editor 5.8 Python after Save All and reopening the project.
Writes one timestamped JSON report next to the import receipt. Never edits assets.
Readback and sampled pose motion are NOT source-target animation fidelity proof.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _project_key(path: str) -> str:
    # Unreal project path may be relative to the running process in some runtimes.
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _hash(path: str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _pose_signature(transform: Any) -> tuple[float, ...]:
    pos = transform.translation
    quat = transform.rotation
    return (float(pos.x), float(pos.y), float(pos.z),
            float(quat.x), float(quat.y), float(quat.z), float(quat.w))


def _pose_changed(a: tuple[float, ...], b: tuple[float, ...]) -> bool:
    translation_cm = math.dist(a[:3], b[:3])
    dot = abs(sum(x * y for x, y in zip(a[3:], b[3:])))
    angle_degrees = math.degrees(2 * math.acos(min(1.0, max(0.0, dot))))
    return translation_cm > 0.01 or angle_degrees > 0.1


def run(receipt_path: str) -> dict[str, Any]:
    import unreal  # Only available in the running Unreal Editor.

    source = Path(receipt_path).resolve()
    receipt = json.loads(source.read_text(encoding="utf-8-sig"))
    if (receipt.get("kind") != "cutsceneai.studio.fresh_animation_import_receipt"
            or receipt.get("status") != "IMPORTED_ANIMATIONS_UNVERIFIED"):
        raise ValueError("Expected completed Stage 2 import receipt; no audit performed.")
    expected_project = str(receipt.get("verified_project", ""))
    live_project = str(unreal.Paths.get_project_file_path())
    if not expected_project or _project_key(expected_project) != _project_key(live_project):
        raise ValueError(f"Wrong project: {live_project}. Expected {expected_project}.")

    observed = []
    for entry in receipt.get("imported", []):
        asset_path = str(entry.get("target_asset_path", ""))
        target_skeleton_path = str(entry.get("target_skeleton_path", ""))
        if not asset_path.startswith("/Game/"):
            raise ValueError("Unsafe asset path in receipt")
        animation = unreal.load_asset(asset_path)
        loaded_class = animation.get_class().get_name() if animation is not None else None
        expected_package = Path(expected_project).parent / "Content" / (
            asset_path[len("/Game/"):] + ".uasset")
        saved = expected_package.is_file()
        skeleton = animation.get_editor_property("skeleton") if loaded_class == "AnimSequence" else None
        actual_skeleton_path = skeleton.get_path_name() if skeleton is not None else None
        skeleton_matches = (actual_skeleton_path == target_skeleton_path)
        frames = 0
        bone_track_names: list[str] = []
        duration = None
        sampled_motion = None
        sampling_error = None
        if loaded_class == "AnimSequence":
            duration = float(animation.get_play_length())
            try:
                frames = int(unreal.AnimationLibrary.get_num_frames(animation))
                bone_track_names = [str(n) for n in unreal.AnimationLibrary.get_animation_track_names(animation)]
                # Detect any changing pose across the clip, including non-root motion.
                # This does not establish retargeting correctness or visual fidelity.
                if frames >= 2 and bone_track_names and duration and duration > 0:
                    sample_times = [0.0, duration * 0.25, duration * 0.5, duration * 0.75]
                    moving = False
                    for name in bone_track_names:
                        baseline = _pose_signature(unreal.AnimationLibrary.get_bone_pose_for_time(
                            animation, unreal.Name(name), sample_times[0], False))
                        for seconds in sample_times[1:]:
                            pose = _pose_signature(unreal.AnimationLibrary.get_bone_pose_for_time(
                                animation, unreal.Name(name), seconds, False))
                            if _pose_changed(baseline, pose):
                                moving = True
                                break
                        if moving:
                            break
                    sampled_motion = moving
            except Exception as exc:
                sampling_error = f"{type(exc).__name__}: {exc}"
        existing_source = str(entry.get("source_path", ""))
        # The receipt contains source project relative locations, not full paths;
        # source checks were performed by the immutable Stage 2 import plan.
        valid = (loaded_class == "AnimSequence" and saved and skeleton_matches
                 and frames >= 2 and bool(bone_track_names)
                 and sampled_motion is True and sampling_error is None)
        observed.append({
            "source_path": existing_source,
            "target_asset_path": asset_path,
            "actual_class": loaded_class,
            "saved_package_exists": saved,
            "expected_skeleton": target_skeleton_path,
            "actual_skeleton": actual_skeleton_path,
            "skeleton_matches": skeleton_matches,
            "duration_seconds": duration,
            "frame_count": frames,
            "bone_track_count": len(bone_track_names),
            "sampled_bone_motion_observed": sampled_motion,
            "sampling_error": sampling_error,
            "structural_trial_ready": valid,
        })

    all_ok = bool(observed) and all(x["structural_trial_ready"] for x in observed)
    report = {
        "kind": "cutsceneai.studio.animation_readback_audit",
        "schema_version": "0.1.0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_receipt": str(source),
        "source_receipt_sha256": _hash(str(source)),
        "unreal_project": live_project,
        "status": ("PERSISTED_AND_SAMPLED_MOTION_OBSERVED" if all_ok
                   else "REVIEW_REQUIRED"),
        "all_structural_trials_ready": all_ok,
        "rows": observed,
        "fidelity_verified": False,
        "bone_correspondence_verified": False,
        "source_target_pose_parity_verified": False,
        "level_sequence_generated": False,
        "limitations": [
            "Sampled bone motion is a presence check, not skeletal compatibility or pose fidelity proof.",
            "The audit does not measure pose errors against the Unity source or compare playback renders.",
            "A static sample or missing Python animation API requires manual or additional diagnostics.",
        ],
    }
    suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = source.parent / f"animation_readback_audit_{suffix}.json"
    with output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    print("[CutSceneAI] STAGE 2 READBACK:", report["status"])
    for row in observed:
        print("[CutSceneAI]", Path(row["source_path"]).name,
              "frames:", row["frame_count"],
              "bone tracks:", row["bone_track_count"],
              "sampled motion:", row["sampled_bone_motion_observed"],
              "saved:", row["saved_package_exists"])
    print("[CutSceneAI] REPORT:", output)
    print("[CutSceneAI] NOT A SOURCE/TARGET FIDELITY PASS")
    return report


if __name__ == "__main__":
    raise SystemExit("Run from Unreal Python Console via run(receipt_path).")
