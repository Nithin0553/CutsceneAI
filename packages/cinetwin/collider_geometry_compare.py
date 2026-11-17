"""Measure saved collider geometry in canonical meters without a physics claim."""
from __future__ import annotations

import math
from typing import Any

LENGTH_TOLERANCE_M = 0.0001
ORIENTATION_TOLERANCE_DEG = 0.05


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
