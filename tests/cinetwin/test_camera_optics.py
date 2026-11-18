"""Frame-matched Unity camera versus native Unreal physical-lens regressions."""
from __future__ import annotations

import copy
import math
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "cinetwin"))

from camera_optics import (  # noqa: E402
    CameraOpticsError,
    NATIVE_BASIS,
    compare_camera_optics,
    observe_native_camera,
)
from behavior_compare import compare  # noqa: E402
from test_behavior_compare import _fixtures  # noqa: E402


def _lens(fov=40.0, focal=50.0):
    height = 2 * focal * math.tan(math.radians(fov) / 2)
    return {
        "status": "OBSERVED",
        "lens_basis": NATIVE_BASIS,
        "sensor_height_mm": height,
        "focal_length_mm": focal,
        "vertical_fov_degrees": fov,
    }


def _with_lens(target, *, fov=40.0):
    for sample in target["samples"]:
        next(x for x in sample["entities"] if x["entity_id"] == "camera")[
            "camera"
        ] = _lens(fov)
    return target


def test_observe_physical_unreal_cine_camera_from_filmback_and_focal_length():
    component = NS(get_editor_property=lambda name: {
        "filmback": NS(get_editor_property=lambda _: 2 * 50 * math.tan(math.radians(20))),
        "current_focal_length": 50.0,
    }[name])
    actor = NS(get_cine_camera_component=lambda: component)
    observed = observe_native_camera(actor)
    assert observed["status"] == "OBSERVED"
    assert observed["vertical_fov_degrees"] == pytest.approx(40)
    assert observed["lens_basis"] == NATIVE_BASIS


def test_unreal_camera_missing_physical_evidence_is_not_assumed_verified():
    assert observe_native_camera(NS()) == {
        "status": "UNAVAILABLE", "reason": "NOT_NATIVE_CINE_CAMERA_ACTOR",
    }
    assert observe_native_camera(NS(get_cine_camera_component=lambda: None))["status"] == "UNAVAILABLE"
    bad = NS(get_editor_property=lambda name: {
        "filmback": NS(get_editor_property=lambda _: 24),
        "current_focal_length": -20,
    }[name])
    assert observe_native_camera(
        NS(get_cine_camera_component=lambda: bad)
    )["reason"] == "NATIVE_LENS_PROPERTIES_UNVERIFIED"


def test_matched_sampled_physical_camera_lens_passes_without_rendered_fidelity():
    plan, source, target = _fixtures()
    _with_lens(target)
    result = compare(plan, source, target)
    optics = result["camera_optics"]
    assert optics["status"] == "PASS"
    assert result["evaluation"]["camera_optics_status"] == "PASS"
    assert optics["per_camera"][0]["comparable_frames"] == len(plan["samples"])
    assert optics["per_camera"][0]["max_vertical_fov_error_degrees"] == pytest.approx(0)
    assert optics["rendered_projection_verified"] is False
    assert optics["shot_cut_timing_verified"] is False
    assert result["camera_cut_timing"]["status"] == "INCOMPLETE"
    assert "camera_cut_timing" in result["unverified_domains"]


def test_wrong_lens_on_single_frame_fails_and_reports_exact_timestamp():
    plan, source, target = _fixtures()
    _with_lens(target)
    frame = target["samples"][3]
    next(x for x in frame["entities"] if x["entity_id"] == "camera")[
        "camera"
    ] = _lens(47)
    result = compare(plan, source, target)
    measured = result["camera_optics"]
    assert measured["status"] == "FAIL"
    assert result["evaluation"]["status"] == "DIFFERENCES_DETECTED"
    assert measured["per_camera"][0]["max_vertical_fov_error_degrees"] == pytest.approx(7)
    assert measured["per_camera"][0]["worst_time_seconds"] == frame["time_seconds"]


def test_animated_camera_lens_matches_at_each_frame():
    plan, source, target = _fixtures()
    for sample_source, sample_target in zip(source["samples"], target["samples"]):
        angle = 38 + 6 * sample_source["time_seconds"]
        next(x for x in sample_source["entities"] if x["entity_id"] == "camera")[
            "camera"
        ]["vertical_fov_degrees"] = angle
        next(x for x in sample_target["entities"] if x["entity_id"] == "camera")[
            "camera"
        ] = _lens(angle)
    assert compare(plan, source, target)["camera_optics"]["status"] == "PASS"


@pytest.mark.parametrize("fault", [
    "all_unobserved", "missing_one", "unmapped", "unverified_basis",
])
def test_missing_or_unknown_optical_evidence_cannot_pass(fault):
    plan, source, target = _fixtures()
    _with_lens(target)
    if fault == "all_unobserved":
        for sample in target["samples"]:
            next(x for x in sample["entities"] if x["entity_id"] == "camera").pop("camera")
    elif fault == "missing_one":
        next(x for x in target["samples"][2]["entities"] if x["entity_id"] == "camera").pop("camera")
    elif fault == "unmapped":
        for sample in target["samples"]:
            sample["entities"] = [x for x in sample["entities"] if x["entity_id"] != "camera"]
        target["coverage"]["unmapped_source_entities"].append({
            "entity_id": "camera", "source_name": "Camera",
        })
    else:
        next(x for x in target["samples"][2]["entities"] if x["entity_id"] == "camera")[
            "camera"
        ] = {"status": "UNAVAILABLE", "reason": "NO_NATIVE_FILMBACK"}
    result = compare(plan, source, target)
    optics = result["camera_optics"]
    assert optics["status"] == "INCOMPLETE"
    assert optics["per_camera"][0]["missing_frames"] >= 1
    assert "camera_optics" in result["unverified_domains"]


@pytest.mark.parametrize("fault", ["physically_inconsistent", "nonfinite", "negative_sensor", "invented_basis"])
def test_false_native_optical_claim_is_rejected(fault):
    plan, source, target = _fixtures()
    _with_lens(target)
    corrupted = next(x for x in target["samples"][0]["entities"] if x["entity_id"] == "camera")[
        "camera"
    ]
    if fault == "physically_inconsistent":
        corrupted["vertical_fov_degrees"] = 80
    elif fault == "nonfinite":
        corrupted["vertical_fov_degrees"] = float("nan")
    elif fault == "negative_sensor":
        corrupted["sensor_height_mm"] = -42
    else:
        corrupted["lens_basis"] = "ASSUMED_FROM_EDITOR_ASPECT"
    with pytest.raises(CameraOpticsError):
        compare(plan, source, target)


def test_comparison_of_absent_camera_domain_is_not_applicable():
    plan, source, target = _fixtures()
    plan = copy.deepcopy(plan)
    plan["entities"] = [x for x in plan["entities"] if x["ced_type"] != "entity.camera"]
    optics = compare_camera_optics(plan, source["samples"], target["samples"])
    assert optics["status"] == "NOT_APPLICABLE" and optics["per_camera"] == []


def test_unaligned_camera_samples_are_never_accepted():
    plan, source, target = _fixtures()
    with pytest.raises(CameraOpticsError, match="frame-aligned"):
        compare_camera_optics(plan, source["samples"], target["samples"][:-1])
