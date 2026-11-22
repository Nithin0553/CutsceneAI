"""Element 8: synthetic-only native recovery and safe bounded agent tests.

Never run Unity/Unreal in this test suite. All target readback is generated
from the existing CineTwin fixtures, recomputed by production comparators.
"""
from __future__ import annotations

import copy
import json
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
for folder in (
    "packages/studio", "packages/ced", "packages/cinetwin",
    "integrations/unreal", "tools", "tests/studio", "tests/cinetwin",
):
    path = str(ROOT / folder)
    if path not in sys.path:
        sys.path.insert(0, path)

import studio_agent_executor
import studio_agent_graph
import studio_element7_readback as element7
import studio_element8_repair as element8
import studio_generation_recovery
import studio_release_gate
from behavior_compare import compare
from test_element7_native_readback import _put, _scenario, _sha


def _target_with_offset(folder: Path, job: dict, centimeters: float,
                        *, capture_marker: str = "") -> None:
    raw = folder / "target-behavior.json"
    target = json.loads(raw.read_text(encoding="utf-8"))
    source = json.loads(Path(job["capture"]).read_text(encoding="utf-8"))
    for original, observed in zip(source["samples"], target["samples"]):
        expected_character = next(x for x in original["entities"]
                                  if x["entity_id"] == "character")
        character = next(x for x in observed["entities"]
                         if x["entity_id"] == "character")
        character["world_transform"]["position_m"][0] = (
            expected_character["world_transform"]["position_m"][0]
            + centimeters / 100
        )
    target["provenance"] = {"capture_marker": capture_marker}
    _put(raw, target)
    sampling = json.loads((folder / "sampling-plan.json").read_text(
        encoding="utf-8"
    ))
    new_comparison = compare(sampling, source, target)
    saved = folder / "comparison.json"
    comparison = json.loads(saved.read_text(encoding="utf-8"))
    comparison.update(new_comparison)
    comparison["target_observation_sha256"] = _sha(raw)
    comparison["acceptance_status"] = (
        "DIFFERENCES_DETECTED" if new_comparison["evaluation"]["status"]
        == "DIFFERENCES_DETECTED" else "INCOMPLETE_MEASURED_SCOPE"
    )
    _put(saved, comparison)
    _put(folder / "element7-readback.json",
         element7.build(folder.parents[2], job["job_id"], folder))


def _second(folder: Path, suffix: str) -> Path:
    other = folder.with_name("native-acceptance-" + suffix)
    other.mkdir()
    for file in folder.glob("*.json"):
        if file.name != "element7-readback.json":
            shutil.copyfile(file, other / file.name)
    return other


def _character(review: dict) -> dict:
    return next(x for x in review["per_occurrence"]
                if x["source_kind"] == "entities"
                and x["latest_status"] == "DIRECT_MEASURED_DIFFERENCE")


def test_element8_cleared_measured_scope_does_not_prove_cinematic_fidelity(tmp_path):
    work, job, native = _scenario(
        tmp_path, with_element3=True, complete=True,
    )
    record = element8.build(work, job["job_id"], [native])
    assert record["status"] == (
        "MEASURED_DOMAINS_CLEAR_OTHER_FIDELITY_UNVERIFIED"
    )
    assert record["remeasurement_attempts"] == 0
    assert record["remaining_manual_observation_budget"] == 2
    assert record["native_repair_adapter_available_for_review"] is False
    assert record["manual_remeasurement_possible"] is False
    assert not record["native_repair_authorized"]
    assert not record["automatic_native_retry_authorized"]
    assert not record["full_cutscene_fidelity_verified"]
    assert "audio_output" in record["unverified_domains"]
    assert "Alice" not in json.dumps(record)
    assert "NativeTest.uproject" not in json.dumps(record)
    element8.verify(record, work, job["job_id"], [native])


def test_element8_only_proposes_existing_user_scoped_offset_adapter(tmp_path):
    work, job, native = _scenario(tmp_path, with_element3=True)
    _target_with_offset(native, job, 7.0, capture_marker="baseline")
    review = element8.build(work, job["job_id"], [native])
    person = _character(review)
    assert person["advisory_strategy"] == (
        "INSPECT_EXISTING_USER_AUTHORIZED_CHARACTER_OFFSET_POLICY"
    )
    assert person["measured_actor_position_error_cm"] == pytest.approx(7.0)
    assert review["native_repair_adapter_available_for_review"] is True
    assert element8.may_review_exact_character_offset(
        work, job["job_id"], [native], "Alice",
    ) is True
    assert element8.may_review_exact_character_offset(
        work, job["job_id"], [native], "Camera",
    ) is False
    assert element8.may_review_exact_character_offset(
        work, job["job_id"], [native], "Other",
    ) is False
    assert review["manual_remeasurement_possible"] is True
    assert review["status"] == (
        "INVESTIGATE_APPROVED_NARROW_ADAPTER_OR_REPORT_LIMITATION"
    )
    choice = element8.select_advisory(
        review, person["occurrence_id"], person["advisory_strategy"],
    )
    assert choice["native_repair_authorized"] is False
    assert choice["native_execution_requested"] is False
    assert "AliceUnreal" not in json.dumps(review)
    assert "/Game/Acceptance/" not in json.dumps(review)


def test_model_cannot_override_repair_target_method_or_edit_permission(tmp_path):
    work, job, native = _scenario(tmp_path, with_element3=True)
    _target_with_offset(native, job, 7.0)
    original = element8.build(work, job["job_id"], [native])
    character = _character(original)
    for selected, strategy in (
        ("E99999", character["advisory_strategy"]),
        (character["occurrence_id"], "set_actor_location"),
        (character["occurrence_id"], "INSPECT_NATIVE_CAMERA_LENS"),
    ):
        with pytest.raises(element8.BoundedRepairError):
            element8.select_advisory(original, selected, strategy)
    forged = copy.deepcopy(original)
    forged["native_repair_authorized"] = True
    forged["repair_plan_sha256"] = element8._hash({
        k: v for k, v in forged.items() if k != "repair_plan_sha256"
    })
    with pytest.raises(element8.BoundedRepairError):
        element8.select_advisory(
            forged, character["occurrence_id"],
            character["advisory_strategy"],
        )
    with pytest.raises(element8.BoundedRepairError):
        element8.verify(forged, work, job["job_id"], [native])


def test_missing_source_mapping_remains_investigation_not_arbitrary_edit(tmp_path):
    work, job, native = _scenario(tmp_path, with_element3=True)
    review = element8.build(work, job["job_id"], [native])
    unresolved = [row for row in review["per_occurrence"]
                  if row["latest_status"] == "INCOMPLETE_TARGET_UNMAPPED"]
    assert len(unresolved) == 1
    assert unresolved[0]["advisory_strategy"] == "INVESTIGATE_TARGET_MAPPING"
    assert not review["native_repair_adapter_available_for_review"]
    assert review["domain_findings"][0]["advisory_strategy"] == (
        "INSPECT_NATIVE_CAMERA_LENS"
    )
    assert review["domain_findings"][0]["source_track_causality_verified"] is False
    assert all(row["native_edit_authorized"] is False
               for row in review["per_occurrence"])


def test_improved_native_remeasurement_is_measured_not_authorized(tmp_path):
    work, job, native = _scenario(tmp_path, with_element3=True)
    _target_with_offset(native, job, 7.0, capture_marker="first")
    second = _second(native, "second")
    _target_with_offset(second, job, 4.0, capture_marker="later")
    review = element8.build(work, job["job_id"], [native, second])
    person = _character(review)
    assert person["measured_actor_position_error_cm"] == pytest.approx(4.0)
    assert person["remeasurement_result"] == (
        "PARTIAL_OR_DIFFERENT_MEASURED_DISCREPANCY_REMAINS"
    )
    assert review["remeasurement_attempts"] == 1
    assert review["remaining_manual_observation_budget"] == 1
    assert review["manual_remeasurement_possible"] is True
    assert review["native_repair_authorized"] is False
    element8.verify(review, work, job["job_id"], [native, second])


def test_repeated_no_progress_stops_and_removes_repair_suggestion(tmp_path):
    work, job, native = _scenario(tmp_path, with_element3=True)
    _target_with_offset(native, job, 7.0, capture_marker="first")
    second = _second(native, "second")
    _target_with_offset(second, job, 7.0, capture_marker="different-observation")
    review = element8.build(work, job["job_id"], [native, second])
    assert review["status"] == "STOP_MEASURED_REGRESSION_OR_NO_PROGRESS"
    assert _character(review)["advisory_strategy"] == "REPORT_LIMITATION"
    assert review["manual_remeasurement_possible"] is False
    assert review["native_repair_adapter_available_for_review"] is False


def test_two_independent_native_remeasurements_exhaust_budget(tmp_path):
    work, job, native = _scenario(tmp_path, with_element3=True)
    _target_with_offset(native, job, 7.0, capture_marker="first")
    second = _second(native, "second")
    _target_with_offset(second, job, 4.0, capture_marker="second")
    third = _second(native, "third")
    _target_with_offset(third, job, 3.0, capture_marker="third")
    review = element8.build(work, job["job_id"], [native, second, third])
    assert review["remeasurement_attempts"] == 2
    assert review["status"] == "STOP_REMEASUREMENT_BUDGET_EXHAUSTED"
    assert not review["manual_remeasurement_possible"]
    assert review["remaining_manual_observation_budget"] == 0
    with pytest.raises(element8.BoundedRepairError, match="at most two"):
        element8.build(
            work, job["job_id"], [native, second, third, third],
        )


def test_repeated_identical_target_capture_cannot_count_as_new_observation(tmp_path):
    work, job, native = _scenario(tmp_path, with_element3=True)
    second = _second(native, "second")
    with pytest.raises(element8.BoundedRepairError, match="Duplicate"):
        element8.build(work, job["job_id"], [native, second])


def test_missing_source_occurrence_contract_only_allows_report_only(tmp_path):
    work, job, native = _scenario(tmp_path, with_element3=False)
    review = element8.build(work, job["job_id"], [native])
    assert review["status"] == "REPORT_ONLY_NO_EXACT_SOURCE_OCCURRENCE_PLAN"
    assert review["source_occurrence_count"] is None
    assert review["per_occurrence"] == []
    assert not review["native_repair_adapter_available_for_review"]


def test_legacy_or_unfinished_element6_attempt_cannot_enter_repair_loop(tmp_path):
    work, job, native = _scenario(
        tmp_path, with_element3=True, attempt=False,
    )
    with pytest.raises(element8.BoundedRepairError, match="completed builder"):
        element8.build(work, job["job_id"], [native])


def test_saved_repair_plan_is_immutable_and_raw_evidence_is_reverified(tmp_path):
    work, job, native = _scenario(tmp_path, with_element3=True)
    _target_with_offset(native, job, 7)
    file, record = element8.save_once(work, job["job_id"], [native])
    assert file.is_file()
    assert file.name == (
        "element8-repair-plan-" + record["repair_plan_sha256"] + ".json"
    )
    again, report = element8.save_once(work, job["job_id"], [native])
    assert again == file and report == record
    forged = dict(record, native_repair_authorized=True)
    _put(file, forged)
    with pytest.raises(element8.BoundedRepairError):
        element8.save_once(work, job["job_id"], [native])


def test_changed_native_observation_invalidates_saved_element8(tmp_path):
    work, job, native = _scenario(tmp_path, with_element3=True)
    file, report = element8.save_once(work, job["job_id"], [native])
    assert file.exists()
    target = native / "target-behavior.json"
    target.write_bytes(target.read_bytes() + b"\n")
    with pytest.raises(element8.BoundedRepairError):
        element8.verify(report, work, job["job_id"], [native])


def test_release_readiness_exposes_element8_safety_without_promoting_fidelity(tmp_path):
    work, job, native = _scenario(
        tmp_path, with_element3=True, complete=True,
    )
    _put(native / "element7-readback.json",
         element7.build(work, job["job_id"], native))
    readiness = studio_release_gate.assess(work, job["job_id"])
    check = readiness["checks"]["element8_bounded_repair_triage"]
    assert check["status"] == "PASS"
    assert check["diagnostic_status"] == (
        "MEASURED_DOMAINS_CLEAR_OTHER_FIDELITY_UNVERIFIED"
    )
    assert check["native_repair_authorized"] is False
    assert check["automatic_native_retry_authorized"] is False
    assert not readiness["release_ready"]
    assert not readiness["fidelity_verified"]


def test_existing_agent_graph_inherits_exact_element8_native_stop_policy(tmp_path):
    work, job, native = _scenario(tmp_path, with_element3=True)
    _target_with_offset(native, job, 7.0)
    view = studio_agent_graph._element8_review(
        work, native.parent, job,
    )
    assert view["native_character_offset_review_available"]
    assert view["native_repair_authorized"] is False
    assert view["automatic_native_retry_authorized"] is False
    assert view["per_occurrence_advisory"]
    assert "Alice" not in json.dumps(view)


def test_unreal_agent_refuses_offset_that_element8_cannot_recommend(tmp_path):
    work, job, native = _scenario(
        tmp_path, with_element3=True,
        ai_agents_enabled=True, automatic_setup=True,
    )
    request = {
        "kind": "cutsceneai.studio.agent_repair_request",
        "schema_version": "1", "job_id": job["job_id"],
        "candidate_id": job["candidate_id"],
        "strategy": "restore_constant_actor_offset",
        "sequence_path": job["sequence_path"],
        "expected_project": job["expected_project"],
        "expected_level": job["expected_level"],
    }
    api = SimpleNamespace(EditorAssetLibrary=SimpleNamespace(
        does_asset_exist=lambda *_: True,
    ))
    _put(native / "element7-readback.json",
         element7.build(work, job["job_id"], native))
    with pytest.raises(ValueError, match="Element 8 measured discrepancy"):
        studio_agent_executor.execute(
            api, work, job, request,
            project=job["expected_project"],
            level=job["expected_level"],
        )


def test_legacy_generation_recovery_cannot_bypass_once_claimed_element6_job(tmp_path):
    work, job, native = _scenario(tmp_path, with_element3=True)
    assert (native.parent / ("element6-native-claim-"
                              + job["job_id"] + ".json")).is_file()
    with pytest.raises(
        studio_generation_recovery.GenerationRecoveryError,
        match="already claimed",
    ):
        studio_generation_recovery.recover_latest(
            work, unreal_api=SimpleNamespace(),
        )


def test_unreal_planner_refreshes_canonical_element8_in_open_editor():
    from studio_planner_sync import MODULES

    index = [name for name, _ in MODULES]
    assert index.index("studio_element7_readback") < index.index(
        "studio_element8_repair"
    ) < index.index("studio_agent_executor")
