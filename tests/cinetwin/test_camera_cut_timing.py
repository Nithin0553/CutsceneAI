"""Authored Unity camera cuts versus independent native Sequencer observations."""
from __future__ import annotations

import copy
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "cinetwin"))
sys.path.insert(0, str(ROOT / "integrations" / "unreal"))

import cinetwin_camera_cuts
from behavior_compare import compare
from camera_cut_timing import CameraCutEvidenceError, compare_camera_cut_sections
from sampling_plan import build_plan
from test_behavior_compare import _fixtures


def _cut(start=0, end=4, *, identifier="camera", status="FRAME_ALIGNED"):
    return {
        "source_entity_id": identifier,
        "source_section_id": "shot-a",
        "start_frame": start,
        "end_frame": end,
        "start_seconds": start / 4,
        "end_seconds": end / 4,
        "status": status,
    }


def _native(*, actor="CameraUnreal", first=0, last=4):
    return {
        "status": "OBSERVED",
        "binding_provenance": "NATIVE_SEQUENCE_CAMERA_BINDING_ID",
        "sections": [
            {"actor_label": actor, "start_frame": first, "end_frame": last},
        ],
    }


def test_source_sampling_plan_retains_and_validates_exact_timeline_camera_cut_sections():
    plan, _source, _target = _fixtures()
    csir = {
        "cutscene_id": plan["cutscene_id"],
        "source": plan["source"],
        "timing": {
            "display_rate": {"numerator": 4, "denominator": 1},
            "playback_start": {"value": 0, "rate": {"numerator": 1, "denominator": 1}},
            "playback_end": {"value": 1, "rate": {"numerator": 1, "denominator": 1}},
        },
        "entities": [
            {"entity_id": "camera", "name": "Camera", "ced_type": "entity.camera"},
        ],
        "tracks": [{
            "track_id": "cut-track", "ced_type": "camera.cut",
            "binding_entity_id": "camera",
            "sections": [{
                "section_id": "shot-a",
                "start": {"value": 0, "rate": {"numerator": 1, "denominator": 1}},
                "end": {"value": 1, "rate": {"numerator": 1, "denominator": 1}},
            }],
        }],
    }
    observed = build_plan(csir, csir_sha256="a" * 64)
    assert observed["camera_cuts"] == [_cut()]
    schema = __import__("json").loads(
        (ROOT / "packages/contracts/cinetwin/sampling-plan-v0.1.schema.json").read_text()
    )
    jsonschema.Draft202012Validator(schema).validate(observed)


def test_native_sequencer_camera_cut_reader_uses_real_section_bounds_and_binding():
    class CameraCutTrack:
        def get_sections(self):
            return [NS(get_camera_binding_id=lambda: "native-camera-id")]

    actor = NS(get_actor_label=lambda: "CameraUnreal")
    binding = object()
    api = NS(
        MovieSceneCameraCutTrack=CameraCutTrack,
        UnrealEditorSubsystem=object(),
        MovieSceneSequenceExtensions=NS(
            get_master_tracks=lambda _: [CameraCutTrack()],
            get_bindings=lambda _: [binding],
            get_binding_id=lambda _seq, _binding: "native-camera-id",
            locate_bound_objects=lambda _seq, _binding, _world: [actor],
        ),
        MovieSceneSectionExtensions=NS(
            get_start_frame=lambda _: 0,
            get_end_frame=lambda _: 4,
        ),
        get_editor_subsystem=lambda _: NS(get_editor_world=object),
    )
    actual = cinetwin_camera_cuts.inspect(object(), api)
    assert actual == _native()
    assert actual["binding_provenance"] == "NATIVE_SEQUENCE_CAMERA_BINDING_ID"


def test_missing_native_binding_id_fails_closed_without_guessing():
    class CameraCutTrack:
        def get_sections(self):
            return [object()]

    api = NS(
        MovieSceneCameraCutTrack=CameraCutTrack,
        UnrealEditorSubsystem=object(),
        MovieSceneSequenceExtensions=NS(
            get_master_tracks=lambda _: [CameraCutTrack()],
            get_bindings=lambda _: [], get_binding_id=lambda *_: "",
            locate_bound_objects=lambda *_: [],
        ),
        MovieSceneSectionExtensions=NS(
            get_start_frame=lambda _: 0, get_end_frame=lambda _: 4,
        ),
        get_editor_subsystem=lambda _: NS(get_editor_world=object),
    )
    result = cinetwin_camera_cuts.inspect(object(), api)
    assert result["status"] == "UNAVAILABLE"
    assert result["reason"] == "CAMERA_CUT_BINDING_READBACK_MISSING"
    assert cinetwin_camera_cuts.inspect(object(), NS())["status"] == "UNAVAILABLE"


def test_source_bound_camera_cut_native_section_match_and_wrong_frame():
    plan, source, target = _fixtures()
    plan["camera_cuts"] = [_cut()]
    target["camera_cut_sections"] = _native()
    measured = compare(plan, source, target)
    assert measured["camera_cut_timing"]["status"] == "PASS"
    assert measured["camera_cut_timing"]["matched_sections"] == 1
    assert measured["camera_cut_timing"]["rendered_cut_equivalence_verified"] is False
    assert measured["evaluation"]["camera_cut_timing_status"] == "PASS"

    target["camera_cut_sections"] = _native(last=3)
    measured = compare(plan, source, target)
    assert measured["evaluation"]["status"] == "DIFFERENCES_DETECTED"
    assert measured["camera_cut_timing"]["status"] == "FAIL"


@pytest.mark.parametrize("fault", ["wrong_camera", "missing_cut", "extra_cut", "missing_binding"])
def test_source_target_camera_cut_mismatch_is_reported(fault):
    plan, source, target = _fixtures()
    plan["camera_cuts"] = [_cut()]
    native = _native()
    if fault == "wrong_camera":
        native["sections"][0]["actor_label"] = "OtherCamera"
    elif fault == "missing_cut":
        native["sections"] = []
    elif fault == "extra_cut":
        native["sections"].append(dict(native["sections"][0]))
    elif fault == "missing_binding":
        native.pop("binding_provenance")
        with pytest.raises(CameraCutEvidenceError, match="binding provenance"):
            compare_camera_cut_sections(plan, native, {"camera": "CameraUnreal"})
        return
    target["camera_cut_sections"] = native
    assert compare(plan, source, target)["camera_cut_timing"]["status"] == "FAIL"


def test_unavailable_native_cut_reader_is_incomplete_not_parity():
    plan, source, target = _fixtures()
    plan["camera_cuts"] = [_cut()]
    target["camera_cut_sections"] = {
        "status": "UNAVAILABLE", "reason": "NATIVE_SEQUENCER_CUT_API_UNVERIFIED",
    }
    outcome = compare(plan, source, target)["camera_cut_timing"]
    assert outcome["status"] == "INCOMPLETE"
    assert "NATIVE_SEQUENCER_CUT_API_UNVERIFIED" in outcome["unavailable_reasons"]


def test_subframe_source_cut_is_incomplete_even_if_native_rounds_to_matching_frames():
    plan, source, target = _fixtures()
    plan["camera_cuts"] = [_cut(status="SUBFRAME_CUT_BOUNDARY_UNVERIFIED")]
    target["camera_cut_sections"] = _native()
    assert compare(plan, source, target)["camera_cut_timing"]["status"] == "INCOMPLETE"


def test_camera_cut_overlap_is_not_accepted_as_verified():
    plan, _source, _target = _fixtures()
    plan["camera_cuts"] = [_cut(0, 3), _cut(2, 4)]
    native = _native(last=3)
    native["sections"].append({"actor_label": "CameraUnreal", "start_frame": 2, "end_frame": 4})
    outcome = compare_camera_cut_sections(plan, native, {"camera": "CameraUnreal"})
    assert outcome["status"] == "INCOMPLETE"
    assert "OVERLAPPING_SOURCE_CAMERA_CUTS" in outcome["unavailable_reasons"]


def test_no_source_cut_and_no_native_cut_is_not_applicable():
    plan, _source, _target = _fixtures()
    assert compare_camera_cut_sections(plan, _native(), {"camera": "CameraUnreal"})["status"] == "FAIL"
    assert compare_camera_cut_sections(plan, None, {"camera": "CameraUnreal"})["status"] == "NOT_APPLICABLE"


def test_tampered_source_or_native_frame_bounds_refuse_evidence():
    plan, _source, _target = _fixtures()
    plan = copy.deepcopy(plan)
    plan["camera_cuts"] = [_cut()]
    native = _native()
    native["sections"][0]["start_frame"] = 2.5
    with pytest.raises(CameraCutEvidenceError, match="frame interval"):
        compare_camera_cut_sections(plan, native, {"camera": "CameraUnreal"})
