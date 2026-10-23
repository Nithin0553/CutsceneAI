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
import scene_prep

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


def _serialized_json(value: Any) -> Any:
    """Compare persisted preparation with the *JSON* form of source-derived data.

    Native planners can contain tuples for vectors/quaternions. JSON correctly
    persists them as arrays; tuple != list must not invalidate honest plans.
    Reject NaN/Infinity because they do not represent interoperable JSON.
    """
    return json.loads(json.dumps(value, allow_nan=False))


# Sub-nanometer / sub-nanodegree absolute tolerance for recomputed float
# values across CPython/Unreal math libraries. This is NOT a cinematic
# fidelity tolerance, and it cannot hide a materially changed key.
PREPARATION_FLOAT_ABS_TOLERANCE = 1e-8


def _first_difference(
    actual: Any, expected: Any, path: str = "$"
) -> str | None:
    """Return first material preparation mismatch, with numerical evidence.

    JSON arrays/maps, keys, action ordering, IDs, booleans, integers and strings
    must match exactly. Finite floating values may differ only by <=1e-8 in
    source-derived units because Unreal and external Python use different math
    libraries. A ±360-degree angle representation change is NOT accepted:
    despite equivalent individual rotations it may affect interpolation.
    """
    if type(actual) is not type(expected):
        return (
            f"{path}: type mismatch: observed={type(actual).__name__}, "
            f"recomputed={type(expected).__name__}"
        )
    if isinstance(expected, dict):
        actual_keys, expected_keys = set(actual), set(expected)
        if actual_keys != expected_keys:
            extra = sorted(actual_keys - expected_keys)
            missing = sorted(expected_keys - actual_keys)
            return f"{path}: extra keys={extra[:5]}, missing keys={missing[:5]}"
        for key in sorted(expected):
            difference = _first_difference(actual[key], expected[key], f"{path}.{key}")
            if difference is not None:
                return difference
    elif isinstance(expected, list):
        if len(actual) != len(expected):
            return f"{path}: length observed={len(actual)}, recomputed={len(expected)}"
        for index, (observed, recalculated) in enumerate(zip(actual, expected)):
            difference = _first_difference(observed, recalculated, f"{path}[{index}]")
            if difference is not None:
                return difference
    elif isinstance(expected, float):
        if (
            not math.isfinite(expected)
            or not math.isfinite(actual)
            or abs(actual - expected) > PREPARATION_FLOAT_ABS_TOLERANCE
        ):
            return (
                f"{path}: observed={actual!r}, recomputed={expected!r}, "
                f"absolute_difference={abs(actual - expected)!r}, "
                f"allowed={PREPARATION_FLOAT_ABS_TOLERANCE}"
            )
    elif actual != expected:
        return f"{path}: observed={actual!r}, recomputed={expected!r}"
    return None


def verify_prepared_artifacts(
    submitted_plan: dict[str, Any],
    submitted_report: dict[str, Any],
    submitted_evidence: dict[str, Any],
    expected_plan: dict[str, Any],
    expected_report: dict[str, Any],
    expected_evidence: dict[str, Any],
) -> None:
    """Check the prepared artifacts against source-derived serialized values.

    The immutable source/mapping/capture hashes and all nonfloating values
    remain exact. Finite floating calculations receive a *tiny* bound to
    accommodate cross-runtime math differences, not a fuzzy motion match.
    This must be called only after recomputing expected input-file digests.
    """
    for name, actual, expected in (
        ("transfer-plan.json", submitted_plan, expected_plan),
        ("coverage-report.json", submitted_report, expected_report),
        ("evidence.json", submitted_evidence, expected_evidence),
    ):
        normalized = _serialized_json(expected)
        # Provenance must match exactly, even if it contains floats someday.
        if name == "evidence.json":
            if actual != normalized:
                difference = _first_difference(actual, normalized)
                raise TransferBackendError(
                    f"{name} provenance mismatch at {difference or '$'}."
                )
            continue
        difference = _first_difference(actual, normalized)
        if difference is not None:
            raise TransferBackendError(
                f"{name} differs materially from source-derived JSON at {difference}. "
                "Do not edit prepared artifacts; diagnose or regenerate into a "
                "new folder if the source files or backend version changed."
            )


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


def _scalar_bake_keys(
    csir: dict[str, Any],
    capture: dict[str, Any],
    entity: dict[str, Any],
    *,
    component_name: str,
    field_name: str,
) -> list[dict[str, Any]]:
    """Build sampled camera/light value tracks at source display-frame timestamps."""
    rate = csir["timing"].get("display_rate") or csir["timing"]["source_rate"]
    hz = float(rate["numerator"]) / float(rate["denominator"])
    start = csir_plan.rational_seconds(csir["timing"]["playback_start"])
    end = csir_plan.rational_seconds(csir["timing"]["playback_end"])
    by_time = {
        round(float(s["time_seconds"]), 8): s
        for s in capture["samples"]
    }
    result = []
    for frame in range(int(math.floor((end - start) * hz + 1e-7))):
        moment = start + frame / hz
        sample = by_time.get(round(moment, 8))
        if sample is None:
            raise TransferBackendError(
                f"Missing source camera/light frame at {moment:.9f}s."
            )
        observed = next(
            (entry for entry in sample["entities"] if entry["entity_id"] == entity["entity_id"]),
            None,
        )
        if observed is None:
            raise TransferBackendError(f"Missing source state for {entity['name']}.")
        value = float(observed.get(component_name, {}).get(field_name, float("nan")))
        if not math.isfinite(value):
            raise TransferBackendError(
                f"Missing finite {component_name}.{field_name} for {entity['name']}."
            )
        result.append({"frame": frame, "value": value})
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
                        status = "NATIVE_PARTIAL"
                        reasons.append(
                            f"Only {len(native_actions)} of {source_sections} "
                            "source sections produced transfer actions; remainder not transferred."
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
        if status in {"NATIVE_UNVERIFIED", "NATIVE_PARTIAL"}:
            additions.extend(native_actions)
        ledger.append({
            "track_index": index,
            "track_id": str(track.get("track_id") or name),
            "track_name": name,
            "track_kind": str(track.get("ced_type", "")),
            "entity_name": entity.get("name", "") if entity else "",
            "source_section_count": len(track.get("sections", [])),
            "native_action_count": len(native_actions) if status in {"NATIVE_UNVERIFIED", "NATIVE_PARTIAL"} else 0,
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
        # Preserve directly measured optical/light behavior as well when the
        # unknown source track belongs to that domain. Do not guess custom
        # exposure, shader, light color or component-specific semantics.
        kinds = {str(csir["tracks"][index].get("ced_type")) for index in track_ids}
        try:
            if entity.get("ced_type") == "entity.camera" and "camera.transform" in kinds:
                fov = _scalar_bake_keys(
                    csir, capture, entity,
                    component_name="camera", field_name="vertical_fov_degrees",
                )
                plan["actions"] = [
                    a for a in plan["actions"] if not (
                        a["kind"] == "camera_fov"
                        and a.get("entity_name") == entity["name"]
                    )
                ]
                plan["actions"].append({
                    "kind": "camera_fov", "entity_name": entity["name"],
                    "actor_label": str(actor_label),
                    "source_fov_axis": "vertical",
                    "target_output_aspect": plan["output_aspect"],
                    "baked_source_curves": True,
                    "keys": fov,
                })
            elif entity.get("ced_type") == "entity.light" and "light.animation" in kinds:
                intensity = _scalar_bake_keys(
                    csir, capture, entity,
                    component_name="light", field_name="intensity",
                )
                plan["actions"] = [
                    a for a in plan["actions"] if not (
                        a["kind"] == "light_intensity"
                        and a.get("entity_name") == entity["name"]
                    )
                ]
                plan["actions"].append({
                    "kind": "light_intensity",
                    "entity_name": entity["name"],
                    "actor_label": str(actor_label),
                    "keys": intensity,
                    "source_behavior_strategy": "sampled_light_intensity",
                })
        except (KeyError, ValueError, TypeError, IndexError) as exc:
            for index in track_ids:
                ledger[index]["details"].append(
                    f"Optical/light scalar fallback unavailable: {exc}"
                )
        for index in track_ids:
            ledger[index]["native_action_count"] = sum(
                action.get("entity_name") == entity["name"]
                and action["kind"] in {"transform", "camera_fov", "light_intensity"}
                for action in plan["actions"]
            )
    # Preserve static actors as native Sequencer poses whenever their CSIR
    # includes an authoritative world transform. A cutscene may contain only
    # static actors or camera cuts; those are valid supported source semantics.
    already_animated = {
        str(a["entity_name"]) for a in plan["actions"]
        if a.get("entity_name") and a["kind"] in {"transform", "skeletal_animation"}
    }
    for entity in csir.get("entities", []):
        if (entity["name"] in already_animated
            or entity["name"] not in mapping.get("entities", {})
            or not isinstance(entity.get("metadata", {}).get("world_transform"), dict)):
            continue
        operation = scene_prep._world_transform(
            entity, str(mapping["entities"][entity["name"]]["actor_label"])
        )
        if operation is None:
            continue
        pitch, yaw, roll = operation["rotation_pitch_yaw_roll_degrees"]
        plan["actions"].append({
            "kind": "transform", "entity_name": entity["name"],
            "actor_label": operation["actor_label"],
            "track_name": "CutSceneAI Static Scene Pose",
            "keys": [{
                "frame": 0,
                "location_cm": list(operation["location_cm"]),
                "rotation_rpy_degrees": [roll, pitch, yaw],
            }],
            "baked_source_curves": False,
            "source_behavior_strategy": "source_static_world_pose",
        })
    if not plan["actions"]:
        raise TransferBackendError(
            "No representable target action. An empty sequence would be misleading."
        )

    counts = dict(Counter(row["outcome"] for row in ledger))
    entity_coverage = [{
        "entity_id": str(e.get("entity_id", "")),
        "source_name": str(e.get("name", "")),
        "source_kind": str(e.get("ced_type", "")),
        "status": ("MAPPED_ACTOR_UNVERIFIED"
                   if e.get("name") in mapping.get("entities", {})
                   else "NO_INDEPENDENT_TARGET_ACTOR"),
    } for e in csir.get("entities", [])]
    asset_coverage = [{
        "asset_id": str(a.get("asset_id", "")),
        "source_name": str(a.get("name", "")),
        "status": ("TARGET_PATH_SPECIFIED_UNVERIFIED"
                   if a.get("name") in mapping.get("assets", {})
                   else "NO_TARGET_ASSET_MAPPING"),
    } for a in csir.get("assets", [])]
    relationships = csir.get("relationships", [])
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
        "source_entities": entity_coverage,
        "source_assets": asset_coverage,
        "source_relationship_count": len(relationships),
        "relationship_fidelity_verified": False,
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
