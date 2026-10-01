from __future__ import annotations

import json
import math
from fractions import Fraction
from pathlib import Path
from typing import Any

PLANNER_VERSION = "0.1.0"

Json = dict[str, Any]


class PlanError(ValueError):
    """Raised when source data cannot be transferred deterministically by this planner."""


def load_json(path: str | Path) -> Json:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise PlanError(f"Expected a JSON object in {path}.")
    return data


def build_transfer_plan(csir: Json, unity_source: Json, mapping: Json) -> Json:
    """Build a deterministic Unity -> Unreal Benchmark 001 transfer plan.

    The function is intentionally independent of Unreal's Python module so it can be
    contract-tested in normal CI. The editor adapter executes the returned plan.
    """
    _validate_inputs(csir, unity_source, mapping)

    timing = _require_dict(csir, "timing")
    display_rate = _read_rate(_require_dict(timing, "display_rate"))
    tick_rate = _read_rate(_require_dict(timing, "tick_resolution"))
    if tick_rate.denominator != 1:
        raise PlanError("Benchmark 001 requires an integer target tick resolution.")

    target = _require_dict(mapping, "target")
    sequence_name = _require_string(target, "sequence_name")
    sequence_path = _require_string(target, "sequence_path")

    entities = {
        _require_string(entity, "entity_id"): entity
        for entity in _require_list(csir, "entities")
    }
    assets = {
        _require_string(asset, "asset_id"): asset
        for asset in _require_list(csir, "assets")
    }
    source_tracks = {
        _require_string(track, "track_id"): track
        for track in _require_list(unity_source, "animation_tracks")
    }
    source_tracks_by_binding = _index_source_tracks_by_binding(source_tracks.values())

    bindings: dict[str, Json] = {}
    operations: list[Json] = []
    warnings: list[str] = []
    quantization: list[Json] = []

    tracks = _require_list(csir, "tracks")
    for track in tracks:
        ced_type = _require_string(track, "ced_type")
        entity = _bound_entity(track, entities)

        if entity is not None and ced_type in {
            "animation.track",
            "camera.cut",
            "camera.transform",
        }:
            _ensure_binding(
                bindings,
                entity,
                mapping,
                source_tracks_by_binding,
                warnings,
            )

        if ced_type == "animation.track":
            if entity is None:
                warnings.append(f"Animation track {_track_name(track)!r} has no bound entity.")
                continue
            if entity.get("ced_type") == "entity.character":
                operations.extend(
                    _plan_character_animation(track, entity, assets, mapping, tick_rate)
                )
            elif entity.get("ced_type") == "entity.prop":
                operations.extend(
                    _plan_transform_animation(
                        track,
                        entity,
                        source_tracks,
                        tick_rate,
                        warnings,
                    )
                )
            else:
                warnings.append(
                    f"Animation track {_track_name(track)!r} is bound to unsupported "
                    f"entity type {entity.get('ced_type')!r}."
                )
        elif ced_type == "camera.transform":
            if entity is None:
                warnings.append(f"Camera transform track {_track_name(track)!r} is unbound.")
                continue
            operations.extend(
                _plan_transform_animation(
                    track,
                    entity,
                    source_tracks,
                    tick_rate,
                    warnings,
                )
            )
            operations.extend(_plan_camera_properties(track, entity, tick_rate))
        elif ced_type == "camera.cut":
            if entity is None:
                raise PlanError(f"Camera cut track {_track_name(track)!r} is unbound.")
            operations.extend(_plan_camera_cut(track, entity, tick_rate))
        elif ced_type == "audio.track":
            operations.extend(_plan_audio(track, assets, mapping, tick_rate))
        elif ced_type == "event.trigger":
            operations.extend(_plan_events(track, assets, tick_rate))
        else:
            warnings.append(
                f"Track {_track_name(track)!r} ({ced_type}) is preserved in CSIR but "
                "has no Benchmark 001 Unreal generator operation."
            )

    playback_start = _time_to_seconds(_require_dict(timing, "playback_start"))
    playback_end = _time_to_seconds(_require_dict(timing, "playback_end"))
    playback_start_tick = _seconds_to_tick(
        playback_start, tick_rate, quantization, "playback_start"
    )
    playback_end_tick = _seconds_to_tick(playback_end, tick_rate, quantization, "playback_end")

    plan: Json = {
        "plan_version": PLANNER_VERSION,
        "transfer_id": f"benchmark001:{_require_string(csir, 'cutscene_id')}",
        "source": {
            "engine": "unity",
            "cutscene_id": _require_string(csir, "cutscene_id"),
            "csir_schema_version": csir.get("schema_version", ""),
            "engine_version": _require_dict(csir, "source").get("engine_version", ""),
            "unity_snapshot_version": unity_source.get("exporter_version", ""),
        },
        "target": {
            "engine": "unreal",
            "sequence_name": sequence_name,
            "sequence_path": sequence_path,
            "level_path": target.get("level_path", ""),
            "display_rate": _rate_to_json(display_rate),
            "tick_resolution": _rate_to_json(tick_rate),
            "playback_start_seconds": float(playback_start),
            "playback_end_seconds": float(playback_end),
            "playback_start_tick": playback_start_tick,
            "playback_end_tick": playback_end_tick,
        },
        "bindings": list(bindings.values()),
        "operations": operations,
        "warnings": warnings,
        "quantization": quantization,
    }
    return plan


def _validate_inputs(csir: Json, unity_source: Json, mapping: Json) -> None:
    if csir.get("schema_version") != "0.1.0":
        raise PlanError(f"Expected CSIR 0.1.0, got {csir.get('schema_version')!r}.")
    source = _require_dict(csir, "source")
    if source.get("engine") != "unity":
        raise PlanError("Benchmark 001 Unreal planner expects a Unity CSIR source.")
    if unity_source.get("engine") != "unity":
        raise PlanError("Unity source snapshot has the wrong engine.")
    if unity_source.get("cutscene_id") != csir.get("cutscene_id"):
        raise PlanError("CSIR and Unity source snapshot refer to different cutscenes.")
    target = _require_dict(mapping, "target")
    if target.get("engine", "unreal") != "unreal":
        raise PlanError("Mapping target.engine must be 'unreal'.")
    _require_dict(mapping, "entities")
    _require_dict(mapping, "assets")


def _index_source_tracks_by_binding(tracks: Any) -> dict[str, list[Json]]:
    result: dict[str, list[Json]] = {}
    for track in tracks:
        binding = track.get("binding_global_object_id", "")
        if binding:
            result.setdefault(binding, []).append(track)
    return result


def _bound_entity(track: Json, entities: dict[str, Json]) -> Json | None:
    entity_id = track.get("binding_entity_id", "")
    if not entity_id:
        return None
    return entities.get(entity_id)


def _ensure_binding(
    bindings: dict[str, Json],
    entity: Json,
    mapping: Json,
    source_tracks_by_binding: dict[str, list[Json]],
    warnings: list[str],
) -> None:
    entity_id = _require_string(entity, "entity_id")
    if entity_id in bindings:
        return

    entity_mapping = _lookup_mapping(_require_dict(mapping, "entities"), entity)
    if entity_mapping is None:
        raise PlanError(
            f"No target entity mapping for {entity.get('name')!r} ({entity_id})."
        )

    preferred_source_track = _preferred_source_track(
        source_tracks_by_binding.get(entity.get("native_ref", ""), [])
    )
    canonical_transform, source_basis = _initial_canonical_transform(
        entity,
        preferred_source_track,
        warnings,
    )
    unreal_transform = _canonical_transform_to_unreal(canonical_transform)

    bindings[entity_id] = {
        "source_entity_id": entity_id,
        "source_name": entity.get("name", ""),
        "ced_type": entity.get("ced_type", ""),
        "kind": entity_mapping.get("kind", ""),
        "asset_path": entity_mapping.get("path")
        or entity_mapping.get("skeletal_mesh")
        or entity_mapping.get("static_mesh")
        or "",
        "initial_transform": unreal_transform,
        "source_transform_basis": source_basis,
    }


def _preferred_source_track(tracks: list[Json]) -> Json | None:
    if not tracks:
        return None
    for track in tracks:
        if track.get("infinite_clip_asset_id"):
            return track
    return tracks[0]


def _initial_canonical_transform(
    entity: Json,
    source_track: Json | None,
    warnings: list[str],
) -> tuple[Json, str]:
    entity_transform = _entity_local_transform(entity)
    if source_track is None:
        return entity_transform, "entity.local_transform"

    offset_mode = source_track.get("track_offset_mode", "")
    animator = _require_dict(_require_dict(entity, "metadata"), "animator")
    controller_ref = animator.get("controller_ref", "")
    if offset_mode == "ApplySceneOffsets" or (offset_mode == "Auto" and controller_ref):
        warnings.append(
            f"{entity.get('name')}: Timeline track offset mode {offset_mode!r} depends "
            "on the bound scene transform. Benchmark 001 planner is using the CSIR "
            "entity transform as the scene-offset base; source snapshot export should "
            "be performed with Timeline Preview disabled."
        )
        base = entity_transform
    else:
        base = _identity_transform()

    track_transform = _transform_from_parts(
        source_track.get("track_position"),
        source_track.get("track_rotation"),
        None,
    )
    base = _compose_transform(base, track_transform)

    if source_track.get("in_clip_mode"):
        clips = source_track.get("clips", [])
        if clips:
            clip = clips[0]
            clip_transform = _transform_from_parts(
                clip.get("clip_offset_position"),
                clip.get("clip_offset_rotation"),
                None,
            )
            base = _compose_transform(base, clip_transform)
            return base, "timeline.track_offset+clip_offset"
    else:
        infinite_transform = _transform_from_parts(
            source_track.get("infinite_clip_offset_position"),
            source_track.get("infinite_clip_offset_rotation"),
            None,
        )
        base = _compose_transform(base, infinite_transform)
        return base, "timeline.track_offset+infinite_clip_offset"

    return base, "timeline.track_offset"


def _entity_local_transform(entity: Json) -> Json:
    metadata = _require_dict(entity, "metadata")
    transform = _require_dict(metadata, "local_transform")
    return {
        "position": _vec3(transform.get("position")),
        "rotation": _quat(transform.get("rotation")),
        "scale": _vec3(transform.get("scale"), default=(1.0, 1.0, 1.0)),
    }


def _plan_character_animation(
    track: Json,
    entity: Json,
    assets: dict[str, Json],
    mapping: Json,
    tick_rate: Fraction,
) -> list[Json]:
    result: list[Json] = []
    for section in _require_list(track, "sections"):
        if section.get("ced_type") != "animation.section":
            continue
        payload = _require_dict(section, "payload")
        asset_id = payload.get("asset_id", "")
        if not asset_id:
            raise PlanError(f"Character animation {_track_name(track)!r} has no asset_id.")
        source_asset = assets.get(asset_id)
        if source_asset is None:
            raise PlanError(f"Animation asset {asset_id!r} was not found in CSIR assets.")
        asset_mapping = _lookup_mapping(_require_dict(mapping, "assets"), source_asset)
        if asset_mapping is None or not asset_mapping.get("path"):
            raise PlanError(
                f"No Unreal animation mapping for source asset "
                f"{source_asset.get('name')!r} ({asset_id})."
            )

        start = _time_to_seconds(_require_dict(section, "start"))
        end = _time_to_seconds(_require_dict(section, "end"))
        clip_in = _time_to_seconds(_require_dict(section, "source_offset"))
        result.append(
            {
                "type": "skeletal_animation",
                "binding_entity_id": _require_string(entity, "entity_id"),
                "source_track": _track_name(track),
                "source_asset_id": asset_id,
                "source_asset_name": source_asset.get("name", ""),
                "target_asset_path": asset_mapping["path"],
                "start_seconds": float(start),
                "end_seconds": float(end),
                "start_tick": _seconds_to_tick(start, tick_rate, None, ""),
                "end_tick": _seconds_to_tick(end, tick_rate, None, ""),
                "clip_in_seconds": float(clip_in),
                "time_scale": float(section.get("time_scale", 1.0)),
                "loop": bool(section.get("loop", False)),
                "apply_foot_ik": bool(
                    _require_dict(payload, "animation").get("apply_foot_ik", False)
                ),
            }
        )
    return result


def _plan_transform_animation(
    track: Json,
    entity: Json,
    source_tracks: dict[str, Json],
    tick_rate: Fraction,
    warnings: list[str],
) -> list[Json]:
    result: list[Json] = []
    source_track = source_tracks.get(track.get("track_id", ""))
    if source_track is None:
        raise PlanError(
            f"Missing Unity source snapshot record for transform track {_track_name(track)!r}."
        )

    base_canonical, source_basis = _initial_canonical_transform(entity, source_track, warnings)
    base_unreal = _canonical_transform_to_unreal(base_canonical)

    for section in _require_list(track, "sections"):
        payload = _require_dict(section, "payload")
        animation = _require_dict(payload, "animation")
        curves = _require_list(animation, "curves")
        transform_curves = [
            curve
            for curve in curves
            if str(curve.get("canonical_semantic", "")).startswith("transform.")
        ]
        if not transform_curves:
            continue

        location_keys = _build_location_keys(transform_curves, base_canonical, tick_rate)
        rotation_keys = _build_rotation_keys(transform_curves, base_canonical, tick_rate)

        result.append(
            {
                "type": "transform_animation",
                "binding_entity_id": _require_string(entity, "entity_id"),
                "source_track": _track_name(track),
                "source_basis": source_basis,
                "section_start_seconds": float(
                    _time_to_seconds(_require_dict(section, "start"))
                ),
                "section_end_seconds": float(
                    _time_to_seconds(_require_dict(section, "end"))
                ),
                "defaults": base_unreal,
                "location_keys": location_keys,
                "rotation_keys": rotation_keys,
            }
        )
    return result


def _build_location_keys(
    curves: list[Json],
    base_transform: Json,
    tick_rate: Fraction,
) -> list[Json]:
    by_axis: dict[str, Json] = {}
    for curve in curves:
        semantic = curve.get("canonical_semantic", "")
        if semantic in {"transform.position.x", "transform.position.y", "transform.position.z"}:
            by_axis[semantic.rsplit(".", 1)[-1]] = curve

    if not by_axis:
        return []

    base_rotation = _quat(base_transform.get("rotation"))
    if not _quat_is_identity(base_rotation):
        raise PlanError(
            "Benchmark 001 v0.1 does not yet compose recorded local-position curves "
            "under a non-identity Timeline base rotation."
        )

    times = _union_curve_times(by_axis.values())
    keys: list[Json] = []
    base_position = _vec3(base_transform.get("position"))
    for time in times:
        delta = (
            _curve_value_at_exact_time(by_axis.get("x"), time, 0.0),
            _curve_value_at_exact_time(by_axis.get("y"), time, 0.0),
            _curve_value_at_exact_time(by_axis.get("z"), time, 0.0),
        )
        canonical_position = tuple(base_position[i] + delta[i] for i in range(3))
        unreal_position = _canonical_position_to_unreal(canonical_position)
        keys.append(
            {
                "time_seconds": time,
                "tick": _float_seconds_to_tick(time, tick_rate),
                "location_cm": {
                    "x": unreal_position[0],
                    "y": unreal_position[1],
                    "z": unreal_position[2],
                },
            }
        )
    return keys


def _build_rotation_keys(
    curves: list[Json],
    base_transform: Json,
    tick_rate: Fraction,
) -> list[Json]:
    by_axis: dict[str, Json] = {}
    for curve in curves:
        if curve.get("canonical_semantic") != "transform.rotation.euler_native":
            continue
        name = str(curve.get("property_name", ""))
        if name.endswith(".x"):
            by_axis["x"] = curve
        elif name.endswith(".y"):
            by_axis["y"] = curve
        elif name.endswith(".z"):
            by_axis["z"] = curve

    if not by_axis:
        return []

    times = _union_curve_times(by_axis.values())
    base_rotation = _quat(base_transform.get("rotation"))
    keys: list[Json] = []
    for time in times:
        native_euler = (
            _curve_value_at_exact_time(by_axis.get("x"), time, 0.0),
            _curve_value_at_exact_time(by_axis.get("y"), time, 0.0),
            _curve_value_at_exact_time(by_axis.get("z"), time, 0.0),
        )
        unity_delta = _unity_euler_zxy_to_quat(native_euler)
        canonical_delta = (-unity_delta[0], -unity_delta[1], unity_delta[2], unity_delta[3])
        canonical_rotation = _quat_mul(base_rotation, canonical_delta)
        unreal_rotation = _canonical_quat_to_unreal(canonical_rotation)
        keys.append(
            {
                "time_seconds": time,
                "tick": _float_seconds_to_tick(time, tick_rate),
                "rotation_quaternion": {
                    "x": unreal_rotation[0],
                    "y": unreal_rotation[1],
                    "z": unreal_rotation[2],
                    "w": unreal_rotation[3],
                },
            }
        )
    return keys


def _plan_camera_properties(track: Json, entity: Json, tick_rate: Fraction) -> list[Json]:
    operations: list[Json] = []
    for section in _require_list(track, "sections"):
        animation = _require_dict(_require_dict(section, "payload"), "animation")
        for curve in _require_list(animation, "curves"):
            property_name = str(curve.get("property_name", "")).strip().lower()
            if property_name not in {"field of view", "fieldofview"}:
                continue
            keys = []
            for key in _require_list(curve, "keys"):
                time_seconds = float(key["time_seconds"])
                keys.append(
                    {
                        "time_seconds": time_seconds,
                        "tick": _float_seconds_to_tick(time_seconds, tick_rate),
                        "value": float(key["value"]),
                    }
                )
            operations.append(
                {
                    "type": "camera_fov",
                    "binding_entity_id": _require_string(entity, "entity_id"),
                    "property_name": "FieldOfView",
                    "keys": keys,
                }
            )
    return operations


def _plan_camera_cut(track: Json, entity: Json, tick_rate: Fraction) -> list[Json]:
    result: list[Json] = []
    for section in _require_list(track, "sections"):
        start = _time_to_seconds(_require_dict(section, "start"))
        end = _time_to_seconds(_require_dict(section, "end"))
        result.append(
            {
                "type": "camera_cut",
                "binding_entity_id": _require_string(entity, "entity_id"),
                "camera_name": entity.get("name", ""),
                "start_seconds": float(start),
                "end_seconds": float(end),
                "start_tick": _seconds_to_tick(start, tick_rate, None, ""),
                "end_tick": _seconds_to_tick(end, tick_rate, None, ""),
            }
        )
    return result


def _plan_audio(
    track: Json,
    assets: dict[str, Json],
    mapping: Json,
    tick_rate: Fraction,
) -> list[Json]:
    result: list[Json] = []
    for section in _require_list(track, "sections"):
        payload = _require_dict(section, "payload")
        asset_id = payload.get("asset_id", "")
        source_asset = assets.get(asset_id)
        if source_asset is None:
            raise PlanError(f"Audio asset {asset_id!r} was not found in CSIR assets.")
        asset_mapping = _lookup_mapping(_require_dict(mapping, "assets"), source_asset)
        if asset_mapping is None or not asset_mapping.get("path"):
            raise PlanError(
                f"No Unreal audio mapping for {source_asset.get('name')!r} ({asset_id})."
            )
        start = _time_to_seconds(_require_dict(section, "start"))
        end = _time_to_seconds(_require_dict(section, "end"))
        source_offset = _time_to_seconds(_require_dict(section, "source_offset"))
        result.append(
            {
                "type": "audio",
                "source_track": _track_name(track),
                "source_asset_id": asset_id,
                "source_asset_name": source_asset.get("name", ""),
                "target_asset_path": asset_mapping["path"],
                "start_seconds": float(start),
                "end_seconds": float(end),
                "start_tick": _seconds_to_tick(start, tick_rate, None, ""),
                "end_tick": _seconds_to_tick(end, tick_rate, None, ""),
                "source_offset_seconds": float(source_offset),
                "loop": bool(section.get("loop", False)),
            }
        )
    return result


def _plan_events(track: Json, assets: dict[str, Json], tick_rate: Fraction) -> list[Json]:
    result: list[Json] = []
    for section in _require_list(track, "sections"):
        signal = _require_dict(_require_dict(section, "payload"), "signal")
        signal_asset_id = signal.get("signal_asset_id", "")
        signal_asset = assets.get(signal_asset_id)
        label = (
            signal_asset.get("name", "")
            if signal_asset is not None
            else _require_dict(section, "payload").get("display_name", "CutSceneAI_Event")
        )
        time = _time_to_seconds(_require_dict(section, "start"))
        result.append(
            {
                "type": "marker",
                "source_track": _track_name(track),
                "label": label or "CutSceneAI_Event",
                "ced_type": section.get("ced_type", "event.trigger"),
                "time_seconds": float(time),
                "tick": _seconds_to_tick(time, tick_rate, None, ""),
                "signal_asset_id": signal_asset_id,
                "emit_once": bool(signal.get("emit_once", False)),
                "retroactive": bool(signal.get("retroactive", False)),
            }
        )
    return result


def _lookup_mapping(mapping_table: Json, source: Json) -> Json | None:
    source_id = str(source.get("entity_id") or source.get("asset_id") or "")
    source_name = str(source.get("name") or "")
    candidate = mapping_table.get(source_id)
    if isinstance(candidate, dict):
        return candidate
    candidate = mapping_table.get(source_name)
    if isinstance(candidate, dict):
        return candidate
    return None


def _time_to_seconds(time_value: Json) -> Fraction:
    value = int(time_value["value"])
    rate = _read_rate(_require_dict(time_value, "rate"))
    return Fraction(value, 1) / rate


def _read_rate(rate: Json) -> Fraction:
    numerator = int(rate["numerator"])
    denominator = int(rate["denominator"])
    if numerator <= 0 or denominator <= 0:
        raise PlanError(f"Invalid rational rate {numerator}/{denominator}.")
    return Fraction(numerator, denominator)


def _rate_to_json(rate: Fraction) -> Json:
    return {"numerator": rate.numerator, "denominator": rate.denominator}


def _seconds_to_tick(
    seconds: Fraction,
    tick_rate: Fraction,
    quantization: list[Json] | None,
    label: str,
) -> int:
    exact = seconds * tick_rate
    tick = _round_fraction(exact)
    error = Fraction(tick, 1) / tick_rate - seconds
    if quantization is not None and error != 0:
        quantization.append(
            {
                "label": label,
                "error_seconds": float(error),
                "target_tick": tick,
            }
        )
    return tick


def _float_seconds_to_tick(seconds: float, tick_rate: Fraction) -> int:
    exact_seconds = Fraction(str(seconds))
    return _seconds_to_tick(exact_seconds, tick_rate, None, "")


def _round_fraction(value: Fraction) -> int:
    if value >= 0:
        return (2 * value.numerator + value.denominator) // (2 * value.denominator)
    positive = -value
    return -((2 * positive.numerator + positive.denominator) // (2 * positive.denominator))


def _track_name(track: Json) -> str:
    return str(track.get("name", track.get("track_id", "<unnamed>")))


def _union_curve_times(curves: Any) -> list[float]:
    times: set[float] = set()
    for curve in curves:
        if curve is None:
            continue
        for key in _require_list(curve, "keys"):
            times.add(float(key["time_seconds"]))
    return sorted(times)


def _curve_value_at_exact_time(curve: Json | None, time: float, default: float) -> float:
    if curve is None:
        return default
    for key in _require_list(curve, "keys"):
        if math.isclose(float(key["time_seconds"]), time, abs_tol=1e-7):
            return float(key["value"])
    raise PlanError(
        f"Curve {curve.get('property_name')!r} has no key aligned to {time:.9f}s. "
        "Benchmark 001 v0.1 only reconstructs aligned transform key times."
    )


def _identity_transform() -> Json:
    return {
        "position": (0.0, 0.0, 0.0),
        "rotation": (0.0, 0.0, 0.0, 1.0),
        "scale": (1.0, 1.0, 1.0),
    }


def _transform_from_parts(position: Any, rotation: Any, scale: Any) -> Json:
    return {
        "position": _vec3(position),
        "rotation": _quat(rotation),
        "scale": _vec3(scale, default=(1.0, 1.0, 1.0)),
    }


def _compose_transform(parent: Json, child: Json) -> Json:
    parent_position = _vec3(parent.get("position"))
    parent_rotation = _quat(parent.get("rotation"))
    parent_scale = _vec3(parent.get("scale"), default=(1.0, 1.0, 1.0))
    child_position = _vec3(child.get("position"))
    child_rotation = _quat(child.get("rotation"))
    child_scale = _vec3(child.get("scale"), default=(1.0, 1.0, 1.0))

    scaled_child = tuple(child_position[i] * parent_scale[i] for i in range(3))
    rotated_child = _quat_rotate(parent_rotation, scaled_child)
    return {
        "position": tuple(parent_position[i] + rotated_child[i] for i in range(3)),
        "rotation": _quat_mul(parent_rotation, child_rotation),
        "scale": tuple(parent_scale[i] * child_scale[i] for i in range(3)),
    }


def _canonical_transform_to_unreal(transform: Json) -> Json:
    position = _canonical_position_to_unreal(_vec3(transform.get("position")))
    rotation = _canonical_quat_to_unreal(_quat(transform.get("rotation")))
    scale = _vec3(transform.get("scale"), default=(1.0, 1.0, 1.0))
    return {
        "location_cm": {"x": position[0], "y": position[1], "z": position[2]},
        "rotation_quaternion": {
            "x": rotation[0],
            "y": rotation[1],
            "z": rotation[2],
            "w": rotation[3],
        },
        "scale": {"x": scale[2], "y": scale[0], "z": scale[1]},
    }


def _canonical_position_to_unreal(
    position: tuple[float, float, float],
) -> tuple[float, float, float]:
    x, y, z = position
    return (-z * 100.0, x * 100.0, y * 100.0)


def _canonical_quat_to_unreal(
    quaternion: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    rotation = _quat_to_matrix(quaternion)
    basis = (
        (0.0, 0.0, -1.0),
        (1.0, 0.0, 0.0),
        (0.0, 1.0, 0.0),
    )
    unreal_rotation = _mat_mul(_mat_mul(basis, rotation), _mat_transpose(basis))
    return _matrix_to_quat(unreal_rotation)


def _unity_euler_zxy_to_quat(
    euler_degrees: tuple[float, float, float],
) -> tuple[float, float, float, float]:
    x, y, z = (math.radians(value) for value in euler_degrees)
    qx = (math.sin(x / 2.0), 0.0, 0.0, math.cos(x / 2.0))
    qy = (0.0, math.sin(y / 2.0), 0.0, math.cos(y / 2.0))
    qz = (0.0, 0.0, math.sin(z / 2.0), math.cos(z / 2.0))
    return _quat_mul(_quat_mul(qy, qx), qz)


def _quat_mul(
    left: tuple[float, float, float, float],
    right: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    lx, ly, lz, lw = left
    rx, ry, rz, rw = right
    result = (
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
        lw * rw - lx * rx - ly * ry - lz * rz,
    )
    return _normalize_quat(result)


def _quat_rotate(
    quaternion: tuple[float, float, float, float],
    vector: tuple[float, float, float],
) -> tuple[float, float, float]:
    rotation = _quat_to_matrix(quaternion)
    return (
        rotation[0][0] * vector[0] + rotation[0][1] * vector[1] + rotation[0][2] * vector[2],
        rotation[1][0] * vector[0] + rotation[1][1] * vector[1] + rotation[1][2] * vector[2],
        rotation[2][0] * vector[0] + rotation[2][1] * vector[1] + rotation[2][2] * vector[2],
    )


def _quat_to_matrix(
    quaternion: tuple[float, float, float, float],
) -> tuple[tuple[float, float, float], ...]:
    x, y, z, w = _normalize_quat(quaternion)
    return (
        (
            1.0 - 2.0 * (y * y + z * z),
            2.0 * (x * y - z * w),
            2.0 * (x * z + y * w),
        ),
        (
            2.0 * (x * y + z * w),
            1.0 - 2.0 * (x * x + z * z),
            2.0 * (y * z - x * w),
        ),
        (
            2.0 * (x * z - y * w),
            2.0 * (y * z + x * w),
            1.0 - 2.0 * (x * x + y * y),
        ),
    )


def _matrix_to_quat(
    matrix: tuple[tuple[float, float, float], ...],
) -> tuple[float, float, float, float]:
    m00, m01, m02 = matrix[0]
    m10, m11, m12 = matrix[1]
    m20, m21, m22 = matrix[2]
    trace = m00 + m11 + m22

    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        quaternion = (
            (m21 - m12) / scale,
            (m02 - m20) / scale,
            (m10 - m01) / scale,
            0.25 * scale,
        )
    elif m00 > m11 and m00 > m22:
        scale = math.sqrt(1.0 + m00 - m11 - m22) * 2.0
        quaternion = (
            0.25 * scale,
            (m01 + m10) / scale,
            (m02 + m20) / scale,
            (m21 - m12) / scale,
        )
    elif m11 > m22:
        scale = math.sqrt(1.0 + m11 - m00 - m22) * 2.0
        quaternion = (
            (m01 + m10) / scale,
            0.25 * scale,
            (m12 + m21) / scale,
            (m02 - m20) / scale,
        )
    else:
        scale = math.sqrt(1.0 + m22 - m00 - m11) * 2.0
        quaternion = (
            (m02 + m20) / scale,
            (m12 + m21) / scale,
            0.25 * scale,
            (m10 - m01) / scale,
        )
    return _normalize_quat(quaternion)


def _mat_mul(
    left: tuple[tuple[float, float, float], ...],
    right: tuple[tuple[float, float, float], ...],
) -> tuple[tuple[float, float, float], ...]:
    return tuple(
        tuple(sum(left[row][k] * right[k][column] for k in range(3)) for column in range(3))
        for row in range(3)
    )


def _mat_transpose(
    matrix: tuple[tuple[float, float, float], ...],
) -> tuple[tuple[float, float, float], ...]:
    return tuple(tuple(matrix[column][row] for column in range(3)) for row in range(3))


def _normalize_quat(
    quaternion: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    length = math.sqrt(sum(component * component for component in quaternion))
    if length <= 1e-12:
        return (0.0, 0.0, 0.0, 1.0)
    return tuple(component / length for component in quaternion)  # type: ignore[return-value]


def _quat_is_identity(quaternion: tuple[float, float, float, float]) -> bool:
    x, y, z, w = _normalize_quat(quaternion)
    return (
        math.isclose(x, 0.0, abs_tol=1e-7)
        and math.isclose(y, 0.0, abs_tol=1e-7)
        and math.isclose(z, 0.0, abs_tol=1e-7)
        and math.isclose(abs(w), 1.0, abs_tol=1e-7)
    )


def _vec3(
    value: Any,
    default: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> tuple[float, float, float]:
    if isinstance(value, (tuple, list)) and len(value) == 3:
        return (float(value[0]), float(value[1]), float(value[2]))
    if not isinstance(value, dict):
        return default
    return (
        float(value.get("x", default[0])),
        float(value.get("y", default[1])),
        float(value.get("z", default[2])),
    )


def _quat(value: Any) -> tuple[float, float, float, float]:
    if isinstance(value, (tuple, list)) and len(value) == 4:
        return _normalize_quat(tuple(float(component) for component in value))
    if not isinstance(value, dict):
        return (0.0, 0.0, 0.0, 1.0)
    return _normalize_quat(
        (
            float(value.get("x", 0.0)),
            float(value.get("y", 0.0)),
            float(value.get("z", 0.0)),
            float(value.get("w", 1.0)),
        )
    )


def _require_dict(parent: Json, key: str) -> Json:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise PlanError(f"Expected object at {key!r}.")
    return value


def _require_list(parent: Json, key: str) -> list[Json]:
    value = parent.get(key)
    if not isinstance(value, list):
        raise PlanError(f"Expected array at {key!r}.")
    if not all(isinstance(item, dict) for item in value):
        raise PlanError(f"Expected object items in array {key!r}.")
    return value


def _require_string(parent: Json, key: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value:
        raise PlanError(f"Expected non-empty string at {key!r}.")
    return value
