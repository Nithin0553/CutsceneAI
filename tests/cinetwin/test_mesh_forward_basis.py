"""Phase 10.2: source-approved mesh forward diagnostics must not invent yaw edits.

These are independent synthetic canonical/native observations, never a
claim of real editor execution or mesh/facial/rendered fidelity.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "packages" / "cinetwin") not in sys.path:
    sys.path.insert(0, str(ROOT / "packages" / "cinetwin"))

from mesh_forward_basis import MeshForwardError, bind_profile, compare_mesh_forward


def _native_yaw(degrees: float) -> list[float]:
    angle = math.radians(degrees) / 2
    return [0.0, 0.0, math.sin(angle), math.cos(angle)]


def _canonical_from_unreal(unreal_quat: list[float]) -> list[float]:
    x, y, z, w = unreal_quat
    return [-y, -z, x, w]


def _rows(source_yaws: list[float], target_yaws: list[float], *, mesh="/Game/Guard/Guard"):
    source = []
    target = []
    for i, (src, dst) in enumerate(zip(source_yaws, target_yaws)):
        source.append({
            "time_seconds": i / 30,
            "entities": [{
                "entity_id": "guard",
                "world_transform": {"rotation_xyzw": _canonical_from_unreal(_native_yaw(src))},
            }],
        })
        target.append({
            "time_seconds": i / 30,
            "skeletal_mesh_component_bases": [{
                "entity_id": "guard", "status": "OBSERVED",
                "target_mesh_asset_path": mesh,
                "unreal_component_world_rotation_xyzw": _native_yaw(dst),
            }],
        })
    return source, target


def _profile(unreal_forward=(0.0, 1.0, 0.0)):
    return {
        "source_forward_actor_local_canonical_xyz": [0.0, 0.0, -1.0],
        "target_forward_mesh_local_unreal_xyz": list(unreal_forward),
        "target_mesh_asset_path": "/Game/Guard/Guard",
    }


def test_constant_native_mesh_basis_offset_remains_diagnostic_only():
    src, dst = _rows([0, 30, 75, -60], [0, 30, 75, -60])
    measured = compare_mesh_forward(src, dst, "guard", _profile())
    assert measured["status"] == "FAIL"
    assert measured["max_world_forward_error_degrees"] == pytest.approx(90)
    assert measured["constant_yaw_diagnostic_status"] == (
        "STABLE_SAMPLED_YAW_DIAGNOSTIC_ONLY"
    )
    assert measured["suggested_target_actor_yaw_correction_degrees"] == pytest.approx(-90)
    assert measured["max_sampled_yaw_variation_degrees"] < 1e-4
    assert measured["max_yaw_only_residual_degrees"] < 1e-4
    assert measured["requires_original_full_grid_validation"] is True
    assert measured["native_actor_yaw_repair_authorized"] is False
    assert measured["suggestion_applied"] is False


def test_time_varying_mesh_orientation_never_yields_single_actor_yaw():
    src, dst = _rows([0, 0, 0], [0, 15, 40])
    measured = compare_mesh_forward(src, dst, "guard", _profile())
    assert measured["status"] == "FAIL"
    assert measured["constant_yaw_diagnostic_status"] == (
        "UNSAFE_TIME_VARYING_OR_NON_YAW_ORIENTATION"
    )
    assert measured["suggested_target_actor_yaw_correction_degrees"] is None
    assert measured["max_sampled_yaw_variation_degrees"] > 1
    assert measured["native_actor_yaw_repair_authorized"] is False


def test_nonplanar_mesh_forward_cannot_be_fixed_by_actor_yaw():
    src, dst = _rows([0, 0, 0], [0, 0, 0])
    profile = _profile((0.0, math.sqrt(3) / 2, 0.5))
    measured = compare_mesh_forward(src, dst, "guard", profile)
    assert measured["status"] == "FAIL"
    assert measured["max_world_forward_error_degrees"] > 30
    assert measured["suggested_target_actor_yaw_correction_degrees"] is None
    assert measured["max_yaw_only_residual_degrees"] > 25


def test_insufficient_independent_frames_or_vertical_axes_refuse_yaw():
    source, target = _rows([0], [0])
    one = compare_mesh_forward(source, target, "guard", _profile())
    assert one["constant_yaw_diagnostic_status"] == (
        "INSUFFICIENT_FRAMES_FOR_CONSTANT_YAW"
    )
    assert one["suggested_target_actor_yaw_correction_degrees"] is None

    src, dst = _rows([0, 0], [0, 0])
    profile = {
        "source_forward_actor_local_canonical_xyz": [0, 1, 0],
        "target_forward_mesh_local_unreal_xyz": [0, 0, -1],
        "target_mesh_asset_path": "/Game/Guard/Guard",
    }
    result = compare_mesh_forward(src, dst, "guard", profile)
    assert result["status"] == "FAIL"
    assert result["constant_yaw_diagnostic_status"] == (
        "UNSAFE_NONPLANAR_OR_VERTICAL_FORWARD"
    )
    assert result["suggested_target_actor_yaw_correction_degrees"] is None


def test_matching_forward_axis_and_antipodal_quaternion_pass():
    src, dst = _rows([0, 80, -35], [0, 80, -35])
    for row in dst:
        q = row["skeletal_mesh_component_bases"][0][
            "unreal_component_world_rotation_xyzw"
        ]
        row["skeletal_mesh_component_bases"][0]["unreal_component_world_rotation_xyzw"] = (
            [-value for value in q]
        )
    result = compare_mesh_forward(src, dst, "guard", _profile((1, 0, 0)))
    assert result["status"] == "PASS"
    assert result["suggested_target_actor_yaw_correction_degrees"] == 0
    assert result["constant_yaw_diagnostic_status"] == "ALREADY_WITHIN_TOLERANCE"


@pytest.mark.parametrize("bad_times", [[0, 0, 1], [2, 1, 3], [0, float("nan"), 2]])
def test_duplicate_reversed_and_nan_sample_times_are_refused(bad_times):
    src, dst = _rows([0, 0, 0], [0, 0, 0])
    for rows in (src, dst):
        for row, time in zip(rows, bad_times):
            row["time_seconds"] = time
    with pytest.raises(MeshForwardError, match="strictly increasing"):
        compare_mesh_forward(src, dst, "guard", _profile())


def test_missing_foreign_or_duplicate_native_basis_refuses_instead_of_guessing():
    src, dst = _rows([0, 0], [0, 0])
    dst[1]["skeletal_mesh_component_bases"][0]["target_mesh_asset_path"] = "/Game/Other"
    with pytest.raises(MeshForwardError, match="differs"):
        compare_mesh_forward(src, dst, "guard", _profile())
    dst[1]["skeletal_mesh_component_bases"] = []
    with pytest.raises(MeshForwardError, match="Missing or ambiguous"):
        compare_mesh_forward(src, dst, "guard", _profile())
    dst[1]["skeletal_mesh_component_bases"] = [
        dict(dst[0]["skeletal_mesh_component_bases"][0]),
        dict(dst[0]["skeletal_mesh_component_bases"][0]),
    ]
    with pytest.raises(MeshForwardError, match="Missing or ambiguous"):
        compare_mesh_forward(src, dst, "guard", _profile())


def test_profile_identity_must_be_exact_and_approved():
    plan = {"source": {
        "csir_sha256": "a" * 64, "sequence_ref": "cutA", "project_fingerprint": "p1",
    }}
    target = {"target": {
        "engine_version": "5.8", "project_identity_sha256": "b" * 64,
        "sequence_asset_path": "/Game/Test/LS_New",
    }}
    profile = {
        "kind": "cutsceneai.mesh_forward_approval",
        "schema_version": "1",
        "reviewed_anatomical_axes": True,
        "source_identity": plan["source"].copy(),
        "target_identity": target["target"].copy(),
        "characters": {"guard": _profile()},
    }
    assert bind_profile(profile, plan, target, "guard") == _profile()
    profile["reviewed_anatomical_axes"] = False
    with pytest.raises(MeshForwardError, match="approval"):
        bind_profile(profile, plan, target, "guard")
    profile["reviewed_anatomical_axes"] = True
    profile["target_identity"]["sequence_asset_path"] = "/Game/Other"
    with pytest.raises(MeshForwardError, match="stale"):
        bind_profile(profile, plan, target, "guard")
