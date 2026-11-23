"""Element 3.3: evidence-ranked, source-routed and strictly advisory strategies."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
for name in ("studio", "ced"):
    sys.path.insert(0, str(ROOT / "packages" / name))

import ced_agent_knowledge as ced
import studio_element_plan as plans
import studio_element_schedule as schedules
import studio_element_strategy as adaptive


def _time(value: int) -> dict:
    return {"value": value, "rate": {"numerator": 24, "denominator": 1}}


def _scene() -> dict:
    return {
        "cutscene_id": "PRIVATE_CUSTOMER_SEQUENCE",
        "source": {"engine": "unity", "engine_version": "6000.3"},
        "assets": [{"asset_id": "SECRET_MODEL", "ced_type": "asset.model"}],
        "entities": [
            {"entity_id": "PRIVATE_ACTOR", "ced_type": "entity.character",
             "asset_id": "SECRET_MODEL", "name": "CLASSIFIED ACTOR"},
            {"entity_id": "PRIVATE_PROP", "ced_type": "entity.prop"},
            {"entity_id": "PRIVATE_CAMERA", "ced_type": "entity.camera"},
            {"entity_id": "PRIVATE_VENDOR", "ced_type": "PrivateCompany.SecretRig"},
        ],
        "tracks": [
            {"track_id": "ANIMATION_OF_ACTOR", "ced_type": "animation.track",
             "binding_entity_id": "PRIVATE_ACTOR", "sections": [{
                 "section_id": "CHARACTER_CLIP", "ced_type": "animation.section",
                 "start": _time(0), "end": _time(24), "payload": {},
             }]},
            {"track_id": "ANIMATION_OF_PROP", "ced_type": "animation.track",
             "binding_entity_id": "PRIVATE_PROP", "sections": [{
                 "section_id": "PROP_CLIP", "ced_type": "animation.section",
                 "start": _time(0), "end": _time(24), "payload": {},
             }]},
            {"track_id": "CAMERA_TRACK", "ced_type": "camera.transform",
             "binding_entity_id": "PRIVATE_CAMERA", "sections": [{
                 "section_id": "CAMERA_CLIP", "ced_type": "camera.fov",
                 "start": _time(0), "end": _time(24), "payload": {},
             }]},
        ],
    }


def _evidence(source=None, *, caps=None):
    scene = source if source is not None else _scene()
    native = caps if caps is not None else {
        "sequencer_skeletal_animation_track": True,
        "cine_camera_actor": True,
        "sequencer_visibility_track": True,
        "fbx_asset_import": True,
    }
    knowledge = ced.retrieve_all(
        scene, target_capabilities=native,
        source_version="6000.3", target_version="5.8",
    )
    plan = plans.prepare(scene, knowledge, native)
    schedule = schedules.build(plan, scene)
    comparison = adaptive.build(plan, schedule, knowledge, scene, native)
    return scene, knowledge, native, plan, schedule, comparison


def _row(comparison, location, plan):
    ident = next(item["occurrence_id"] for item in plan["elements"]
                 if item["source_location"] == location)
    return next(item for item in comparison["comparisons"]
                if item["occurrence_id"] == ident)


def _alternatives(item):
    return {alt["action"]: alt for alt in item["alternatives"]}


def test_native_source_branch_disambiguates_character_vs_prop_without_native_execution():
    scene, knowledge, caps, plan, schedule, comparison = _evidence()
    actor = _row(comparison, "tracks[0]", plan)
    prop = _row(comparison, "tracks[1]", plan)
    actor_options, prop_options = _alternatives(actor), _alternatives(prop)
    assert actor_options["skeletal_animation"]["eligible_for_model_proposal"] is True
    assert actor_options["transform"]["eligible_for_model_proposal"] is False
    assert prop_options["transform"]["eligible_for_model_proposal"] is True
    assert prop_options["skeletal_animation"]["eligible_for_model_proposal"] is False
    assert actor["suggested_action"] == "skeletal_animation"
    assert prop["suggested_action"] == "transform"
    assert actor["selected_action"] == "report_only"
    assert comparison["native_execution_authorized"] is False
    assert comparison["full_cutscene_fidelity_verified"] is False
    assert all(not row["native_execution_authorized"] for row in comparison["comparisons"])
    assert all(not alt["current_cutscene_fidelity_verified"]
               for row in comparison["comparisons"] for alt in row["alternatives"])
    assert "MATCHES_INSTALLED_NATIVE_TRACK_ROUTE" in actor_options[
        "skeletal_animation"]["signals"]
    assert "INSTALLED_NATIVE_SOURCE_BRANCH_MISMATCH" in actor_options["transform"]["signals"]
    adaptive.verify(comparison, plan, schedule, knowledge, scene, caps)


def test_section_inherits_parent_track_routing_and_unknown_vendor_is_private():
    _, _, _, plan, _, comparison = _evidence()
    actor_section = _row(comparison, "tracks[0].sections[0]", plan)
    prop_section = _row(comparison, "tracks[1].sections[0]", plan)
    assert _alternatives(actor_section)["transform"]["eligible_for_model_proposal"] is False
    assert _alternatives(prop_section)["skeletal_animation"][
        "eligible_for_model_proposal"] is False
    unknown = _row(comparison, "entities[3]", plan)
    assert unknown["ced"] == "unknown.unclassified"
    assert unknown["alternatives"] == []
    hints = adaptive.proposal_hints(comparison)
    serialized = json.dumps(hints) + json.dumps(comparison)
    for forbidden in ("PRIVATE_", "CLASSIFIED", "PrivateCompany",
                      "SECRET_MODEL", "ANIMATION_OF_ACTOR", "CAMERA_TRACK"):
        assert forbidden not in serialized


def test_missing_native_capability_never_becomes_positive_adaptive_evidence():
    scene = _scene()
    _, knowledge, caps, plan, schedule, comparison = _evidence(
        scene, caps={"cine_camera_actor": True})
    actor = _row(comparison, "tracks[0]", plan)
    skeleton = _alternatives(actor)["skeletal_animation"]
    assert "TARGET_CAPABILITY_NOT_OBSERVED" in skeleton["signals"]
    assert skeleton["eligible_for_model_proposal"] is False
    assert actor["suggested_action"] == "report_only"
    adaptive.verify(comparison, plan, schedule, knowledge, scene, caps)


def test_ambiguous_non_routed_alternatives_remain_advisory():
    source = {"entities": [
        {"entity_id": "A", "ced_type": "metadata.property_descriptor"},
    ]}
    _, _, _, _, _, comparison = _evidence(source)
    item = comparison["comparisons"][0]
    assert item["suggested_action"] == "report_only"
    assert item["suggestion_reason"] == "UNDISTINGUISHED_CED_ALTERNATIVES"
    assert {a["action"] for a in item["alternatives"]} == {
        "property_float", "property_bool"
    }
    assert all(a["native_preflight_required"] for a in item["alternatives"])


def test_scheduler_conflict_propagates_to_adaptive_action_eligibility():
    scene = _scene()
    scene["tracks"][1]["binding_entity_id"] = "PRIVATE_ACTOR"
    _, _, _, plan, _, comparison = _evidence(scene)
    actor = _row(comparison, "tracks[0]", plan)
    assert actor["source_schedule_status"] == "OWNERSHIP_CONFLICT"
    assert actor["suggested_action"] == "report_only"
    assert all(not a["eligible_for_model_proposal"] for a in actor["alternatives"])
    assert adaptive.proposal_hints(comparison)[actor["occurrence_id"]]["alternatives"] == []


def test_full_model_review_rejects_source_native_branch_mismatch_and_no_checkpoint(tmp_path):
    _, _, _, plan, _, comparison = _evidence()
    actor_id = _row(comparison, "tracks[0]", plan)["occurrence_id"]
    hints = adaptive.proposal_hints(comparison)
    class MaliciousModel:
        def complete_json(self, **kwargs):
            choices = [{"occurrence_id": item["occurrence_id"],
                        "action": "transform" if item["occurrence_id"] == actor_id
                        else (item["candidate_actions"][0]
                              if item["candidate_actions"] else "report_only")}
                       for item in kwargs["payload"]["elements"]]
            return SimpleNamespace(answer={"choices": choices}, response_sha256="f" * 64)

    checkpoint = tmp_path / "adaptive.json"
    with pytest.raises(plans.ElementPlanError, match="excluded"):
        plans.review_with_model(
            plan, provider=MaliciousModel(), checkpoint_path=checkpoint,
            model_identity="test/model", strategy_hints=hints,
        )
    assert not checkpoint.exists()


def test_model_receives_complete_ranked_options_and_can_choose_safe_report_only():
    scene, knowledge, caps, plan, _, comparison = _evidence()
    hints = adaptive.proposal_hints(comparison)
    calls = []
    class Model:
        def complete_json(self, **kwargs):
            payload = kwargs["payload"]
            calls.append(payload)
            return SimpleNamespace(answer={"choices": [
                {"occurrence_id": item["occurrence_id"],
                 "action": item["adaptive_evidence"]["suggested_action"]}
                for item in payload["elements"]
            ]}, response_sha256="e" * 64)
    reviewed, hashes = plans.review_with_model(
        plan, provider=Model(), strategy_hints=hints,
    )
    assert hashes
    assert reviewed["model_reviewed_count"] == len(plan["elements"])
    for call in calls:
        body = json.dumps(call)
        assert "PrivateCompany" not in body
        assert "PRIVATE_CUSTOMER_SEQUENCE" not in body
        for item in call["elements"]:
            assert item["adaptive_evidence"] is not None
            assert item["candidate_actions"] == [
                option["action"] for option in item["adaptive_evidence"]["alternatives"]
            ]
    plans.verify(reviewed, scene, knowledge, caps)
    chosen_schedule = schedules.build(reviewed, scene)
    chosen_comparison = adaptive.build(
        reviewed, chosen_schedule, knowledge, scene, caps,
    )
    adaptive.verify(chosen_comparison, reviewed, chosen_schedule, knowledge, scene, caps)


def test_independently_recomputed_strategy_rejects_forged_ranking_and_old_source():
    scene, knowledge, caps, plan, schedule, comparison = _evidence()
    tampered = copy.deepcopy(comparison)
    tampered["comparisons"][0]["native_execution_authorized"] = True
    tampered.pop("comparison_sha256")
    tampered["comparison_sha256"] = plans._digest(tampered)
    with pytest.raises(adaptive.AdaptiveStrategyError, match="tampered"):
        adaptive.verify(tampered, plan, schedule, knowledge, scene, caps)
    scene["entities"][0]["name"] = "REPLACED PRIVATE ENTITY"
    with pytest.raises(adaptive.AdaptiveStrategyError, match="evidence"):
        adaptive.verify(comparison, plan, schedule, knowledge, scene, caps)


def test_ced_ranking_pass_groups_and_failure_flags_are_only_signals():
    # Use the already-ranked CED service vocabulary, never create new
    # independently verified project evidence from an asserted model output.
    source = _scene()
    _, _, _, plan, _, comparison = _evidence(source)
    row = _row(comparison, "tracks[0]", plan)
    alt = _alternatives(row)["skeletal_animation"]
    assert alt["independent_evidence_level"] in {
        "INSUFFICIENT_INDEPENDENT_EVIDENCE",
        "NEGATIVE_OBSERVATION", "MULTI_PROJECT_REVIEWED",
    }
    assert type(alt["reviewed_success_project_groups"]) is int
    assert alt["current_cutscene_fidelity_verified"] is False
    assert comparison["native_execution_authorized"] is False


def test_invalid_optional_adaptive_hints_cannot_invent_or_duplicate_actions():
    _, _, _, plan, _, comparison = _evidence()
    hints = adaptive.proposal_hints(comparison)
    bad = copy.deepcopy(hints)
    first = plan["elements"][0]["occurrence_id"]
    bad[first]["alternatives"] = [{"action": "execute_unreal_python"}]
    bad[first]["suggested_action"] = "execute_unreal_python"
    class NeverCalled:
        def complete_json(self, **kwargs):
            pytest.fail("Untrusted strategy hints cannot reach model")
    with pytest.raises(plans.ElementPlanError, match="invented"):
        plans.review_with_model(plan, provider=NeverCalled(), strategy_hints=bad)
