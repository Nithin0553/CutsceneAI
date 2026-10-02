import math
import sys
from pathlib import Path

UNREAL_DIR = Path(__file__).resolve().parents[2] / "integrations" / "unreal"
sys.path.insert(0, str(UNREAL_DIR))

import csir_plan
import readback_math


def _quat_angle(a, b) -> float:
    dot = abs(sum(float(a[i]) * float(b[i]) for i in range(4)))
    dot = max(-1.0, min(1.0, dot))
    return math.degrees(2.0 * math.acos(dot))


def test_unreal_position_and_scale_roundtrip_basis() -> None:
    canonical_position = (2.5, 1.0, -8.0)
    target_position = csir_plan.canonical_position_to_unreal_cm(canonical_position)
    assert readback_math.unreal_position_cm_to_canonical_m(target_position) == canonical_position

    canonical_scale = (0.6, 2.0, 0.6)
    target_scale = (canonical_scale[2], canonical_scale[0], canonical_scale[1])
    assert readback_math.unreal_scale_to_canonical(target_scale) == canonical_scale


def test_rotation_roundtrip_for_benchmark_camera_and_general_euler_samples() -> None:
    samples = [
        (25.0, 0.0, 0.0),
        (0.0, 30.0, 0.0),
        (0.0, 0.0, 10.0),
        (5.0, -58.0, 5.0),
        (-12.0, 140.0, -7.0),
    ]
    for x_deg, y_deg, z_deg in samples:
        canonical = csir_plan.unity_euler_delta_to_canonical_quat(x_deg, y_deg, z_deg)
        roll, pitch, yaw = csir_plan.canonical_quat_to_unreal_rotator(canonical)
        recovered = readback_math.unreal_rpy_to_canonical_quat(roll, pitch, yaw)
        assert _quat_angle(canonical, recovered) < 1e-5


def test_lens_roundtrip_helpers() -> None:
    vertical = 35.0
    sensor_height = 24.0
    focal = sensor_height / (2.0 * math.tan(math.radians(vertical) * 0.5))
    assert abs(readback_math.vertical_fov_from_focal_length(sensor_height, focal) - vertical) < 1e-9
