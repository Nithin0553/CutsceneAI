"""Element 5 canonical source-bound plan: coverage, provenance and no native writes."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for path in ("packages/studio", "tests/studio", "tools", "integrations/unreal"):
    sys.path.insert(0, str(ROOT / path))

import studio_element4_validation as validation
import studio_element5_plan as stage5
import studio_element_investigation as investigation
import studio_element_schedule as scheduling
import studio_element_strategy as adaptive
import studio_element_native_gate as unreal_gate
import studio_element_workflow as workflow
from test_element_adaptive_strategy import _evidence
from test_element_native_execution import _manifest
from test_element_studio_workflow import _setup, _write


def _scenario(actions=None, *, mapping=None, scene=None, caps=None):
    csir, knowledge, target, plan, schedule, strategy = _evidence(
        source=scene, caps=caps
    )
    cases = investigation.build(plan, schedule, strategy, knowledge, csir, target)
    gate = validation.build(
        plan, schedule, strategy, cases, knowledge, csir, target,
        global_strategy="native_source",
        allowed_strategies=["native_source", "source_materials"],
    )
    mapping = mapping or {
        "sequence_asset_path": "/Game/Stage/LS_Safe",
        "overwrite_sequence": False,
        "entities": {
            "PRIVATE_CAMERA": {"actor_label": "CameraUnreal"},
        },
        "assets": {
            "SECRET_MODEL": "/Game/Stage/ImportedModel",
        },
    }
    actions = actions if actions is not None else [
        {"kind": "camera_setup", "source_location": "entities[2]",
         "source_ced": "entity.camera", "actor_label": "CameraUnreal"},
        {"kind": "marker"},
    ]
    compiled = {
        "sequence_asset_path": mapping["sequence_asset_path"],
        "actions": actions,
    }
    return csir, mapping, compiled, plan, schedule, strategy, gate


def _build(values):
    return stage5.build(*values)


def test_immutable_stage5_accounts_for_every_source_occurrence_and_native_action():
    values = _scenario()
    plan = _build(values)
    assert plan["kind"] == stage5.KIND
    assert plan["source_occurrence_count"] == values[3]["source_occurrence_count"]
    assert len(plan["source_occurrences"]) == len(values[3]["elements"])
    assert plan["action_count"] == len(values[2]["actions"]) == 2
    assert plan["explicit_source_action_count"] == 1
    assert plan["legacy_unattributed_action_count"] == 1
    assert plan["blocked_action_count"] == 0
    assert plan["source_occurrences"][3]["source_kind"] == "entities"
    camera = next(row for row in plan["source_occurrences"]
                  if row["source_location"] == "entities[2]")
    # This synthetic CSIR uses only entity_id, not an exported Unity name.
    # A mapping keyed by an ID alone must not be promoted to a native actor.
    assert camera["mapping_status"] == "NO_TARGET_REFERENCE"
    assert camera["explicitly_attributed_action_ids"] == ["A00000"]
    assert camera["conversion_plan_state"] == (
        "EXPLICIT_NATIVE_SOURCE_PROVENANCE_PREPARED_UNVERIFIED"
    )
    assert plan["native_actions"][1]["source_attribution"] == (
        "LEGACY_ACTION_SOURCE_ATTRIBUTION_UNVERIFIED"
    )
    assert all(not item["target_readback_verified"] and
               not item["native_execution_verified"]
               for item in plan["native_actions"])
    assert plan["native_preflight_complete"] is False
    assert plan["native_execution_authorized"] is False
    assert plan["full_cutscene_fidelity_verified"] is False
    stage5.verify(plan, *values)


def test_unknown_source_semantics_are_preserved_as_report_only_not_covered():
    values = _scenario()
    report = _build(values)
    unknown = next(item for item in report["source_occurrences"]
                   if item["ced"] == "unknown.unclassified")
    assert unknown["conversion_plan_state"] == (
        "UNKNOWN_SEMANTIC_RETAINED_FOR_INVESTIGATION"
    )
    assert unknown["explicitly_attributed_action_ids"] == []
    assert report["source_plan_states"][unknown["conversion_plan_state"]] >= 1
    flat = json.dumps(report)
    for secret in (
        "PRIVATE_CUSTOMER_SEQUENCE", "PRIVATE_CAMERA", "PRIVATE_PROP",
        "PrivateCompany", "CLASSIFIED ACTOR", "SECRET_MODEL",
        "CameraUnreal", "/Game/Stage/LS_Safe",
    ):
        assert secret not in flat


def test_unmapped_source_reference_is_reported_without_dropping_any_occurrences():
    values = _scenario(mapping={
        "sequence_asset_path": "/Game/Stage/LS_Safe",
        "entities": {}, "assets": {},
    }, actions=[])
    report = _build(values)
    assert report["source_occurrence_count"] == len(values[3]["elements"])
    assert report["action_count"] == 0
    assert report["missing_target_reference_count"] >= 2
    assert any(x["conversion_plan_state"] == "TARGET_REFERENCE_NOT_MAPPED"
               for x in report["source_occurrences"])
    assert report["native_execution_authorized"] is False


@pytest.mark.parametrize("native_action", [
    {"kind": "execute_python"},
    {"kind": "camera_setup", "source_location": "entities[999]"},
    {"kind": "camera_setup", "source_location": "entities[2]",
     "source_ced": "PrivateCompany.SecretRig"},
    {"kind": "camera_setup", "covered_source_locations": ["entities[2]", "entities[2]"]},
])
def test_unknown_unregistered_or_foreign_native_actions_cannot_be_planned(native_action):
    values = list(_scenario())
    values[2] = {"sequence_asset_path": "/Game/Stage/LS_Safe",
                 "actions": [native_action]}
    with pytest.raises(stage5.SourceBoundPlanError):
        _build(values)


def test_explicit_wrong_source_context_remains_hard_native_blocker():
    values = list(_scenario())
    values[2] = {
        "sequence_asset_path": "/Game/Stage/LS_Safe",
        "actions": [{"kind": "audio", "source_location": "entities[2]"}],
    }
    plan = _build(values)
    assert plan["blocked_action_count"] == 1
    assert plan["native_actions"][0]["source_context_eligible"] is False
    assert plan["native_actions"][0]["source_blocker"]
    assert plan["source_occurrences"][3]["source_kind"] == "entities"


def test_recompute_rejects_rehashed_status_forgery_and_action_order_mutation():
    values = _scenario()
    baseline = _build(values)
    forged = copy.deepcopy(baseline)
    forged["source_occurrences"][0]["conversion_plan_state"] = "NATIVE_VERIFIED"
    forged.pop("source_bound_plan_sha256")
    forged["source_bound_plan_sha256"] = stage5._digest(forged)
    with pytest.raises(stage5.SourceBoundPlanError, match="modified|stale|altered"):
        stage5.verify(forged, *values)
    changed = list(copy.deepcopy(values))
    changed[2]["actions"].reverse()
    with pytest.raises(stage5.SourceBoundPlanError, match="modified|stale|altered"):
        stage5.verify(baseline, *changed)
    changed = list(copy.deepcopy(values))
    changed[1]["entities"]["PRIVATE_CAMERA"]["actor_label"] = "ModifiedTarget"
    with pytest.raises(stage5.SourceBoundPlanError):
        stage5.verify(baseline, *changed)


def test_mutated_source_and_changed_element4_gate_fail_closed():
    values = _scenario()
    old = _build(values)
    changed = list(copy.deepcopy(values))
    changed[0]["entities"][2]["name"] = "DifferentPrivateCamera"
    with pytest.raises(stage5.SourceBoundPlanError):
        stage5.verify(old, *changed)
    changed = list(copy.deepcopy(values))
    changed[6]["accepted_for_source_bound_plan"] = False
    changed[6].pop("validation_sha256")
    changed[6]["validation_sha256"] = stage5._digest(changed[6])
    with pytest.raises(stage5.SourceBoundPlanError, match="Element 4"):
        _build(changed)
    changed = list(copy.deepcopy(values))
    changed[1]["overwrite_sequence"] = True
    with pytest.raises(stage5.SourceBoundPlanError, match="overwritable"):
        _build(changed)


def test_persisted_studio_element5_review_binds_action_ledger_and_page_views(tmp_path):
    work, worker, _target = _setup(tmp_path)
    current = workflow.prepare(work, worker)
    assert current["element5_source_bound_plan"]["source_occurrence_count"] == 5
    assert current["element5_source_bound_plan"]["action_count"] == 0
    assert len(current["element5_source_bound_plan"]["source_page"]) == 5
    assert current["element5_source_bound_plan"]["native_execution_authorized"] is False
    assert current["element5_source_bound_plan"]["full_cutscene_fidelity_verified"] is False
    location = work / "candidates" / current["candidate_id"]
    stored = json.loads((location / (
        "element-workflow-" + current["workflow_sha256"] + ".json"
    )).read_text())
    assert stored["element5_source_bound_plan"]["source_bound_plan_sha256"] == (
        current["element5_source_bound_plan"]["source_bound_plan_sha256"]
    )
    assert stored["element4_baseline_validation"]["accepted_for_source_bound_plan"]
    assert workflow.current(work, worker)["element5_source_bound_plan"] == (
        current["element5_source_bound_plan"]
    )
    assert workflow.current(work, worker, offset=2)[
        "element5_source_bound_plan"]["source_page"][0]["occurrence_id"] == "E00002"


def test_real_native_worker_pre_mutation_recomputes_stage5_after_consent(tmp_path):
    work, worker, _target, summary, manifest = _manifest(tmp_path)
    current = workflow._active(work)
    assert current["element5_source_bound_plan"]["action_count"] == 1
    workflow.acknowledge(work, worker, summary["workflow_sha256"])
    approved = workflow.approve_native_actions(
        work, worker, workflow_sha256=summary["workflow_sha256"],
        inventory_sha256=summary["native_actions"]["action_inventory_sha256"],
        review_all=True, accept_legacy_unattributed=False,
    )
    candidate = json.loads((work / "active-candidate.json").read_text())
    config = json.loads((work / "connection.json").read_text())
    folder = work / "candidates" / candidate["candidate_id"]
    job = {
        "candidate_id": candidate["candidate_id"],
        "candidate_dir": str(folder),
        "csir": config["csir"],
        "mapping": candidate["mapping_copy"],
        "sequence_path": candidate["sequence_path"],
        "expected_project": config["target_project"],
        "element_native_authorization_sha256":
            approved["native_action_authorization_sha256"],
    }
    permission, checked = unreal_gate.verify_job(
        work, job, worker["scene_inventory"],
    )
    assert permission["action_count"] == 1
    assert checked == manifest
    # Re-signing a nested Element 5 record without the original source proof
    # is insufficient; engine rejects altered content before native mutation.
    pointer = folder / (
        "element-workflow-" + summary["workflow_sha256"] + ".json"
    )
    altered = json.loads(pointer.read_text())
    altered["element5_source_bound_plan"]["native_actions"][0][
        "source_attribution"] = "NATIVE_FIDELITY_PROVEN"
    altered["element5_source_bound_plan"].pop("source_bound_plan_sha256")
    altered["element5_source_bound_plan"]["source_bound_plan_sha256"] = (
        stage5._digest(altered["element5_source_bound_plan"])
    )
    altered.pop("workflow_sha256")
    altered["workflow_sha256"] = stage5._digest(altered)
    _write(pointer, altered)
    with pytest.raises(unreal_gate.NativeElementGateError, match="tampered|stale"):
        unreal_gate.verify_job(work, job, worker["scene_inventory"])
    assert all(not action["native_execution_verified"]
               for action in current["element5_source_bound_plan"]["native_actions"])



def test_deterministic_compiler_emits_exact_source_origins_not_guessing_names():
    import transfer_backend
    from test_transfer_backend import mapping, source

    src = source()
    target = mapping()
    source_before = copy.deepcopy(src)
    prepared, coverage = transfer_backend.compose(src, target)
    assert src == source_before
    assert coverage["source_track_count"] == len(src["tracks"])
    by_kind = {row["kind"]: row for row in prepared["actions"]}
    assert by_kind["camera_setup"]["source_location"] == "entities[1]"
    assert by_kind["camera_setup"]["source_ced"] == "entity.camera"
    assert by_kind["transform"]["source_location"] == "tracks[0]"
    assert by_kind["transform"]["source_ced"] == "animation.track"
    assert by_kind["camera_cut"]["source_location"] == "tracks[2]"
    assert by_kind["camera_cut"]["source_ced"] == "camera.cut"
    assert by_kind["marker"]["source_location"] == "tracks[4]"
    assert by_kind["marker"]["source_ced"] == "event.trigger"
    assert not any(row.get("source_location") == "tracks[1]"
                   for row in prepared["actions"])


def test_unregistered_legacy_action_never_acquires_a_fabricated_origin_by_name():
    values = list(_scenario())
    values[2] = {
        "sequence_asset_path": "/Game/Stage/LS_Safe",
        "actions": [{
            "kind": "camera_setup", "actor_label": "CameraUnreal",
            "entity_name": "PRIVATE_CAMERA",
        }],
    }
    report = _build(values)
    assert report["explicit_source_action_count"] == 0
    assert report["legacy_unattributed_action_count"] == 1
    assert all(not row["explicitly_attributed_action_ids"]
               for row in report["source_occurrences"])
    assert report["native_actions"][0]["source_attribution"] == (
        "LEGACY_ACTION_SOURCE_ATTRIBUTION_UNVERIFIED"
    )
