"""Element 3.5: CineTwin source-bound attribution and bounded remeasurement."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for directory in ("studio", "ced", "cinetwin"):
    sys.path.insert(0, str(ROOT / "packages" / directory))
sys.path.insert(0, str(ROOT / "tests" / "cinetwin"))

import ced_agent_knowledge as ced
import studio_element_cinetwin as audit
import studio_element_plan as elements
from sampling_plan import build_plan
from test_behavior_compare import _fixtures


def _time(value: int) -> dict:
    return {"value": value, "rate": {"numerator": 1, "denominator": 1}}


def _inputs():
    # Reuse the independently tested CineTwin source and target fixture;
    # reconstruct its exact CSIR source, not a hand-written fake report.
    csir = {
        "cutscene_id": "unit-test-cinematic",
        "source": {
            "engine": "unity", "engine_version": "6000.3.8f1",
            "sequence_ref": "Assets/timeline.playable|guid=a|local=1",
            "project_fingerprint": "sha256:fixture",
        },
        "timing": {
            "display_rate": {"numerator": 4, "denominator": 1},
            "playback_start": _time(0), "playback_end": _time(1),
        },
        "entities": [
            {"entity_id": "character", "name": "Alice", "ced_type": "entity.character"},
            {"entity_id": "camera", "name": "Camera", "ced_type": "entity.camera"},
            {"entity_id": "audio", "name": "Sound", "ced_type": "entity.audio"},
        ],
        "tracks": [{
            "track_id": "animate", "ced_type": "animation.track",
            "binding_entity_id": "character",
            "sections": [{
                "section_id": "walk", "ced_type": "animation.section",
                "start": _time(0), "end": _time(1), "payload": {},
            }],
        }],
    }
    sampling, source, target = _fixtures()
    assert sampling == build_plan(csir, csir_sha256="ab" * 32)
    native = {
        "sequencer_skeletal_animation_track": True,
        "cine_camera_actor": True,
    }
    knowledge = ced.retrieve_all(
        csir, target_capabilities=native, source_version="6000.3.8f1",
        target_version="5.8",
    )
    conversion = elements.prepare(csir, knowledge, native)
    return csir, conversion, sampling, source, target


def _item(report, location, conversion):
    ident = next(row["occurrence_id"] for row in conversion["elements"]
                 if row["source_location"] == location)
    return next(row for row in report["occurrences"]
                if row["occurrence_id"] == ident)


def _offset(target, centimeters=7.0):
    for frame in target["samples"]:
        frame["entities"][0]["world_transform"]["position_m"][0] += centimeters / 100.0


def _target_identity(target):
    target["target"] = {
        "project_identity_sha256": "c" * 64,
        "sequence_asset_path": "/Game/Acceptance/LS_Test",
    }


def test_per_occurrence_pass_context_incomplete_and_unmapped_are_not_fidelity():
    csir, conversion, sampling, source, target = _inputs()
    report = audit.build(csir, conversion, sampling, source, target)
    assert report["source_occurrence_count"] == len(conversion["elements"])
    assert all(not item["native_repair_authorized"] and
               not item["full_cutscene_fidelity_verified"]
               for item in report["occurrences"])
    assert report["full_cutscene_fidelity_verified"] is False
    character = _item(report, "entities[0]", conversion)
    assert character["measurement_status"] == "DIRECT_MEASUREMENT_INCOMPLETE"
    assert character["measured"]["actor_position_cm"] == 0.0
    assert character["recovery_hint"] == "DIAGNOSTIC_REVIEW_ONLY"
    cam = _item(report, "entities[1]", conversion)
    assert cam["measurement_status"] == "DIRECT_MEASUREMENT_INCOMPLETE"
    assert cam["measured"]["camera_lens_status"] == "INCOMPLETE"
    audio = _item(report, "entities[2]", conversion)
    assert audio["measurement_status"] == "INCOMPLETE_TARGET_UNMAPPED"
    track = _item(report, "tracks[0]", conversion)
    assert track["measurement_status"] == "LINKED_CONTEXT_NOT_CAUSAL_ATTRIBUTION"
    assert track["bound_entity_occurrence"] == character["occurrence_id"]
    section = _item(report, "tracks[0].sections[0]", conversion)
    assert section["measurement_status"] == "LINKED_CONTEXT_NOT_CAUSAL_ATTRIBUTION"
    assert len(report["unverified_domains"]) > 0
    audit.verify(report, csir, conversion, sampling, source, target)


def test_native_discrepancy_is_direct_for_actor_only_not_parent_track():
    csir, conversion, sampling, source, target = _inputs()
    _offset(target)
    report = audit.build(csir, conversion, sampling, source, target)
    character = _item(report, "entities[0]", conversion)
    assert character["measurement_status"] == "DIRECT_MEASURED_DIFFERENCE"
    assert character["measured"]["actor_position_cm"] == pytest.approx(7)
    assert "WORLD_POSITION_OUTSIDE_TOLERANCE" in character["discrepancy_flags"]
    assert character["recovery_hint"] == (
        "INSPECT_EXISTING_USER_AUTHORIZED_CHARACTER_OFFSET_POLICY"
    )
    track = _item(report, "tracks[0]", conversion)
    assert track["measurement_status"] == "LINKED_CONTEXT_NOT_CAUSAL_ATTRIBUTION"
    assert track["discrepancy_flags"] == ["BOUND_ENTITY_HAS_MEASURED_DIFFERENCE"]
    assert track["native_repair_authorized"] is False
    assert report["target_identity_sha256"] is None


def test_source_and_sample_plan_hash_and_coverage_cannot_be_spoofed():
    csir, conversion, sampling, source, target = _inputs()
    csir["cutscene_id"] = "FOREIGN"
    with pytest.raises(audit.ElementCineTwinError, match="stale"):
        audit.build(csir, conversion, sampling, source, target)
    csir, conversion, sampling, source, target = _inputs()
    sampling["samples"][0]["time_seconds"] = 0.125
    with pytest.raises(audit.ElementCineTwinError, match="Sampling plan"):
        audit.build(csir, conversion, sampling, source, target)
    csir, conversion, sampling, source, target = _inputs()
    target["samples"].pop()
    with pytest.raises(audit.ElementCineTwinError, match="failed validation"):
        audit.build(csir, conversion, sampling, source, target)


def test_recomputed_attribution_hash_cannot_hide_altered_flags_or_identity():
    csir, conversion, sampling, source, target = _inputs()
    _offset(target)
    report = audit.build(csir, conversion, sampling, source, target)
    tampered = copy.deepcopy(report)
    tampered["occurrences"][0]["discrepancy_flags"].clear()
    tampered.pop("attribution_sha256")
    tampered["attribution_sha256"] = elements._digest(tampered)
    with pytest.raises(audit.ElementCineTwinError, match="tampered"):
        audit.verify(tampered, csir, conversion, sampling, source, target)
    unknown = copy.deepcopy(conversion)
    unknown["elements"].pop()
    with pytest.raises(audit.ElementCineTwinError):
        audit.build(csir, unknown, sampling, source, target)


def test_report_redacts_private_source_ids_names_assets_and_target_actor_labels():
    csir, conversion, sampling, source, target = _inputs()
    csir["cutscene_id"] = "SECRET_CINEMATIC"
    csir["entities"][0]["name"] = "PRIVATE_CHAR"
    source["cutscene_id"] = target["cutscene_id"] = "SECRET_CINEMATIC"
    sampling = build_plan(csir, csir_sha256="ab" * 32)
    source["source"] = target["source"] = dict(sampling["source"])
    native = {"sequencer_skeletal_animation_track": True, "cine_camera_actor": True}
    knowledge = ced.retrieve_all(csir, target_capabilities=native)
    conversion = elements.prepare(csir, knowledge, native)
    report = audit.build(csir, conversion, sampling, source, target)
    body = json.dumps(report)
    assert "SECRET_CINEMATIC" not in body
    assert "PRIVATE_CHAR" not in body
    assert "AliceUnreal" not in body
    assert "Assets/timeline" not in body


def test_same_target_capture_is_not_an_independent_recheck():
    csir, conversion, sampling, source, target = _inputs()
    with pytest.raises(audit.ElementCineTwinError, match="reused"):
        audit.remeasure(csir, conversion, sampling, source, [target, copy.deepcopy(target)])


def test_true_remeasurement_can_clear_measured_actor_flags_but_not_full_fidelity():
    csir, conversion, sampling, source, target = _inputs()
    baseline = copy.deepcopy(target)
    _offset(baseline)
    _target_identity(baseline)
    _target_identity(target)
    review = audit.remeasure(csir, conversion, sampling, source, [baseline, target])
    character = next(row for row in review["per_occurrence"]
                     if row["occurrence_id"] == _item(
                         audit.build(csir, conversion, sampling, source, target),
                         "entities[0]", conversion,
                     )["occurrence_id"])
    assert character["result"] != "STOP_REPEATED_NO_MEASURED_IMPROVEMENT"
    assert character["latest_actor_position_error_cm"] == 0.0
    assert review["target_project_and_sequence_identity_claim_consistent"] is True
    assert review["full_cutscene_fidelity_verified"] is False
    assert review["further_automatic_repair_or_retry_authorized"] is False
    assert review["next_attempt_recommended"] is False
    audit.verify_remeasurement(review, csir, conversion, sampling, source, [baseline, target])


def test_missing_target_identity_never_claims_engine_verified_recovery():
    csir, conversion, sampling, source, target = _inputs()
    before = copy.deepcopy(target)
    _offset(before)
    result = audit.remeasure(csir, conversion, sampling, source, [before, target])
    assert result["target_project_and_sequence_identity_claim_consistent"] is False
    entity = result["per_occurrence"][0]
    assert entity["result"] in {
        "MEASURED_IMPROVEMENT_TARGET_PROVENANCE_INCOMPLETE",
        "REMEASUREMENT_INCOMPLETE",
    }


def test_ineffective_recheck_stops_same_attempt_and_blocks_automatic_repair():
    csir, conversion, sampling, source, target = _inputs()
    first = copy.deepcopy(target)
    second = copy.deepcopy(target)
    _offset(first, 7)
    _offset(second, 7.000001)
    result = audit.remeasure(csir, conversion, sampling, source, [first, second])
    assert result["next_attempt_recommended"] is False
    assert result["further_automatic_repair_or_retry_authorized"] is False
    assert any(row["result"] == "STOP_REPEATED_NO_MEASURED_IMPROVEMENT"
               for row in result["per_occurrence"])


def test_one_more_recheck_than_budget_fails_closed_and_rehashed_summary_rejected():
    csir, conversion, sampling, source, target = _inputs()
    captures = []
    for value in (7, 6, 5):
        row = copy.deepcopy(target)
        _offset(row, value)
        captures.append(row)
    report = audit.remeasure(csir, conversion, sampling, source, captures)
    assert report["remeasurement_attempts"] == audit.MAX_REMEASURE_ATTEMPTS
    assert report["next_attempt_recommended"] is False
    tampered = copy.deepcopy(report)
    tampered["per_occurrence"][0]["result"] = "PERFECT_FIDELITY"
    tampered.pop("remeasurement_sha256")
    tampered["remeasurement_sha256"] = elements._digest(tampered)
    with pytest.raises(audit.ElementCineTwinError, match="forged"):
        audit.verify_remeasurement(
            tampered, csir, conversion, sampling, source, captures,
        )
    captures.append(copy.deepcopy(target))
    with pytest.raises(audit.ElementCineTwinError, match="at most"):
        audit.remeasure(csir, conversion, sampling, source, captures)


def test_rechecking_a_different_unreal_project_or_sequence_refuses_audit():
    csir, conversion, sampling, source, target = _inputs()
    baseline = copy.deepcopy(target)
    _offset(baseline, 7)
    _target_identity(baseline)
    _target_identity(target)
    target["target"]["project_identity_sha256"] = "f" * 64
    with pytest.raises(audit.ElementCineTwinError, match="different"):
        audit.remeasure(csir, conversion, sampling, source, [baseline, target])


def test_no_entity_is_misclassified_as_native_repaired_when_only_rig_moves():
    csir, conversion, sampling, source, target = _inputs()
    before = copy.deepcopy(target)
    for frame in before["samples"]:
        frame["entities"][0]["world_transform"]["position_m"] = [0, 0, 0]
    report = audit.build(csir, conversion, sampling, source, before)
    character = _item(report, "entities[0]", conversion)
    assert "SOURCE_MOVES_BUT_TARGET_ACTOR_STATIC" in character["discrepancy_flags"]
    assert character["recovery_hint"] == "DIAGNOSTIC_REVIEW_ONLY"
    assert character["native_repair_authorized"] is False



def test_standalone_cinetwin_element_cli_never_overwrites_source_or_existing_report(tmp_path):
    csir, conversion, _, source, target = _inputs()
    source_path = tmp_path / "source.csir.json"
    raw_csir = json.dumps(csir, sort_keys=True).encode("utf-8")
    source_path.write_bytes(raw_csir)
    sampling = build_plan(
        csir, csir_sha256=hashlib.sha256(raw_csir).hexdigest(),
    )
    source["source"] = dict(sampling["source"])
    target["source"] = dict(sampling["source"])
    evidence = {
        "element_plan": conversion,
        "sampling_plan": sampling,
        "source_capture": source,
        "target_capture": target,
    }
    paths = {"csir": source_path}
    for key, value in evidence.items():
        path = tmp_path / (key + ".json")
        path.write_text(json.dumps(value), encoding="utf-8")
        paths[key] = path
    command = [sys.executable, str(ROOT / "tools" / "cinetwin.py"),
               "element-verify", *[
                   str(paths[key]) for key in (
                       "csir", "element_plan", "sampling_plan",
                       "source_capture", "target_capture",
                   )
               ]]
    output = tmp_path / "direct-attribution.json"
    result = subprocess.run(
        [*command, str(output)], capture_output=True,
        text=True, check=False, timeout=20,
    )
    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["native_repair_authorized"] is False
    assert report["source_occurrence_count"] == len(conversion["elements"])
    again = subprocess.run(
        [*command, str(output)], capture_output=True,
        text=True, check=False, timeout=20,
    )
    assert again.returncode == 1
    assert "File exists" in again.stderr
    unsafe = subprocess.run(
        [*command, str(source_path)], capture_output=True,
        text=True, check=False, timeout=20,
    )
    assert unsafe.returncode == 1
    assert source_path.read_bytes() == raw_csir

    # Replacing only the CSIR byte layout, without re-exporting the native
    # source capture and plan, must fail even if the JSON object is equivalent.
    source_path.write_text(json.dumps(csir, indent=2), encoding="utf-8")
    stale = subprocess.run(
        [*command, str(tmp_path / "stale-attribution.json")],
        capture_output=True, text=True, check=False, timeout=20,
    )
    assert stale.returncode == 1
    assert "identity" in stale.stderr
