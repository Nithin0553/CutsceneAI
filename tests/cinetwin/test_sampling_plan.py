"""Regression tests for source-derived CineTwin sampling and capture verification."""
import copy
import json
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "cinetwin"))
import sampling_plan


def _time(numerator: int, rate: int = 1_000_000) -> dict:
    return {"value": numerator, "rate": {"numerator": rate, "denominator": 1}}


def _section(name: str, start: int, end: int, *, blend_in=0, blend_out=0) -> dict:
    return {
        "section_id": name, "ced_type": "animation.section",
        "start": _time(start), "end": _time(end), "payload": {},
        "native_payload": {
            "blend_in_seconds": blend_in,
            "blend_out_seconds": blend_out,
        },
    }


def _csir() -> dict:
    return {
        "cutscene_id": "scene:example",
        "source": {
            "engine": "unity", "engine_version": "6000.3.8f1",
            "sequence_ref": "Assets/Timeline.playable|guid=abc|local=1",
            "project_fingerprint": "sha256:test",
        },
        "timing": {
            "display_rate": {"numerator": 24, "denominator": 1},
            "playback_start": _time(0),
            "playback_end": _time(4_000_000),
        },
        "entities": [
            {
                "entity_id": "entity:a", "name": "Actor", "ced_type": "entity.character",
                "metadata": {"hierarchy_path": "Scene/Actor"},
            },
            {
                "entity_id": "entity:cam", "name": "Camera", "ced_type": "entity.camera",
                "parent_entity_id": "entity:a",
                "metadata": {"hierarchy_path": "Scene/Actor/Camera"},
            },
            {
                "entity_id": "entity:light", "name": "Light", "ced_type": "entity.light",
                "metadata": {"hierarchy_path": "Scene/Light"},
            },
        ],
        "tracks": [
            {
                "track_id": "track:animation", "ced_type": "animation.track",
                "sections": [
                    _section("walk", 0, 2_458_333, blend_out=0.4583333333333335),
                    _section("idle", 2_000_000, 4_000_000, blend_in=0.4583333333333335),
                ],
            },
            {
                "track_id": "track:event", "ced_type": "event.trigger",
                "sections": [_section("signal", 2_500_000, 2_500_000)],
            },
        ],
    }


def _capture(plan: dict) -> dict:
    def state(entry: dict) -> dict:
        record = {
            "entity_id": entry["entity_id"],
            "world_transform": {
                "position_m": [1, 0, 0],
                "rotation_xyzw": [0, 0, 0, 1],
                "scale_xyz": [1, 1, 1],
            },
        }
        if entry["ced_type"] == "entity.camera":
            record["camera"] = {"vertical_fov_degrees": 35.0}
        if entry["ced_type"] == "entity.light":
            record["light"] = {"intensity": 1.0}
        return record

    return {
        "schema_version": "0.1.0",
        "kind": "cinetwin.behavior_capture",
        "cutscene_id": plan["cutscene_id"],
        "source": dict(plan["source"]),
        "capture_layers": [
            {"layer": item["layer"], "status": (
                "CAPTURED" if item["status"] == "PLANNED" else "NOT_IMPLEMENTED"
            )}
            for item in plan["capabilities"]
        ],
        "samples": [
            {"time_seconds": sample["time_seconds"],
             "entities": [state(entity) for entity in plan["entities"]]}
            for sample in plan["samples"]
        ],
        "errors": [],
        "provenance": {
            "method": "PlayableDirector.Evaluate",
            "engine_version": "6000.3.8f1",
            "captured_at_utc": "2026-10-17T12:00:00Z",
            "play_mode": True,
        },
    }


def _validate_schema(file_name: str, artifact: dict) -> None:
    contract = (
        ROOT / "packages" / "contracts" / "cinetwin" / file_name
    )
    jsonschema.Draft202012Validator(
        json.loads(contract.read_text(encoding="utf-8"))
    ).validate(artifact)


def test_sample_schedule_includes_frames_events_clip_edges_and_blend_interiors() -> None:
    plan = sampling_plan.build_plan(_csir())
    times = [item["time_seconds"] for item in plan["samples"]]
    assert times[0] == 0.0
    assert times[-1] == 4.0
    assert 2.0 in times
    assert 2.5 in times
    assert 2.458333 in times
    assert len(times) > 97  # base 24fps + critical subframe blend samples
    assert times == sorted(set(times))
    events = [entry for entry in plan["samples"] if entry["time_seconds"] == 2.5]
    assert any(reason.startswith("event:") for reason in events[0]["reasons"])
    assert any(
        "blend_in_interior" in reason
        for sample in plan["samples"]
        for reason in sample["reasons"]
    )
    _validate_schema("sampling-plan-v0.1.schema.json", plan)


def test_source_entity_identity_and_ancestry_preserved() -> None:
    plan = sampling_plan.build_plan(_csir(), csir_sha256="123")
    assert plan["source"]["csir_sha256"] == "123"
    assert plan["entities"][1]["parent_entity_id"] == "entity:a"
    assert plan["entities"][1]["hierarchy_path"] == "Scene/Actor/Camera"


def test_fractional_frame_rate_and_narrow_event_uses_exact_time() -> None:
    source = _csir()
    source["timing"]["display_rate"] = {"numerator": 24000, "denominator": 1001}
    source["tracks"][1]["sections"][0]["start"] = _time(1_234_567)
    source["tracks"][1]["sections"][0]["end"] = _time(1_234_567)
    plan = sampling_plan.build_plan(source)
    assert any(sample["time_seconds"] == 1.234567 for sample in plan["samples"])


def test_invalid_section_bounds_rejected() -> None:
    source = _csir()
    source["tracks"][0]["sections"][0]["end"] = _time(-1)
    with pytest.raises(sampling_plan.SamplingPlanError):
        sampling_plan.build_plan(source)


def test_valid_capture_has_explicit_incomplete_global_coverage() -> None:
    plan = sampling_plan.build_plan(_csir())
    capture = _capture(plan)
    _validate_schema("behavior-capture-v0.1.schema.json", capture)
    report = sampling_plan.validate_capture(plan, capture)
    assert report["status"] == "INCOMPLETE"
    assert report["failures"] == []
    assert "skeletal_pose" in report["not_verified"]


def test_missing_entity_or_camera_state_fails_closed() -> None:
    plan = sampling_plan.build_plan(_csir())
    capture = _capture(plan)
    capture["samples"][4]["entities"].pop()
    report = sampling_plan.validate_capture(plan, capture)
    assert report["status"] == "FAIL"
    assert "missing, extra, or repeated entities" in str(report["failures"])

    capture = _capture(plan)
    del capture["samples"][0]["entities"][1]["camera"]
    report = sampling_plan.validate_capture(plan, capture)
    assert report["status"] == "FAIL"
    assert "missing camera state" in str(report["failures"])


def test_source_hash_mismatch_and_missing_samples_fail() -> None:
    plan = sampling_plan.build_plan(_csir(), csir_sha256="expected")
    capture = _capture(plan)
    capture["source"]["csir_sha256"] = "wrong"
    capture["samples"] = capture["samples"][:-1]
    report = sampling_plan.validate_capture(plan, capture)
    assert report["status"] == "FAIL"
    assert len(report["failures"]) >= 2


def test_unsupported_capture_layers_are_not_invented() -> None:
    plan = sampling_plan.build_plan(_csir())
    capture = _capture(plan)
    capture["capture_layers"] = [
        {"layer": entry["layer"], "status": "CAPTURED"}
        for entry in plan["capabilities"]
    ]
    report = sampling_plan.validate_capture(plan, capture)
    assert report["status"] == "FAIL"
    assert "claims unsupported" in str(report["failures"])


def test_export_source_input_is_not_modified() -> None:
    source = _csir()
    before = copy.deepcopy(source)
    sampling_plan.build_plan(source)
    assert source == before


def test_cinetwin_unity_capture_is_play_mode_only_and_separate_from_extractor() -> None:
    editor_root = ROOT / "integrations/unity/com.cutsceneai.extractor"
    capture = (editor_root / "CineTwin/Editor/CineTwinBehaviorCapture.cs").read_text(
        encoding="utf-8"
    )
    structural = (editor_root / "Editor/UnityTimelineExtractor.cs").read_text(
        encoding="utf-8"
    )
    assert "EditorApplication.isPlaying" in capture
    assert "director.Evaluate();" in capture
    assert "SaveScene(" not in capture
    assert "SaveAssets(" not in capture
    assert "PlayableDirector.Evaluate" not in structural
