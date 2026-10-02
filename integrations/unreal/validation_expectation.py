"""Build source-derived validation expectations for an Unreal target.

This module is pure Python. It translates the frozen source CSIR into the semantic values
that target readback must reproduce; it does not inspect Unreal runtime state.
"""

from __future__ import annotations

from typing import Any

import csir_plan
import readback_math
import scene_prep


def _binding_table(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(name): {
            "name": str(name),
            "binding_id": "",
            "tracks": [],
        }
        for name in plan.get("bindings", {})
    }


def build_expectation(
    csir: dict[str, Any],
    mapping: dict[str, Any],
) -> dict[str, Any]:
    plan = csir_plan.build_plan(csir, mapping)
    bindings = _binding_table(plan)

    # Static/prepared actor transforms. Dynamic actors intentionally omitted by scene_prep
    # are validated from their Sequencer transform keys instead.
    for operation in scene_prep.build_scene_prep(csir, mapping):
        name = str(operation["actor_label"])
        if name not in bindings:
            continue
        bindings[name]["canonical_world_transform"] = readback_math.target_transform_to_canonical(
            operation["location_cm"],
            (
                operation["rotation_pitch_yaw_roll_degrees"][2],
                operation["rotation_pitch_yaw_roll_degrees"][0],
                operation["rotation_pitch_yaw_roll_degrees"][1],
            ),
            operation["scale_xyz"],
        )

    camera_cuts: list[dict[str, Any]] = []
    audio_sections: list[dict[str, Any]] = []
    markers: list[dict[str, Any]] = []

    for action in plan.get("actions", []):
        kind = str(action.get("kind", ""))

        if kind == "transform":
            name = str(action["entity_name"])
            if name not in bindings:
                continue
            keys: list[dict[str, Any]] = []
            for key in action.get("keys", []):
                roll, pitch, yaw = (
                    float(key["rotation_rpy_degrees"][0]),
                    float(key["rotation_rpy_degrees"][1]),
                    float(key["rotation_rpy_degrees"][2]),
                )
                canonical = readback_math.target_transform_to_canonical(
                    key["location_cm"],
                    (roll, pitch, yaw),
                    (1.0, 1.0, 1.0),
                )
                keys.append(
                    {
                        "frame": int(key["frame"]),
                        "position_m": canonical["position_m"],
                        "rotation_xyzw": canonical["rotation_xyzw"],
                    }
                )
            bindings[name]["tracks"].append({"kind": "transform", "keys": keys})

        elif kind == "skeletal_animation":
            name = str(action["entity_name"])
            if name not in bindings:
                continue
            track: dict[str, Any] = {
                "kind": "skeletal_animation",
                "start_frame": int(action["start_frame"]),
                "end_frame": int(action["end_frame"]),
                "asset_path": str(action["unreal_asset_path"]),
                "post_roll_frames": max(
                    0,
                    int(action.get("hold_end_frame", action["end_frame"]))
                    - int(action["end_frame"]),
                ),
                "completion_mode": str(action.get("completion_mode", "project_default")),
            }
            expected_root_delta = action.get("expected_root_delta_cm")
            if expected_root_delta is not None:
                track["effective_root_delta_cm"] = [
                    float(value) for value in expected_root_delta
                ]
            bindings[name]["tracks"].append(track)

        elif kind == "camera_setup":
            name = str(action["entity_name"])
            if name in bindings:
                bindings[name]["camera_state"] = {
                    "vertical_fov_degrees": float(action["field_of_view_degrees"]),
                    "target_output_aspect": float(action["target_output_aspect"]),
                }

        elif kind == "camera_fov":
            name = str(action["entity_name"])
            if name not in bindings:
                continue
            bindings[name]["tracks"].append(
                {
                    "kind": "camera_lens",
                    "keys": [
                        {
                            "frame": int(key["frame"]),
                            "vertical_fov_degrees": float(key["value"]),
                        }
                        for key in action.get("keys", [])
                    ],
                }
            )

        elif kind == "camera_cut":
            camera_cuts.append(
                {
                    "start_frame": int(action["start_frame"]),
                    "end_frame": int(action["end_frame"]),
                    "camera_binding": str(action["entity_name"]),
                }
            )

        elif kind == "audio":
            audio_sections.append(
                {
                    "start_frame": int(action["start_frame"]),
                    "end_frame": int(action["end_frame"]),
                    "asset_path": str(action["unreal_asset_path"]),
                    "loop": bool(action.get("loop", False)),
                }
            )

        elif kind == "marker":
            markers.append(
                {
                    "frame": int(action["frame"]),
                    "label": str(action["label"]),
                }
            )

    return {
        "schema_version": "0.1.0",
        "engine": {"name": "unreal", "version": "source-derived-expectation"},
        "sequence_asset_path": str(plan["sequence_asset_path"]),
        "display_rate": dict(plan["display_rate"]),
        "playback": {
            "start_frame": 0,
            "end_frame": int(plan["duration_frames"]),
        },
        "bindings": list(bindings.values()),
        "camera_cuts": camera_cuts,
        "audio_sections": audio_sections,
        "markers": markers,
    }
