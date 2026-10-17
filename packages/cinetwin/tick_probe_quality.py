"""Pure-Python sampling helpers for tick-synchronized Unreal CineTwin probes."""
from __future__ import annotations

import math
from typing import Any


class TickObservationError(ValueError):
    """Invalid or incomplete tick-synchronized observation."""


def choose_times(plan: dict[str, Any], requested: tuple[float, ...] | None) -> list[float]:
    all_times = [float(item["time_seconds"]) for item in plan["samples"]]
    if len(all_times) < 2 or any(not math.isfinite(value) for value in all_times):
        raise TickObservationError("Source sampling plan must contain finite timestamps.")
    if any(b <= a for a, b in zip(all_times, all_times[1:])):
        raise TickObservationError("Source sampling plan times must be increasing.")
    if requested is None:
        return all_times
    if not requested:
        raise TickObservationError("Specify nonempty probe times or None for full plan.")
    result: list[float] = []
    for moment in requested:
        value = float(moment)
        if not math.isfinite(value):
            raise TickObservationError("All probe times must be finite.")
        nearest = min(all_times, key=lambda t: abs(t - value))
        if abs(nearest - value) > 0.05:
            raise TickObservationError(
                f"Requested time {value} s lies outside sampled source timing."
            )
        if nearest not in result:
            result.append(nearest)
    if result != sorted(result):
        raise TickObservationError("Probe times must be chronologically ordered.")
    return result


def max_bone_motion_m(samples: list[dict[str, Any]], rig_id: str) -> float:
    """Measure native target bone motion without cross-engine name assumptions."""
    initial: dict[str, tuple[float, float, float]] = {}
    maximum = 0.0
    if len(samples) < 2:
        raise TickObservationError("At least two instants are required for motion evidence.")
    for i, sample in enumerate(samples):
        poses = [
            entry for entry in sample.get("skeletal_poses", [])
            if entry.get("entity_id") == rig_id
        ]
        if len(poses) != 1:
            raise TickObservationError(f"Sample {i} missing skeletal rig {rig_id}.")
        current: dict[str, tuple[float, float, float]] = {}
        for bone in poses[0].get("bones", []):
            name = str(bone["bone_name"])
            xyz = tuple(float(x) for x in bone["world_position_m"])
            if len(xyz) != 3 or any(not math.isfinite(x) for x in xyz):
                raise TickObservationError(f"Rig {rig_id} has invalid bone position.")
            if name in current:
                raise TickObservationError(f"Rig {rig_id} has duplicate bone {name}.")
            current[name] = xyz  # type: ignore[assignment]
        if i == 0:
            if not current:
                raise TickObservationError(f"Rig {rig_id} has no bones.")
            initial = current
        elif set(current) != set(initial):
            raise TickObservationError(f"Rig {rig_id} changed bone topology.")
        for name, xyz in current.items():
            maximum = max(maximum, math.dist(initial[name], xyz))
    return maximum
