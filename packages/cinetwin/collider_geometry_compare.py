"""Measure saved collider geometry in canonical meters without a physics claim."""
from __future__ import annotations

import math
from typing import Any

LENGTH_TOLERANCE_M = 0.0001
ORIENTATION_TOLERANCE_DEG = 0.05
RAY_TOLERANCE_M = 0.002


def compare(shape: str, source: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    errors_m = {"center": math.dist(source["center_m"], observed["center_m"])}
    orientation_deg = None
    if shape in {"box", "capsule"}:
        a, b = source["rotation_xyzw"], observed["rotation_xyzw"]
        norm = math.hypot(*a) * math.hypot(*b)
        if not math.isfinite(norm) or norm <= 0:
            raise ValueError("Collider orientation observation is invalid.")
        cosine = abs(sum(x * y for x, y in zip(a, b)) / norm)
        orientation_deg = math.degrees(2 * math.acos(min(1.0, cosine)))
    if shape == "box":
        errors_m["size"] = max(abs(x - y) for x, y in zip(source["size_m"], observed["size_m"]))
    else:
        errors_m["radius"] = abs(source["radius_m"] - observed["radius_m"])
    if shape == "capsule":
        errors_m["height"] = abs(source["height_m"] - observed["height_m"])
    matched = all(math.isfinite(error) and error <= LENGTH_TOLERANCE_M
                  for error in errors_m.values())
    if orientation_deg is not None:
        matched = matched and orientation_deg <= ORIENTATION_TOLERANCE_DEG
    return {
        "status": "PASS" if matched else "FAIL",
        "comparison_scope": "saved_authoring_geometry",
        "length_errors_m": errors_m,
        "orientation_error_degrees": orientation_deg,
        "tolerances": {"length_m": LENGTH_TOLERANCE_M, "orientation_degrees": ORIENTATION_TOLERANCE_DEG},
        "behavior_verified": False,
    }


def compare_rays(source: list[dict[str, Any]], target: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare native hit/miss and distance for the same world-space rays."""
    result = {
        "status": "INCOMPLETE", "scope": "static_collider_raycast",
        "distance_tolerance_m": RAY_TOLERANCE_M, "rays": [],
    }
    if len(source) != 4 or len(target) != len(source):
        return result
    for index, (expected, actual) in enumerate(zip(source, target)):
        distance_error = None
        match = expected["hit"] == actual["hit"]
        if match and expected["hit"]:
            distance_error = abs(expected["distance_m"] - actual["distance_m"])
            match = math.isfinite(distance_error) and distance_error <= RAY_TOLERANCE_M
        result["rays"].append({
            "index": index, "source_hit": expected["hit"], "target_hit": actual["hit"],
            "source_distance_m": expected["distance_m"], "target_distance_m": actual["distance_m"],
            "distance_error_m": distance_error, "matches": match,
        })
    result["status"] = "PASS" if all(ray["matches"] for ray in result["rays"]) else "FAIL"
    return result
