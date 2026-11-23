"""Exact source-grounded Phase 10.4 synthetic end-to-end acceptance matrix.

Each gate names real test functions in the repository. Missing, renamed,
uninvoked or redirected tests are a hard failure, never a silent skip. This
describes synthetic/software coverage, NOT genuine Unity/Unreal execution.
"""
from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path
from typing import Any

SCENARIOS = (
    ("source_hash_tamper", "Source acquisition / immutable CSIR", (
        "tests/studio/test_studio_autopilot.py::test_bad_source_receipt_blocks_without_preparing_anything",
        "tests/studio/test_release_gate.py::test_source_file_mutation_after_plan_blocks_release",
    )),
    ("unity_playmode_capture_and_timeout", "Unity Play Mode CineTwin capture", (
        "tests/studio/test_studio_autopilot.py::test_source_play_mode_capture_waits_without_faking_evidence",
        "tests/studio/test_studio_autopilot.py::test_stalled_unity_play_mode_capture_times_out_without_reissuing_requests",
    )),
    ("ced_unregistered_unknown_feature", "CED unknown feature refusal", (
        "tests/studio/test_phase10_2_consolidated_audit.py::test_phase10_2_unknown_plugin_and_unregistered_action_cannot_disappear",
    )),
    ("model_provider_loss", "AI planning and pre-native recovery", (
        "tests/studio/test_studio_autopilot.py::test_model_disconnect_recovers_only_before_unreal_submission",
    )),
    ("pre_native_plan_and_approval", "Source-bound strategy validation", (
        "tests/studio/test_element_studio_workflow.py::test_changing_original_csir_or_prepared_mapping_refuses_stale_review",
        "tests/studio/test_element_studio_workflow.py::test_new_element_review_pre_native_acknowledgment_is_exact_candidate_bound",
    )),
    ("wrong_unreal_project_and_level", "Unreal identity and capability preflight", (
        "tests/studio/test_studio_local_bridge.py::test_worker_must_match_project_and_level",
        "tests/studio/test_studio_destination_preflight.py::test_wrong_target_blocks_even_if_actors_ready",
    )),
    ("unreal_native_partial_import", "Incomplete engine writes never auto-retry", (
        "tests/studio/test_studio_generation_recovery.py::test_failed_generator_records_one_attempt_and_preserves_job",
        "tests/studio/test_studio_autopilot.py::test_native_execution_cannot_be_interrupted_by_autopilot_cancel",
    )),
    ("crash_after_queue", "Crash/restart may not duplicate native execution", (
        "tests/studio/test_studio_autopilot.py::test_crash_after_unreal_job_submission_recovers_without_requeue",
        "tests/studio/test_studio_autopilot.py::test_crash_recovery_refuses_duplicate_jobs_and_conflicting_pointer",
    )),
    ("crash_before_candidate_commit", "Partial candidate preservation", (
        "tests/studio/test_studio_autopilot.py::test_restart_during_partial_candidate_preparation_refuses_second_candidate",
    )),
    ("native_reopened_process", "Separate-process native CineTwin proof gates", (
        "tests/studio/test_studio_native_acceptance.py::test_native_acceptance_requires_reopen_and_compares_the_exact_full_capture",
        "tests/studio/test_release_gate.py::test_same_session_persistence_audit_is_not_reopen_proof",
    )),
    ("limited_repair_and_untrusted_feedback", "Bounded repair consent and feedback", (
        "tests/studio/test_studio_agent_feedback.py::test_pending_native_request_blocks_a_second_correction",
        "tests/studio/test_element_studio_workflow.py::test_readback_index_forgery_and_budget_refuse_unsafe_replays",
    )),
    ("effects_without_false_parity", "Unsupported effect domains remain unresolved", (
        "tests/studio/test_phase10_2_effect_coverage.py::test_events_lossy_marker_never_reported_as_executed_signal",
    )),
    ("terminal_source_ledger", "Element 9 complete source accounting", (
        "tests/studio/test_element9_final_outcome.py::test_terminal_document_is_immutable_and_pagination_redacted",
        "tests/studio/test_element9_final_outcome.py::test_three_observations_exhaust_budget_and_never_grant_retry",
    )),
    ("heldout_fidelity_refusal", "Foreign held-out sources and native parity", (
        "tests/studio/test_phase10_2_engine_acceptance_suite.py::test_foreign_heldout_source_identity_still_refused",
        "tests/studio/test_phase10_2_engine_acceptance_suite.py::test_seven_area_complete_evidence_bundle_never_claims_engine_parity",
    )),
    ("end_to_end_native_mock", "Whole source-to-native synthetic transfer", (
        "tests/studio/test_studio_software_e2e_synthetic.py::test_synthetic_transfer_reaches_native_receipt_but_not_fidelity",
    )),
    ("job_switch_and_late_result", "Two UI variants and stale report isolation", (
        "tests/studio/test_studio_local_bridge.py::test_phase10_3_stage_diagnostics_read_only_and_invalid_active_pointer",
    )),
    ("first_run_and_distribution", "Clean workstation setup and verifiable source bundle", (
        "tests/studio/test_phase10_3_companion_and_flow.py::test_explicit_companion_wiring_is_non_overwriting_and_idempotent",
        "tests/studio/test_phase10_3_distribution.py::test_distribution_build_reproducible_and_verify_each_file",
    )),
)
JS_SCENARIOS = (
    "testSimpleOneClickFlowAndNaturalLanguageCorrections",
    "testPendingOutcomeResponseCannotPopulateDifferentRun",
    "testAdvancedJobChangeInvalidatesDiagnostics",
    "testSimpleSourceOutcomeMissingEvidenceAndExplicitRetry",
    "testSharedNineStagesAndOptInCompanionPreview",
)
JS_FILE="tests/studio/test_cinematic_ui.cjs"


class MatrixError(ValueError):
    """A required synthetic evidence scenario is missing or redirected."""


def verify(repo: Path) -> dict[str, Any]:
    root=Path(repo).resolve()
    paths={entry.split("::",1)[0] for _,_,cases in SCENARIOS for entry in cases}
    paths.add(JS_FILE)
    source={}
    python_nodes={}
    for relative in sorted(paths):
        path=root/relative
        if (path.is_symlink() or not path.is_file() or
                not path.resolve().is_relative_to(root) or path.stat().st_size>2*1024*1024):
            raise MatrixError("Required synthetic test file missing or redirected: "+relative)
        data=path.read_bytes()
        source[relative]=hashlib.sha256(data).hexdigest()
        if relative.endswith(".py"):
            try:
                module=ast.parse(data,filename=relative)
            except (SyntaxError,UnicodeDecodeError) as exc:
                raise MatrixError("Synthetic test module could not be parsed: "+relative) from exc
            python_nodes[relative]={
                node.name for node in module.body
                if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))
                and node.name.startswith("test_")
            }
    exact_nodes=[]
    matrix=[]
    for key,label,cases in SCENARIOS:
        for entry in cases:
            file,name=entry.split("::",1)
            if name not in python_nodes[file]:
                raise MatrixError("Required synthetic acceptance scenario missing: "+entry)
            if entry in exact_nodes:
                raise MatrixError("Duplicate scenario selection: "+entry)
            exact_nodes.append(entry)
        matrix.append({
            "id":key,
            "label":label,
            "coverage":"EXECUTED_PYTHON_MODULE_BY_FULL_SUITE",
            "required_test_nodes":list(cases),
            "native_engine_evidence":False,
        })
    js=(root/JS_FILE).read_text(encoding="utf-8")
    for name in JS_SCENARIOS:
        if (len(re.findall(r"\basync function "+re.escape(name)+r"\s*\(",js))!=1 or
                len(re.findall(r"\bawait "+re.escape(name)+r"\s*\(",js))!=1):
            raise MatrixError("Required JS scenario must be defined and invoked once: "+name)
    matrix.append({
        "id":"browser_ui_interruptions",
        "label":"Live mock UI routing, job switches and delayed responses",
        "coverage":"EXECUTED_NODE_SCENARIO_SCRIPT",
        "required_js_scenarios":list(JS_SCENARIOS),
        "native_engine_evidence":False,
    })
    return {
        "kind":"cutsceneai.studio.phase10_4.matrix",
        "schema_version":"1",
        "total_gates":len(matrix),
        "required_python_test_count":len(exact_nodes),
        "required_js_scenarios":len(JS_SCENARIOS),
        "gates":matrix,
        "source_sha256":source,
        "native_replay_authorized":False,
        "engine_fidelity_verified":False,
    }
