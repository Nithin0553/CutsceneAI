"""Element 9 source-complete terminal outcome — synthetic software fixtures only.

No Unity/Unreal editor is invoked. Real native equivalence, rendered, audio,
event and physical fidelity remain explicitly unverified in every case.
"""
from __future__ import annotations

import copy
import json
import shutil
import sys
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for location in ("packages/studio", "packages/ced", "packages/cinetwin",
                 "integrations/unreal", "tools", "tests/studio"):
    p = str(ROOT / location)
    if p not in sys.path:
        sys.path.insert(0, p)

import studio_element7_readback as element7
import studio_element9_outcome as outcome
import studio_release_gate as release_gate
from test_element7_native_readback import _put, _scenario
from test_element8_bounded_repair import _second, _target_with_offset
from test_studio_local_bridge import bridge, call


def _ready(tmp_path, *, complete=False, workflow=True):
    work, job, folder = _scenario(
        tmp_path, with_element3=workflow, complete=complete,
    )
    _put(folder / "element7-readback.json", element7.build(
        work, job["job_id"], folder,
    ))
    return work, job, folder


def test_before_engine_acceptance_all_source_occurrences_are_pending(tmp_path):
    work, job, folder = _ready(tmp_path, workflow=True)
    shutil.rmtree(folder)
    result = outcome.build(work, job["job_id"])
    assert result["status"] == (
        "NATIVE_ACCEPTANCE_PENDING_ALL_SOURCE_OCCURRENCES_UNVERIFIED"
    )
    assert result["source_occurrence_count"] > 3
    assert len(result["source_occurrences"]) == result["source_occurrence_count"]
    assert result["native_observation_count"] == 0
    assert result["remaining_manual_remeasurement_budget"] == 2
    assert result["element8_repair_plan_sha256"] is None
    assert result["release_ready"] is False
    assert result["full_cutscene_fidelity_verified"] is False
    assert not result["automatic_native_retry_authorized"]
    assert not result["native_repair_authorized"]
    assert all(
        "MEASURED" not in row["outcome"]
        or row["outcome"] in ("UNKNOWN_SEMANTIC_NOT_MEASURED",)
        for row in result["source_occurrences"]
    )
    assert "rendered_frame_parity" in {
        domain["domain"] for domain in result["measured_and_unverified_domains"]
    }
    assert result["source_outcome_counts"]
    assert "NativeTest.uproject" not in json.dumps(result)
    assert "AliceUnreal" not in json.dumps(result)
    outcome.verify(result, work, job["job_id"])


def test_pending_source_report_can_work_without_element3_model_review(tmp_path):
    work, job, folder = _ready(tmp_path, workflow=False)
    shutil.rmtree(folder)
    result = outcome.build(work, job["job_id"])
    assert result["source_workflow_sha256"] is None
    assert result["source_occurrence_count"] > 0
    assert all(row["source_plan_status"] == "NO_ELEMENT5_SOURCE_BOUND_PLAN"
               for row in result["source_occurrences"])
    assert all(row["explicit_native_source_action_count"] == 0
               for row in result["source_occurrences"])


def test_passed_measured_scope_remains_full_fidelity_unverified(tmp_path):
    work, job, _native = _ready(tmp_path, complete=True)
    report = outcome.build(work, job["job_id"])
    assert report["status"] == (
        "MEASURED_SCOPE_WITHIN_TOLERANCE_FULL_FIDELITY_UNVERIFIED"
    )
    assert report["native_observation_count"] == 1
    assert report["bounded_remeasurement_attempt_count"] == 0
    assert report["native_builder_receipt_consistent_with_saved_evidence"] is True
    assert report["measured_improvement_is_not_repair_causality"] is True
    assert report["independent_engine_attestation_verified"] is False
    assert report["source_occurrence_count"] == len(report["source_occurrences"])
    assert any(row["outcome"] == "MEASURED_SCOPE_NO_FLAGGED_DIFFERENCE"
               for row in report["source_occurrences"])
    assert all(not row["native_equivalence_proven"]
               for row in report["source_occurrences"])
    assert all(not x["full_fidelity_verified"]
               for x in report["measured_and_unverified_domains"])
    assert "audio_and_event_behavior" in {
        row["domain"] for row in report["measured_and_unverified_domains"]
    }
    assert not report["release_ready"]
    outcome.verify(report, work, job["job_id"])


def test_pending_target_mapping_is_not_silently_converted(tmp_path):
    work, job, _native = _ready(tmp_path, complete=False)
    report = outcome.build(work, job["job_id"])
    assert report["status"] == "NATIVE_MEASUREMENT_GAPS_REMAIN_LIMITATIONS_RECORDED"
    assert any(row["outcome"] == "TARGET_MAPPING_NOT_VERIFIED"
               for row in report["source_occurrences"])
    assert report["source_outcome_counts"]["TARGET_MAPPING_NOT_VERIFIED"] >= 1
    assert all(row["full_cinematic_fidelity_proven"] is False
               for row in report["source_occurrences"])


def test_remaining_seven_cm_difference_reported_not_auto_repaired(tmp_path):
    work, job, native = _scenario(tmp_path, with_element3=True)
    _target_with_offset(native, job, 7, capture_marker="baseline")
    report = outcome.build(work, job["job_id"])
    assert report["status"] == "MEASURED_DIFFERENCES_REMAIN_LIMITATIONS_RECORDED"
    assert any(row["outcome"] == "MEASURED_DIFFERENCE_REMAINS"
               for row in report["source_occurrences"])
    assert report["next_step"] == "REVIEW_SUPPORTED_REPAIR_OR_REPORT_LIMITATION"
    assert report["native_repair_authorized"] is False
    assert report["automatic_native_retry_authorized"] is False


def test_seven_to_four_cm_is_progress_without_causal_repair_claim(tmp_path):
    work, job, native = _scenario(tmp_path, with_element3=True)
    _target_with_offset(native, job, 7, capture_marker="first")
    second = _second(native, "second")
    _target_with_offset(second, job, 4, capture_marker="second")
    report = outcome.build(work, job["job_id"], [native, second])
    assert report["native_observation_count"] == 2
    assert report["remaining_manual_remeasurement_budget"] == 1
    assert report["bounded_remeasurement_attempt_count"] == 1
    assert report["measured_improvement_is_not_repair_causality"] is True
    assert any(row["measurement_progress"]
               == "PARTIAL_OR_DIFFERENT_MEASURED_DISCREPANCY_REMAINS"
               for row in report["source_occurrences"])
    assert report["status"] == "MEASURED_DIFFERENCES_REMAIN_LIMITATIONS_RECORDED"


def test_repeated_same_error_forces_limitations_stop(tmp_path):
    work, job, native = _scenario(tmp_path, with_element3=True)
    _target_with_offset(native, job, 7, capture_marker="first")
    second = _second(native, "second")
    _target_with_offset(second, job, 7, capture_marker="new-observation-same-error")
    report = outcome.build(work, job["job_id"], [native, second])
    assert report["status"] == (
        "STOP_REPAIR_NO_MEASURED_IMPROVEMENT_REPORT_LIMITATIONS"
    )
    assert report["stop_reason"] == "STOP_MEASURED_REGRESSION_OR_NO_PROGRESS"
    assert any(row["next_step"] == "STOP_BOUNDED_REPAIR_REPORT_LIMITATION"
               for row in report["source_occurrences"])
    assert report["manual_review_required"] is True
    assert not report["automatic_native_retry_authorized"]


def test_three_observations_exhaust_budget_and_never_grant_retry(tmp_path):
    work, job, native = _scenario(tmp_path, with_element3=True)
    _target_with_offset(native, job, 7, capture_marker="first")
    second = _second(native, "second")
    _target_with_offset(second, job, 4, capture_marker="second")
    third = _second(native, "third")
    _target_with_offset(third, job, 3, capture_marker="third")
    report = outcome.build(work, job["job_id"], [native, second, third])
    assert report["status"] == "STOP_REMEASUREMENT_BUDGET_REPORT_LIMITATIONS"
    assert report["remaining_manual_remeasurement_budget"] == 0
    assert report["stop_reason"] == "STOP_REMEASUREMENT_BUDGET_EXHAUSTED"
    with pytest.raises(outcome.OutcomeError, match="Duplicate|excessive"):
        outcome.build(work, job["job_id"], [native, second, third, native])


def test_tampered_canonical_report_and_source_evidence_are_rejected(tmp_path):
    work, job, _folder = _ready(tmp_path)
    good = outcome.build(work, job["job_id"])
    forged = copy.deepcopy(good)
    forged["release_ready"] = True
    forged["full_cutscene_fidelity_verified"] = True
    forged.pop("outcome_sha256")
    forged["outcome_sha256"] = outcome._hash(forged)
    with pytest.raises(outcome.OutcomeError, match="altered"):
        outcome.verify(forged, work, job["job_id"])
    source = Path(job["csir"])
    source.write_bytes(source.read_bytes() + b"\n")
    with pytest.raises(outcome.OutcomeError):
        outcome.build(work, job["job_id"])


def test_incomplete_native_acceptance_directory_is_not_ignored(tmp_path):
    work, job, folder = _ready(tmp_path)
    (folder / "element7-readback.json").unlink()
    with pytest.raises(outcome.OutcomeError, match="independently verified Element 7"):
        outcome.discover(work, job["job_id"])
    with pytest.raises(outcome.OutcomeError):
        outcome.build(work, job["job_id"])


def test_synthetic_evidence_legacy_attempt_cannot_be_marked_verified(tmp_path):
    work, job, folder = _scenario(
        tmp_path, with_element3=True, attempt=False,
    )
    _put(folder / "element7-readback.json", element7.build(
        work, job["job_id"], folder,
    ))
    with pytest.raises(outcome.OutcomeError, match="bounded repair evidence is invalid"):
        outcome.build(work, job["job_id"])


def test_terminal_document_is_immutable_and_pagination_redacted(tmp_path):
    work, job, _native = _ready(tmp_path)
    path, report = outcome.save_once(work, job["job_id"])
    assert path.is_file()
    assert path.name == "element9-outcome-" + report["outcome_sha256"] + ".json"
    again, same = outcome.save_once(work, job["job_id"])
    assert again == path and same == report
    paged = outcome.page(report, 2)
    assert paged["source_page"][0]["occurrence_id"] == "E00002"
    assert len(paged["source_page"]) <= outcome.PAGE_SIZE
    assert "source_occurrences" not in paged
    assert paged["outcome_sha256"] == report["outcome_sha256"]
    with pytest.raises(outcome.OutcomeError):
        outcome.page(report, -1)
    with pytest.raises(outcome.OutcomeError):
        outcome.page(report, 30001)
    tampered = copy.deepcopy(report)
    tampered["source_occurrences"][0]["outcome"] = "FULL_FIDELITY_VERIFIED"
    _put(path, tampered)
    with pytest.raises(outcome.OutcomeError):
        outcome.save_once(work, job["job_id"])


def test_release_readiness_accounts_for_each_source_and_never_promotes_fidelity(tmp_path):
    work, job, _native = _ready(tmp_path, complete=True)
    readiness = release_gate.assess(work, job["job_id"])
    check = readiness["checks"]["element9_final_outcome_accounting"]
    assert check["status"] == "PASS"
    assert check["source_occurrence_count"] == outcome.build(
        work, job["job_id"]
    )["source_occurrence_count"]
    assert check["automatic_native_retry_authorized"] is False
    assert check["full_cutscene_fidelity_verified"] is False
    assert readiness["release_ready"] is False
    assert readiness["fidelity_verified"] is False


def test_studio_http_api_returns_page_and_pending_limitations_without_mutation(tmp_path):
    work, _job, folder = _ready(tmp_path, complete=True)
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("test", encoding="utf-8")
    server = ThreadingHTTPServer(
        ("127.0.0.1", 0), bridge.create_handler(web, work),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        assert call(url + "/api/final-outcome?offset=-1")[0] == 409
        status, data = call(url + "/api/final-outcome?offset=1")
        assert status == 200
        assert data["available"] is True
        assert data["source_page"][0]["occurrence_id"] == "E00001"
        assert data["full_cutscene_fidelity_verified"] is False
        assert not data["automatic_native_retry_authorized"]
        assert call(url + "/api/final-outcome?bogus=1")[0] == 409
        assert call(url + "/api/final-outcome?offset=999999")[0] == 409
        assert not list(folder.parent.glob("element9-outcome-*.json"))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
