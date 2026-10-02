import copy
import sys
from pathlib import Path

VALIDATION_DIR = Path(__file__).resolve().parents[2] / "packages" / "validation"
sys.path.insert(0, str(VALIDATION_DIR))

import core


def _snapshot() -> dict:
    return {
        "schema_version": "0.1.0",
        "engine": {"name": "unreal", "version": "test"},
        "sequence_asset_path": "/Game/CutSceneAI/Benchmark001/LS_Benchmark001",
        "display_rate": {"numerator": 60, "denominator": 1},
        "playback": {"start_frame": 0, "end_frame": 600},
        "bindings": [
            {
                "name": "Floor",
                "binding_id": "floor",
                "canonical_world_transform": {
                    "position_m": [0.0, -0.1, -5.0],
                    "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
                    "scale_xyz": [8.0, 0.2, 12.0],
                },
                "tracks": [],
            },
            {
                "name": "CHARACTER_Guard",
                "binding_id": "guard",
                "tracks": [
                    {
                        "kind": "skeletal_animation",
                        "start_frame": 0,
                        "end_frame": 195,
                        "asset_path": "/Game/CutSceneAI/Benchmark001/Animations/A_CatwalkWalkTurn180",
                        "post_roll_frames": 405,
                        "play_rate": 1.0,
                        "effective_root_delta_cm": [-150.0, 0.0, 0.0],
                        "root_motion_source_profile": {
                            "horizontal_end_distance_cm": 150.0,
                            "vertical_net_displacement_cm": 0.0,
                            "vertical_excursion_cm": 2.5,
                            "sample_count": 40.0,
                        },
                    }
                ],
            },
            {
                "name": "MOVING_PROP",
                "binding_id": "prop",
                "tracks": [
                    {
                        "kind": "transform",
                        "keys": [
                            {
                                "frame": 120,
                                "position_m": [-2.0, 0.5, -5.0],
                                "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
                            },
                            {
                                "frame": 420,
                                "position_m": [2.0, 0.5, -5.0],
                                "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
                            },
                        ],
                    }
                ],
            },
            {
                "name": "CAM_A_Wide",
                "binding_id": "cam-a",
                "camera_state": {
                    "vertical_fov_degrees": 60.0,
                    "target_output_aspect": 16.0 / 9.0,
                },
                "tracks": [],
            },
            {
                "name": "CAM_B_Close",
                "binding_id": "cam-b",
                "camera_state": {
                    "vertical_fov_degrees": 35.0,
                    "target_output_aspect": 16.0 / 9.0,
                },
                "tracks": [
                    {
                        "kind": "camera_lens",
                        "keys": [
                            {"frame": 300, "vertical_fov_degrees": 35.0},
                            {"frame": 599, "vertical_fov_degrees": 25.0},
                        ],
                    }
                ],
            },
        ],
        "camera_cuts": [
            {"start_frame": 0, "end_frame": 300, "camera_binding": "CAM_A_Wide"},
            {"start_frame": 300, "end_frame": 600, "camera_binding": "CAM_B_Close"},
        ],
        "audio_sections": [
            {
                "start_frame": 298,
                "end_frame": 600,
                "asset_path": "/Game/CutSceneAI/Benchmark001/Audio/A_Ominous",
                "loop": False,
            }
        ],
        "markers": [{"frame": 390, "label": "Benchmark_Event_01"}],
    }


def test_exact_readback_passes_all_validation_layers() -> None:
    expected = _snapshot()
    actual = copy.deepcopy(expected)
    actual["engine"]["version"] = "5.8.3"

    report = core.compare(expected, actual)

    assert report["status"] == "PASS"
    assert report["summary"]["failed"] == 0
    assert report["summary"]["incomplete"] == 0


def test_camera_cut_regression_fails() -> None:
    expected = _snapshot()
    actual = copy.deepcopy(expected)
    actual["camera_cuts"][1]["start_frame"] = 301

    report = core.compare(expected, actual)

    assert report["status"] == "FAIL"
    failed_ids = {item["id"] for item in report["checks"] if item["status"] == "FAIL"}
    assert "camera.cuts" in failed_ids


def test_missing_root_motion_measurement_is_incomplete_not_false_pass() -> None:
    expected = _snapshot()
    actual = copy.deepcopy(expected)
    del actual["bindings"][1]["tracks"][0]["effective_root_delta_cm"]

    report = core.compare(expected, actual)

    assert report["status"] == "INCOMPLETE"
    item = next(check for check in report["checks"] if check["id"] == "animation.root_motion.CHARACTER_Guard")
    assert item["status"] == "INCOMPLETE"


def test_root_motion_subcentimeter_import_difference_passes_semantic_gate() -> None:
    expected = _snapshot()
    actual = copy.deepcopy(expected)
    actual["bindings"][1]["tracks"][0]["effective_root_delta_cm"] = [
        -150.02,
        0.01,
        0.39,
    ]

    report = core.compare(expected, actual)

    item = next(
        check for check in report["checks"]
        if check["id"] == "animation.root_motion.CHARACTER_Guard"
    )
    assert item["status"] == "PASS"
    assert item["actual"]["metrics"]["horizontal_endpoint_error_cm"] < 0.5


def test_root_motion_wrong_direction_still_fails() -> None:
    expected = _snapshot()
    actual = copy.deepcopy(expected)
    actual["bindings"][1]["tracks"][0]["effective_root_delta_cm"] = [
        150.0,
        0.0,
        0.0,
    ]

    report = core.compare(expected, actual)

    item = next(
        check for check in report["checks"]
        if check["id"] == "animation.root_motion.CHARACTER_Guard"
    )
    assert item["status"] == "FAIL"
    assert item["actual"]["metrics"]["direction_error_degrees"] > 179.0


def test_root_motion_large_endpoint_drift_fails() -> None:
    expected = _snapshot()
    actual = copy.deepcopy(expected)
    actual["bindings"][1]["tracks"][0]["effective_root_delta_cm"] = [
        -148.0,
        0.0,
        0.0,
    ]

    report = core.compare(expected, actual)

    item = next(
        check for check in report["checks"]
        if check["id"] == "animation.root_motion.CHARACTER_Guard"
    )
    assert item["status"] == "FAIL"
    assert item["actual"]["metrics"]["horizontal_endpoint_error_cm"] > 0.5


def test_grounded_root_motion_allows_small_vertical_import_baseline_difference() -> None:
    expected = _snapshot()
    expected_track = expected["bindings"][1]["tracks"][0]
    expected_track["effective_root_delta_cm"] = [
        -143.279836831084,
        9.377430092622522,
        -0.3940307787440145,
    ]
    expected_track["root_motion_source_profile"] = {
        "horizontal_end_distance_cm": 143.586393,
        "vertical_net_displacement_cm": -0.3940307787440145,
        "vertical_excursion_cm": 2.565968,
        "sample_count": 75.0,
    }

    actual = copy.deepcopy(expected)
    actual["bindings"][1]["tracks"][0]["effective_root_delta_cm"] = [
        -143.2968983194817,
        9.378550322968488,
        -1.0808486938476562,
    ]

    report = core.compare(expected, actual)
    item = next(
        check for check in report["checks"]
        if check["id"] == "animation.root_motion.CHARACTER_Guard"
    )

    assert item["status"] == "PASS"
    assert item["actual"]["policy"]["mode"] == "grounded_low_vertical_excursion"
    assert item["actual"]["metrics"]["horizontal_endpoint_error_cm"] < 0.02
    assert item["actual"]["metrics"]["vertical_error_cm"] < 1.0


def test_material_vertical_excursion_requires_sampled_trajectory_validation() -> None:
    expected = _snapshot()
    expected["bindings"][1]["tracks"][0]["root_motion_source_profile"] = {
        "horizontal_end_distance_cm": 120.0,
        "vertical_net_displacement_cm": 0.0,
        "vertical_excursion_cm": 85.0,
        "sample_count": 80.0,
    }
    actual = copy.deepcopy(expected)

    report = core.compare(expected, actual)
    item = next(
        check for check in report["checks"]
        if check["id"] == "animation.root_motion.CHARACTER_Guard"
    )

    assert item["status"] == "INCOMPLETE"
    assert item["actual"]["policy"]["mode"] == "requires_sampled_vertical_trajectory"
