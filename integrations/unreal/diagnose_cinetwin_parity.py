"""One-run, non-destructive source/target CineTwin world-pose diagnosis.

Evaluates a SAVED Unreal Level Sequence through the editor without saving changes.
It compares source-evaluated Unity world poses against target actor and skeletal
root world poses at every common display frame. This is diagnostic evidence,
NOT verified rendered, audio, event or complete skeletal-animation parity.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ParityDiagnosticError(RuntimeError):
    """Invalid evidence, ambiguous target actor, or unsupported read-only evaluation."""


def _load(path: str | Path) -> dict[str, Any]:
    obj = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(obj, dict):
        raise ParityDiagnosticError("Expected JSON object: " + str(path))
    return obj


def _sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_to_unreal_cm(pos: list[float] | tuple[float, ...]) -> tuple[float, float, float]:
    """Canonical RH (+Y up, -Z forward, meters) -> Unreal LH centimeters."""
    x, y, z = (float(v) for v in pos)
    return (-100.0 * z, 100.0 * x, 100.0 * y)


def _vec(value: Any) -> tuple[float, float, float]:
    return float(value.x), float(value.y), float(value.z)


def _distance(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    return math.dist(a, b)


def _delta(a: tuple[float, ...], origin: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(x - y for x, y in zip(a, origin))


def _bone_alias(bone_id: str) -> str:
    leaf = bone_id.rsplit("/", 1)[-1]
    leaf = re.sub(r"\[\d+\]$", "", leaf)
    return leaf.rsplit(":", 1)[-1].casefold()


def _get_source_index(
    csir: dict[str, Any], capture: dict[str, Any], csir_sha: str,
) -> tuple[dict[int, dict[str, Any]], list[int], float]:
    if csir.get("cutscene_id") != capture.get("cutscene_id"):
        raise ParityDiagnosticError("Source capture cutscene ID differs from CSIR.")
    origin = capture.get("source", {})
    if origin.get("csir_sha256", "").lower() != csir_sha.lower():
        raise ParityDiagnosticError("Source CineTwin capture hash does not match CSIR.")
    for field in ("sequence_ref", "project_fingerprint"):
        expected = csir.get("source", {}).get(field)
        if expected and origin.get(field) != expected:
            raise ParityDiagnosticError("Source capture provenance mismatch: " + field)
    rate = csir["timing"].get("display_rate") or csir["timing"]["source_rate"]
    fps = float(rate["numerator"]) / float(rate["denominator"])
    if not math.isfinite(fps) or fps <= 0:
        raise ParityDiagnosticError("Invalid source frame rate.")
    samples: dict[int, dict[str, Any]] = {}
    errors: dict[int, float] = {}
    for sample in capture.get("samples", []):
        time_s = float(sample["time_seconds"])
        frame = int(round(time_s * fps))
        error = abs(time_s - frame / fps)
        # Exclude intentional subframe transition samples, never treat them as frames.
        if error > 0.0001:
            continue
        if error < errors.get(frame, float("inf")):
            samples[frame] = sample
            errors[frame] = error
    if not samples:
        raise ParityDiagnosticError("No frame-aligned source samples were captured.")
    first = min(samples)
    last = max(samples)
    missing = [frame for frame in range(first, last + 1) if frame not in samples]
    return samples, missing, fps


def _source_entity(sample: dict[str, Any], entity_id: str) -> tuple[float, float, float] | None:
    for entity in sample.get("entities", []):
        if str(entity.get("entity_id")) == entity_id:
            return canonical_to_unreal_cm(entity["world_transform"]["position_m"])
    return None


def _source_bone(
    sample: dict[str, Any], entity_id: str, target_bone: str,
) -> tuple[tuple[float, float, float] | None, str | None]:
    matches = [
        bone for rig in sample.get("skeletal_poses", [])
        if str(rig.get("entity_id")) == entity_id
        for bone in rig.get("bones", [])
        if _bone_alias(str(bone.get("bone_id", ""))) == target_bone.casefold()
    ]
    if len(matches) != 1:
        return None, None
    bone = matches[0]
    return canonical_to_unreal_cm(bone["world_transform"]["position_m"]), str(bone["bone_id"])


def _active_playback_frames(
    source_frames: dict[int, dict[str, Any]], playback_start: int, playback_end: int,
) -> tuple[list[int], list[int]]:
    """Exclude target playback end, which is an exclusive boundary in Sequencer.

    A source CineTwin capture may include the exact sequence end to verify
    boundary semantics. At that point Unreal evaluation may return the LEVEL
    default rather than an authored movie-scene pose. It is not a valid active
    playback frame for pose-error aggregation.
    """
    if playback_end <= playback_start:
        raise ParityDiagnosticError("Target sequence has an invalid playback range.")
    active = sorted(f for f in source_frames if playback_start <= f < playback_end)
    excluded = sorted(set(source_frames) - set(active))
    if not active:
        raise ParityDiagnosticError("Source and target have no matching active playback frames.")
    return active, excluded


def _summarize(samples: list[dict[str, Any]]) -> dict[str, Any]:
    if not samples:
        return {"status": "NO_MATCHED_POSES", "sample_count": 0}
    first = samples[0]
    first_source = first["source_cm"]
    first_target = first["target_cm"]
    records = []
    for item in samples:
        source = item["source_cm"]
        target = item["target_cm"]
        absolute = _distance(source, target)
        relative = _distance(_delta(source, first_source), _delta(target, first_target))
        records.append((item["frame"], absolute, relative))
    worst_abs = max(records, key=lambda x: x[1])
    worst_relative = max(records, key=lambda x: x[2])
    return {
        "status": "MEASURED_NOT_FIDELITY_VERIFIED",
        "sample_count": len(records),
        "first_frame": first["frame"],
        "last_frame": samples[-1]["frame"],
        "first_source_cm": first_source,
        "first_target_cm": first_target,
        "initial_offset_target_minus_source_cm": _delta(first_target, first_source),
        "first_to_last_source_displacement_cm":
            _delta(samples[-1]["source_cm"], first_source),
        "first_to_last_target_displacement_cm":
            _delta(samples[-1]["target_cm"], first_target),
        "mean_absolute_error_cm": sum(x[1] for x in records) / len(records),
        "max_absolute_error_cm": worst_abs[1],
        "max_absolute_error_frame": worst_abs[0],
        "max_offset_removed_motion_error_cm": worst_relative[2],
        "max_offset_removed_motion_error_frame": worst_relative[0],
        "checkpoints": [
            {
                "frame": item["frame"],
                "source_cm": item["source_cm"],
                "target_cm": item["target_cm"],
                "absolute_error_cm": _distance(item["source_cm"], item["target_cm"]),
                "offset_removed_error_cm": _distance(
                    _delta(item["source_cm"], first_source),
                    _delta(item["target_cm"], first_target),
                ),
            }
            for item in samples
            if item["frame"] in (0, 24, 48, 58, 59, 96, 288)
        ],
    }


def _safe_property(obj: Any, name: str) -> Any:
    try:
        return obj.get_editor_property(name)
    except Exception:
        return None


def _track_inventory(sequence: Any, api: Any) -> list[dict[str, Any]]:
    inventory = []
    for binding in sequence.get_bindings():
        record: dict[str, Any] = {"binding": str(binding.get_name()), "tracks": []}
        for track in binding.get_tracks():
            try:
                display = str(track.get_display_name())
            except Exception:
                display = str(_safe_property(track, "display_name"))
            tr: dict[str, Any] = {
                "class": track.get_class().get_name(), "name": display, "sections": [],
            }
            for sec in track.get_sections():
                row: dict[str, Any] = {
                    "class": sec.get_class().get_name(),
                    "start": int(sec.get_start_frame()),
                    "end": int(sec.get_end_frame()),
                }
                if isinstance(track, api.MovieSceneSkeletalAnimationTrack):
                    params = _safe_property(sec, "params")
                    anim = _safe_property(params, "animation") if params else None
                    row["animation_asset"] = anim.get_path_name() if anim else None
                    row["animation_root_motion_enabled"] = (
                        _safe_property(anim, "enable_root_motion") if anim else None
                    )
                    row["source_offset"] = str(_safe_property(params, "start_frame_offset"))
                if isinstance(track, api.MovieScene3DTransformTrack):
                    channels = getattr(sec, "get_all_channels", None)
                    if callable(channels):
                        row["channels"] = []
                        for ch in channels():
                            values = [float(key.get_value()) for key in ch.get_keys()]
                            row["channels"].append({
                                "name": str(_safe_property(ch, "channel_name")),
                                "key_count": len(values),
                                "min": min(values) if values else None,
                                "max": max(values) if values else None,
                            })
                tr["sections"].append(row)
            record["tracks"].append(tr)
        inventory.append(record)
    return inventory


def _component_info(actor: Any, api: Any) -> dict[str, Any]:
    meshes = actor.get_components_by_class(api.SkeletalMeshComponent)
    result: dict[str, Any] = {
        "actor_class": actor.get_class().get_name(),
        "mesh_component_count": len(meshes),
    }
    parent = actor.get_attach_parent_actor()
    result["parent_actor_label"] = parent.get_actor_label() if parent else None
    if len(meshes) == 1:
        mesh = meshes[0]
        result["skeletal_mesh_component_world_cm_frame0"] = _vec(mesh.get_world_location())
        result["mesh_relative_location_property"] = (
            _vec(_safe_property(mesh, "relative_location"))
            if _safe_property(mesh, "relative_location") is not None else None
        )
        result["root_bone_name"] = str(mesh.get_bone_name(0))
        parent_comp = mesh.get_attach_parent()
        result["mesh_attach_parent_component"] = (
            parent_comp.get_name() if parent_comp else None
        )
        return result
    return result


def run(
    *,
    csir_path: str | Path,
    capture_path: str | Path,
    mapping_path: str | Path,
    sequence_path: str,
    output_dir: str | Path,
    unreal_api: Any = None,
) -> dict[str, Any]:
    """Sample every matching source frame vs evaluated saved Unreal sequence.

    No actor, asset, file or mapping is modified; only Sequencer's temporary editor
    playhead/current asset changes, which are restored in a finally block.
    """
    if unreal_api is None:
        import unreal as unreal_api
    csir = _load(csir_path)
    capture = _load(capture_path)
    mapping = _load(mapping_path)
    source_sha = _sha256(csir_path)
    source_frames, missing_frames, fps = _get_source_index(csir, capture, source_sha)
    if len(source_frames) > 3000:
        raise ParityDiagnosticError("Too many frames for one editor diagnostic.")
    sequence = unreal_api.load_asset(sequence_path)
    if not isinstance(sequence, unreal_api.LevelSequence):
        raise ParityDiagnosticError("Target Level Sequence missing: " + sequence_path)
    if mapping.get("overwrite_sequence") is True:
        raise ParityDiagnosticError("Unsafe mapping requests sequence overwrite.")
    playback_frames, excluded_boundary_frames = _active_playback_frames(
        source_frames, int(sequence.get_playback_start()),
        int(sequence.get_playback_end()),
    )

    actor_list = unreal_api.get_editor_subsystem(
        unreal_api.EditorActorSubsystem
    ).get_all_level_actors()
    by_label: dict[str, list[Any]] = {}
    for actor in actor_list:
        by_label.setdefault(str(actor.get_actor_label()), []).append(actor)
    src_by_name = {str(e["name"]): e for e in csir.get("entities", [])}
    target_actors: dict[str, Any] = {}
    entity_report: dict[str, dict[str, Any]] = {}
    for name, binding in mapping.get("entities", {}).items():
        label = str(binding.get("actor_label", "")) if isinstance(binding, dict) else ""
        matches = by_label.get(label, [])
        source = src_by_name.get(name)
        row: dict[str, Any] = {
            "source_name": name, "target_actor_label": label,
            "source_entity_id": source.get("entity_id") if source else None,
            "actor_match_count": len(matches),
            "status": "READY" if source and len(matches) == 1 else "INCOMPLETE",
        }
        if source and len(matches) == 1:
            target_actors[name] = matches[0]
        entity_report[name] = row
    if not target_actors:
        raise ParityDiagnosticError("No unambiguous mapped source actors are in this level.")

    lib = unreal_api.LevelSequenceEditorBlueprintLibrary
    previous = lib.get_current_level_sequence()
    previous_time = lib.get_current_time() if previous else None
    errors: list[str] = []
    records = {name: {"actor": [], "root_bone": []} for name in target_actors}
    try:
        lib.open_level_sequence(sequence)
        for frame in playback_frames:
            sample = source_frames[frame]
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                lib.set_current_time(frame)
            updater = getattr(lib, "force_update", None)
            if callable(updater):
                updater()
            for name, actor in target_actors.items():
                source_id = str(entity_report[name]["source_entity_id"])
                sp = _source_entity(sample, source_id)
                if sp is not None:
                    records[name]["actor"].append({
                        "frame": frame, "source_cm": sp,
                        "target_cm": _vec(actor.get_actor_location()),
                    })
                meshes = actor.get_components_by_class(unreal_api.SkeletalMeshComponent)
                if len(meshes) != 1:
                    continue
                mesh = meshes[0]
                bone_name = str(mesh.get_bone_name(0))
                source_bone, bone_id = _source_bone(sample, source_id, bone_name)
                if source_bone is None:
                    continue
                entity_report[name]["source_root_bone_id"] = bone_id
                records[name]["root_bone"].append({
                    "frame": frame, "source_cm": source_bone,
                    "target_cm": _vec(mesh.get_socket_location(bone_name)),
                })
            if frame == playback_frames[0]:
                for name, actor in target_actors.items():
                    entity_report[name]["actor_world_cm_frame0"] = _vec(actor.get_actor_location())
                    entity_report[name]["component_info_frame0"] = _component_info(
                        actor, unreal_api
                    )
    finally:
        try:
            if previous:
                lib.open_level_sequence(previous)
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", DeprecationWarning)
                    lib.set_current_time(previous_time)
            else:
                lib.close_level_sequence()
        except Exception as exc:
            errors.append("EDITOR_RESTORE_FAILED: " + str(exc))

    asset_report = {}
    for name, path in mapping.get("assets", {}).items():
        asset = unreal_api.load_asset(path) if isinstance(path, str) and path else None
        asset_report[name] = {
            "path": path, "found": asset is not None,
            "class": asset.get_class().get_name() if asset else None,
        }
    for name in target_actors:
        entity_report[name]["actor_world"] = _summarize(records[name]["actor"])
        entity_report[name]["skeletal_root_world"] = _summarize(records[name]["root_bone"])

    result = {
        "kind": "cutsceneai.cinetwin.unreal_world_pose_diagnostic",
        "schema_version": "0.1.0",
        "status": "DIAGNOSTIC_NOT_FIDELITY_VERIFIED",
        "source": {
            "csir_path": str(Path(csir_path).resolve()), "csir_sha256": source_sha,
            "capture_path": str(Path(capture_path).resolve()),
            "capture_sha256": _sha256(capture_path),
            "mapping_path": str(Path(mapping_path).resolve()),
            "mapping_sha256": _sha256(mapping_path),
            "cutscene_id": csir.get("cutscene_id"),
            "source_frames": len(source_frames),
            "evaluated_playback_frames": len(playback_frames),
            "excluded_frames_outside_playback": excluded_boundary_frames,
            "missing_source_frames": missing_frames,
            "fps": fps,
        },
        "target": {
            "project": str(unreal_api.Paths.get_project_file_path()),
            "sequence_path": sequence.get_path_name(),
            "sequence_playback_frames": [
                sequence.get_playback_start(), sequence.get_playback_end()
            ],
            "binding_tracks": _track_inventory(sequence, unreal_api),
            "asset_mappings": asset_report,
        },
        "entities": entity_report,
        "frames": records,
        "errors": errors,
        "limitations": [
            "The saved Unreal playback end is exclusive; out-of-range source end frames are excluded from error aggregates.",
            "Unreal evaluated editor actor and root-bone poses, not rendered pixels.",
            "Matching bones by normalized name does not verify complete rig parity.",
            "Camera image, audio waveforms, event execution and joint-by-joint pose not tested.",
            "One loaded level and existing actor mapping only; no automatic actor staging proven.",
            "Sequencer evaluation uses editor playback; no standalone packaged runtime proof.",
        ],
    }
    folder = Path(output_dir)
    folder.mkdir(parents=True, exist_ok=True)
    datecode = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output = folder / ("CineTwin_WorldPose_Diagnosis_" + datecode + ".json")
    with output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False)
        handle.write("\n")

    print("[CutSceneAI] DIAGNOSIS SAVED:", output)
    print("[CutSceneAI] Source frames:", len(source_frames),
          "Missing:", len(missing_frames), "Mapping actors:", len(entity_report))
    for name, row in entity_report.items():
        summary = row.get("skeletal_root_world") or row.get("actor_world") or {}
        print("[CutSceneAI]", name, ":", row["status"],
              "| pose samples:", summary.get("sample_count", 0),
              "| initial offset:", summary.get("initial_offset_target_minus_source_cm"),
              "| worst motion error cm:",
              round(summary["max_offset_removed_motion_error_cm"], 2)
              if "max_offset_removed_motion_error_cm" in summary else "N/A")
    print("[CutSceneAI] NOT A FIDELITY PASS: inspect full report and known unsupported domains.")
    return result
