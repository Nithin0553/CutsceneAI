"""Engine-independent best-effort Unity -> Unreal planning and coverage accounting.

This planner NEVER labels an omitted feature as converted. It first tries the
existing deterministic CSIR adapter one source track at a time, so one
unsupported track cannot discard all supported tracks. When a complete,
source-authenticated CineTwin capture exists it can bake actor world motion.
Baking actor transforms does not recreate skeletal joint poses or script
behavior; those remain explicitly unverified in the outcome ledger.
"""
from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

import csir_plan
import sampling_plan

NATIVE_GAPS = {
    "event.trigger": "Preserves event timestamp/identity as a marked frame, NOT executable payload.",
    "light.animation": "Light intensity transferred where available; rendered appearance not verified.",
    "audio.track": "Audio timeline sections transferred; waveforms and mixing not verified.",
}


class TransferBackendError(ValueError):
    """Invalid input, incompatible evidence or unsafe transfer request."""


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise TransferBackendError(f"Expected JSON object: {path}")
    return value


def _capture_validated(
    csir: dict[str, Any], path: Path, csir_hash: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    capture = _load(path)
    if capture.get("source", {}).get("csir_sha256") != csir_hash:
        raise TransferBackendError("CineTwin capture CSIR SHA-256 differs from source file.")
    # Derive the exact canonical sampling timestamps from this source CSIR;
    # do not trust truncated, randomly-spaced or made-up motion samples.
    plan = sampling_plan.build_plan(csir, csir_sha256=csir_hash)
    verification = sampling_plan.validate_capture(plan, capture)
    if verification["failures"]:
        raise TransferBackendError(
            f"Source capture failed verification: {'; '.join(verification['failures'][:3])}"
        )
    return capture, verification


def _unwrap(previous: float, current: float) -> float:
    return previous + ((current - previous + 180.0) % 360.0) - 180.0


def _world_keys(
    csir: dict[str, Any],
    capture: dict[str, Any],
    entity: dict[str, Any],
) -> list[dict[str, Any]]:
    """Convert verified source world poses into 24/30/etc-fps Unreal transform keys.

    CineTwin captures include subframe samples near blend boundaries. A target
    frame selects only an exact matching source frame-time sample; no arbitrary
    resampling of unknown physics is presented as source ground truth.
    """
    fps = csir["timing"].get("display_rate") or csir["timing"]["source_rate"]
    hz = float(fps["numerator"]) / float(fps["denominator"])
    start = csir_plan.rational_seconds(csir["timing"]["playback_start"])
    end = csir_plan.rational_seconds(csir["timing"]["playback_end"])
    samples = capture["samples"]
    entity_id = entity["entity_id"]
    by_time = {
        round(float(sample["time_seconds"]), 8): sample
        for sample in samples
    }
    count = int(math.floor((end - start) * hz + 1e-7))
    last_rpy = None
    result = []
    for frame in range(count):
        time_seconds = start + frame / hz
        sample = by_time.get(round(time_seconds, 8))
        if sample is None:
            raise TransferBackendError(
                f"Missing exact evaluated source frame for {entity['name']} "
                f"at t={time_seconds:.9f}s; cannot bake reliably."
            )
        poses = {x["entity_id"]: x for x in sample["entities"]}
        pose = poses.get(entity_id)
        if pose is None:
            raise TransferBackendError(f"No evaluated world pose for {entity['name']}.")
        transform = pose["world_transform"]
        position = tuple(float(x) for x in transform["position_m"])
        rotation = tuple(float(x) for x in transform["rotation_xyzw"])
        values = position + rotation
        if not all(math.isfinite(x) for x in values):
            raise TransferBackendError(f"Non-finite evaluated pose for {entity['name']}.")
        # Unreal expects ROLL/PITCH/YAW in its three rotation channels.
        roll, pitch, yaw = csir_plan.canonical_quat_to_unreal_rotator(rotation)
        rpy = (roll, pitch, yaw)
        if last_rpy is not None:
            rpy = tuple(_unwrap(p, c) for p, c in zip(last_rpy, rpy))
        last_rpy = rpy
        result.append({
            "frame": frame,
            "location_cm": list(csir_plan.canonical_position_to_unreal_cm(position)),
            "rotation_rpy_degrees": list(rpy),
        })
    if not result:
        raise TransferBackendError(f"No frame samples for {entity['name']}.")
    return result


def _native_track(
    csir: dict[str, Any], mapping: dict[str, Any], track: dict[str, Any]
) -> list[dict[str, Any]]:
    isolated = dict(csir)
    isolated["tracks"] = [track]
    plan = csir_plan.build_plan(isolated, mapping)
    # Camera setup is derived from scene entities, not an individual track.
    return [a for a in plan["actions"] if a.get("kind") != "camera_setup"]


def compose(
    csir: dict[str, Any],
    mapping: dict[str, Any],
    *,
    capture: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return conservative target plan plus complete per-track transfer report.

    "BEST_EFFORT" never means "all features converted". Every missing feature
    appears as SKIPPED/BAKED_PARTIAL in the ledger.
    """
    if mapping.get("overwrite_sequence") is True:
        raise TransferBackendError("Refusing to overwrite an existing Level Sequence.")
    if csir.get("schema_version") != "0.1.0" or csir.get("source", {}).get("engine") != "unity":
        raise TransferBackendError("This adapter supports source Unity CSIR v0.1.0.")
    entities = {str(e["entity_id"]): e for e in csir.get("entities", [])}
    # A malformed frame-zero/nonmatching capture must not be used for baking.
    if capture is not None and capture.get("cutscene_id") != csir.get("cutscene_id"):
        raise TransferBackendError("CineTwin cutscene ID differs from CSIR.")
    baseline = dict(csir)
    baseline["tracks"] = []
    try:
        plan = csir_plan.build_plan(baseline, mapping)
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        raise TransferBackendError(f"CSIR base scene cannot be planned: {exc}") from exc

    by_entity_bake: dict[str, list[int]] = {}
    ledger = []
    additions = []
    for index, track in enumerate(csir.get("tracks", [])):
        name = str(track.get("name") or track.get("track_id") or f"track-{index}")
        entity = entities.get(str(track.get("binding_entity_id", "")))
        status = "SKIPPED"
        reasons: list[str] = []
        native_actions: list[dict[str, Any]] = []
        if track.get("muted") is True or not track.get("sections"):
            status = "INACTIVE"
            reasons.append("Muted track or no source sections.")
        else:
            try:
                native_actions = _native_track(csir, mapping, track)
                if native_actions:
                    status = "NATIVE_UNVERIFIED"
                    warnings = NATIVE_GAPS.get(str(track.get("ced_type")))
                    if warnings:
                        reasons.append(warnings)
                    source_sections = len(track.get("sections") or [])
                    if (str(track.get("ced_type")) in {"animation.track", "audio.track"}
                        and len(native_actions) < source_sections):
                        reasons.append(
                            f"Only {len(native_actions)} of {source_sections} "
                            "source sections produced transfer actions."
                        )
                else:
                    reasons.append("No native target action for active source track.")
            except (ValueError, KeyError, TypeError, IndexError, ZeroDivisionError) as exc:
                reasons.append(f"Native converter cannot represent track: {type(exc).__name__}: {exc}")
        if status == "SKIPPED" and capture is not None and entity is not None:
            if (entity.get("name") in mapping.get("entities", {})
                and entity.get("ced_type") != "entity.audio_source"):
                by_entity_bake.setdefault(str(entity["entity_id"]), []).append(index)
                status = "BAKED_PARTIAL"
                reasons.append(
                    "Fallback: evaluated actor world transforms only; no "
                    "skeletal joint equivalence, custom property, script or physics guarantee."
                )
        if status == "NATIVE_UNVERIFIED":
            additions.extend(native_actions)
        ledger.append({
            "track_index": index,
            "track_id": str(track.get("track_id") or name),
            "track_name": name,
            "track_kind": str(track.get("ced_type", "")),
            "entity_name": entity.get("name", "") if entity else "",
            "source_section_count": len(track.get("sections", [])),
            "native_action_count": len(native_actions) if status == "NATIVE_UNVERIFIED" else 0,
            "outcome": status,
            "details": reasons,
        })

    # If a track needs world-pose fallback, do not mix its baked actor-world
    # animation with native transform sections on the SAME actor.
    baked_names = {entities[eid]["name"] for eid in by_entity_bake}
    for action in additions:
        if action["kind"] == "transform" and action.get("entity_name") in baked_names:
            continue
        plan["actions"].append(action)

    for eid, track_ids in sorted(by_entity_bake.items()):
        entity = entities[eid]
        actor_label = mapping["entities"][entity["name"]]["actor_label"]
        try:
            keys = _world_keys(csir, capture, entity)
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            for index in track_ids:
                ledger[index]["outcome"] = "SKIPPED"
                ledger[index]["details"].append(f"World-pose baking rejected: {exc}")
            continue
        plan["actions"].append({
            "kind": "transform", "entity_name": entity["name"],
            "actor_label": str(actor_label),
            "track_name": "CutSceneAI Evaluated World Motion",
            "keys": keys, "baked_source_curves": True,
            "source_behavior_strategy": "frame_sampled_world_pose",
        })
        for index in track_ids:
            ledger[index]["native_action_count"] = 1
    # Bound actors with neither native actions nor fallback still require
    # static scene mapping; keep all explicitly mapped entities from baseline.
    if not plan["actions"]:
        raise TransferBackendError(
            "No representable target action. An empty sequence would be misleading."
        )

    counts = dict(Counter(row["outcome"] for row in ledger))
    summary = {
        "report_kind": "cutsceneai.best_effort_transfer",
        "schema_version": "0.1.0",
        "mode": "BEST_EFFORT",
        "cutscene_id": csir.get("cutscene_id", ""),
        "generation_readiness": "AWAITING_REAL_ENGINE_PREFLIGHT",
        "target_sequence_asset": plan["sequence_asset_path"],
        "source_track_count": len(ledger),
        "accounted_track_count": len(ledger),
        "outcomes": counts,
        "unverified_domains": [
            "skeletal_joint_correspondence", "executable_event_payloads",
            "custom_shader_and_script_behavior", "physics_equivalence",
            "audio_waveform", "render_fidelity", "native_engine_runtime",
        ],
        "no_full_fidelity_claim": True,
        "actions": dict(Counter(a["kind"] for a in plan["actions"])),
        "tracks": ledger,
    }
    return plan, summary


def compose_files(
    csir_path: str | Path, mapping_path: str | Path,
    *, capture_path: str | Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, str]]:
    csir_file = Path(csir_path)
    mapping_file = Path(mapping_path)
    csir = _load(csir_file)
    mapping = _load(mapping_file)
    capture = None
    if capture_path is not None:
        capture, verification = _capture_validated(csir, Path(capture_path), _sha(csir_file))
    else:
        verification = None
    plan, report = compose(csir, mapping, capture=capture)
    report["source_capture_verification"] = verification
    evidence = {
        "csir_sha256": _sha(csir_file),
        "mapping_sha256": _sha(mapping_file),
    }
    if capture_path is not None:
        evidence["source_capture_sha256"] = _sha(Path(capture_path))
        evidence["source_capture_path"] = str(Path(capture_path).resolve())
    return plan, report, evidence
