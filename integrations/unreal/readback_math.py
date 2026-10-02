"""Target-neutral math used by Unreal readback.

These functions intentionally live outside the Unreal runtime API so they can be tested
in CI. They invert the Unreal realization basis back into CutSceneAI canonical space.
"""

from __future__ import annotations

import math
from typing import Iterable


_BASIS = [[0.0, 0.0, -1.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0]]


def unreal_position_cm_to_canonical_m(
    position: Iterable[float],
) -> tuple[float, float, float]:
    x, y, z = (float(value) for value in position)
    return (y / 100.0, z / 100.0, -x / 100.0)


def unreal_scale_to_canonical(scale: Iterable[float]) -> tuple[float, float, float]:
    x, y, z = (float(value) for value in scale)
    return (y, z, x)


def _mat_mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [
        [sum(a[row][k] * b[k][col] for k in range(3)) for col in range(3)]
        for row in range(3)
    ]


def _transpose(value: list[list[float]]) -> list[list[float]]:
    return [[value[col][row] for col in range(3)] for row in range(3)]


def unreal_rpy_to_matrix(
    roll_degrees: float,
    pitch_degrees: float,
    yaw_degrees: float,
) -> list[list[float]]:
    roll = math.radians(float(roll_degrees))
    pitch = math.radians(float(pitch_degrees))
    yaw = math.radians(float(yaw_degrees))

    sin_roll, cos_roll = math.sin(roll), math.cos(roll)
    sin_pitch, cos_pitch = math.sin(pitch), math.cos(pitch)
    sin_yaw, cos_yaw = math.sin(yaw), math.cos(yaw)

    forward = (
        cos_pitch * cos_yaw,
        cos_pitch * sin_yaw,
        sin_pitch,
    )
    zero_roll_right = (-sin_yaw, cos_yaw, 0.0)
    zero_roll_up = (
        -sin_pitch * cos_yaw,
        -sin_pitch * sin_yaw,
        cos_pitch,
    )

    right = tuple(
        zero_roll_right[i] * cos_roll + zero_roll_up[i] * sin_roll for i in range(3)
    )
    up = tuple(
        -zero_roll_right[i] * sin_roll + zero_roll_up[i] * cos_roll for i in range(3)
    )

    return [
        [forward[0], right[0], up[0]],
        [forward[1], right[1], up[1]],
        [forward[2], right[2], up[2]],
    ]


def _matrix_to_quat(matrix: list[list[float]]) -> tuple[float, float, float, float]:
    trace = matrix[0][0] + matrix[1][1] + matrix[2][2]
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        w = 0.25 * scale
        x = (matrix[2][1] - matrix[1][2]) / scale
        y = (matrix[0][2] - matrix[2][0]) / scale
        z = (matrix[1][0] - matrix[0][1]) / scale
    elif matrix[0][0] > matrix[1][1] and matrix[0][0] > matrix[2][2]:
        scale = math.sqrt(1.0 + matrix[0][0] - matrix[1][1] - matrix[2][2]) * 2.0
        w = (matrix[2][1] - matrix[1][2]) / scale
        x = 0.25 * scale
        y = (matrix[0][1] + matrix[1][0]) / scale
        z = (matrix[0][2] + matrix[2][0]) / scale
    elif matrix[1][1] > matrix[2][2]:
        scale = math.sqrt(1.0 + matrix[1][1] - matrix[0][0] - matrix[2][2]) * 2.0
        w = (matrix[0][2] - matrix[2][0]) / scale
        x = (matrix[0][1] + matrix[1][0]) / scale
        y = 0.25 * scale
        z = (matrix[1][2] + matrix[2][1]) / scale
    else:
        scale = math.sqrt(1.0 + matrix[2][2] - matrix[0][0] - matrix[1][1]) * 2.0
        w = (matrix[1][0] - matrix[0][1]) / scale
        x = (matrix[0][2] + matrix[2][0]) / scale
        y = (matrix[1][2] + matrix[2][1]) / scale
        z = 0.25 * scale

    length = math.sqrt(x * x + y * y + z * z + w * w)
    if length <= 1e-12:
        return (0.0, 0.0, 0.0, 1.0)
    return (x / length, y / length, z / length, w / length)


def unreal_rpy_to_canonical_quat(
    roll_degrees: float,
    pitch_degrees: float,
    yaw_degrees: float,
) -> tuple[float, float, float, float]:
    target = unreal_rpy_to_matrix(roll_degrees, pitch_degrees, yaw_degrees)
    basis_t = _transpose(_BASIS)
    canonical = _mat_mul(_mat_mul(basis_t, target), _BASIS)
    return _matrix_to_quat(canonical)


def target_transform_to_canonical(
    location_cm: Iterable[float],
    rotation_rpy_degrees: Iterable[float],
    scale_xyz: Iterable[float],
) -> dict[str, list[float]]:
    roll, pitch, yaw = (float(value) for value in rotation_rpy_degrees)
    return {
        "position_m": list(unreal_position_cm_to_canonical_m(location_cm)),
        "rotation_xyzw": list(unreal_rpy_to_canonical_quat(roll, pitch, yaw)),
        "scale_xyz": list(unreal_scale_to_canonical(scale_xyz)),
    }


def vertical_fov_from_focal_length(sensor_height_mm: float, focal_length_mm: float) -> float:
    sensor_height = float(sensor_height_mm)
    focal_length = float(focal_length_mm)
    if sensor_height <= 0.0 or focal_length <= 0.0:
        raise ValueError("Sensor height and focal length must be positive")
    return math.degrees(2.0 * math.atan(sensor_height / (2.0 * focal_length)))


def vertical_fov_from_horizontal(horizontal_fov_degrees: float, aspect_ratio: float) -> float:
    horizontal = math.radians(float(horizontal_fov_degrees))
    aspect = float(aspect_ratio)
    if aspect <= 0.0:
        raise ValueError("Aspect ratio must be positive")
    return math.degrees(2.0 * math.atan(math.tan(horizontal * 0.5) / aspect))
