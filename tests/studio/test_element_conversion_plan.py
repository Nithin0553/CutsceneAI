"""Element 3.1 — complete source-grounded, per-occurrence agent planning."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
for folder in ("studio", "ced"):
    sys.path.insert(0, str(ROOT / "packages" / folder))

import ced_agent_knowledge as ced
import studio_element_plan as elements


def source_scene():
    return {
        "schema_version": "0.1.0",
        "cutscene_id": "PRIVATE_CLIENT_SCENE",
        "source": {"engine": "unity", "engine_version": "6000.3"},
        "assets": [{"asset_id": "private-asset-007", "ced_type": "asset.model",
                    "name": "CLASSIFIED_CHARACTER_ASSET"}],
        "entities": [
            {"entity_id": "parent-id", "ced_type": "entity.prop",
             "name": "PRIVATE_ROOT"},
            {"entity_id": "actor-id", "ced_type": "entity.character",
             "parent_entity_id": "parent-id", "asset_id": "private-asset-007",
             "name": "PRIVATE_LEAD_CHARACTER"},
            {"entity_id": "camera-id", "ced_type": "entity.camera",
             "name": "PRIVATE_CAMERA"},
            {"entity_id": "vendor-id", "ced_type": "CustomStudio.SecretRigPlugin",
             "name": "TOP_SECRET_SCRIPT"},
        ],
        "tracks": [
            {"track_id": "camera-track-id", "ced_type": "camera.transform",
             "binding_entity_id": "camera-id", "name": "CONFIDENTIAL_SHOT",
             "sections": [
                 {"section_id": "private-section", "ced_type": "camera.fov",
                  "payload": {"animation": {"curves": [
                      {"curve_id": "private-curve", "canonical_semantic": "camera.fov",
                       "property_name": "CONFIDENTIAL_FOCAL_LENGTH"}
                  ]}}}
             ]},
            {"track_id": "actor-track-id", "ced_type": "animation.track",
             "binding_entity_id": "actor-id", "sections": []},
        ],
        "relationships": [
            {"relationship_id": "rel-private", "ced_type": "transform.parent",
             "source_id": "actor-id", "target_id": "parent-id"},
        ],
    }


def evidence(source=None, *, camera_capable=True):
    scene = source or source_scene()
    capabilities = {
        "cine_camera_actor": camera_capable,
        "sequencer_skeletal_animation_track": True,
        "sequencer_visibility_track": True,
        "fbx_asset_import": True,
    }
    knowledge = ced.retrieve_all(
        scene, target_capabilities=capabilities,
        source_version="6000.3", target_version="5.8",
    )
    return scene, knowledge, capabilities


def test_per_occurrence_inventory_covers_every_nested_curve_and_duplicate_semantics():
    source, knowledge, caps = evidence()
    plan = elements.prepare(source, knowledge, caps)
    assert plan["source_occurrence_count"] == knowledge["source_occurrence_count"]
    assert plan["source_occurrence_count"] == 10
    assert plan["model_reviewed_count"] == 0
    assert plan["no_native_execution_permission"] is True
    assert plan["native_conversion_executed"] is False
    assert len({x["occurrence_id"] for x in plan["elements"]}) == 10
    by_location = {x["source_location"]: x for x in plan["elements"]}
    assert by_location["entities[1]"]["dependencies"] == [
        by_location["entities[0]"]["occurrence_id"],
        by_location["assets[0]"]["occurrence_id"],
    ]
    assert by_location["tracks[0]"]["dependencies"] == [
        by_location["entities[2]"]["occurrence_id"]
    ]
    assert by_location["tracks[0].sections[0]"]["dependencies"] == [
        by_location["tracks[0]"]["occurrence_id"]
    ]
    curve = by_location["tracks[0].sections[0].payload.animation.curves[0]"]
    assert curve["ced"] == "camera.fov"
    assert curve["dependencies"] == [by_location["tracks[0].sections[0]"]["occurrence_id"]]
    assert by_location["entities[3]"]["state"] == "UNKNOWN_SEMANTIC_INVESTIGATE"
    assert by_location["entities[3]"]["candidate_actions"] == []
    assert "camera_setup" in by_location["entities[2]"]["candidate_actions"]
    body = json.dumps(plan)
    for secret in ("PRIVATE_CLIENT_SCENE", "CLASSIFIED", "PRIVATE_ROOT",
                   "TOP_SECRET", "CustomStudio", "CONFIDENTIAL",
                   "camera-id", "actor-id", "private-asset-007"):
        assert secret not in body
    elements.verify(plan, source, knowledge, caps)


def test_capability_refusal_and_ambiguous_or_missing_source_dependencies():
    source, knowledge, caps = evidence(camera_capable=False)
    plan = elements.prepare(source, knowledge, caps)
    camera = next(x for x in plan["elements"] if x["source_location"] == "entities[2]")
    assert camera["candidate_actions"] == []
    assert camera["state"] == "TARGET_CAPABILITY_MISSING"
    assert "cine_camera_actor" in camera["missing_target_capabilities"]
    source["entities"][1]["parent_entity_id"] = "not-an-actual-parent"
    new_knowledge = ced.retrieve_all(
        source, target_capabilities=caps,
    )
    new_plan = elements.prepare(source, new_knowledge, caps)
    actor = next(x for x in new_plan["elements"] if x["source_location"] == "entities[1]")
    assert actor["state"] == "UNRESOLVED_SOURCE_DEPENDENCY"
    assert actor["candidate_actions"] == []
    assert actor["unresolved_dependencies"] == ["parent_MISSING_OR_AMBIGUOUS"]
    source["entities"][0]["entity_id"] = "actor-id"  # duplicate ID
    another = ced.retrieve_all(source, target_capabilities=caps)
    with_duplicate = elements.prepare(source, another, caps)
    assert next(x for x in with_duplicate["elements"]
                if x["source_location"] == "tracks[1]")["state"] == (
        "UNRESOLVED_SOURCE_DEPENDENCY"
    )


def test_model_reviews_all_elements_in_exact_bounded_batches_without_private_source():
    source, knowledge, caps = evidence()
    initial = elements.prepare(source, knowledge, caps)
    calls = []

    class Model:
        def complete_json(self, **kwargs):
            calls.append(kwargs)
            assert kwargs["task"] == "cutsceneai_element_conversion_choices"
            body = json.dumps(kwargs["payload"])
            for forbidden in ("PRIVATE_", "CONFIDENTIAL", "CustomStudio",
                              "actor-id", "camera-id"):
                assert forbidden not in body
            choices = []
            for element in kwargs["payload"]["elements"]:
                options = element["candidate_actions"]
                choices.append({
                    "occurrence_id": element["occurrence_id"],
                    "action": options[0] if options else "report_only",
                })
            return SimpleNamespace(
                answer={"choices": choices}, response_sha256="b" * 64,
            )

    reviewed, hashes = elements.review_with_model(initial, provider=Model())
    assert len(calls) == 1
    assert hashes == ["b" * 64]
    assert reviewed["model_reviewed_count"] == len(reviewed["elements"])
    assert all(row["model_reviewed"] for row in reviewed["elements"])
    assert all(row["selected_action"] in {"report_only", *row["candidate_actions"]}
               for row in reviewed["elements"])
    assert reviewed["native_conversion_executed"] is False
    elements.verify(reviewed, source, knowledge, caps)


def test_agent_must_review_each_element_even_across_separate_batches():
    source = {"entities": [
        {"ced_type": "entity.camera", "entity_id": f"camera-{i}"}
        for i in range(31)
    ]}
    caps = {"cine_camera_actor": True}
    knowledge = ced.retrieve_all(source, target_capabilities=caps)
    initial = elements.prepare(source, knowledge, caps)
    pages = []

    class Model:
        def complete_json(self, **kwargs):
            page = kwargs["payload"]["page_index"]
            pages.append(page)
            return SimpleNamespace(
                answer={"choices": [
                    {"occurrence_id": item["occurrence_id"], "action": "camera_setup"}
                    for item in kwargs["payload"]["elements"]
                ]}, response_sha256="c" * 64,
            )

    reviewed, hashes = elements.review_with_model(initial, provider=Model())
    assert pages == [0, 1, 2]
    assert len(hashes) == 3
    assert reviewed["model_reviewed_count"] == 31
    elements.verify(reviewed, source, knowledge, caps)


@pytest.mark.parametrize("failure", ["omission", "duplicate", "wrong_id",
                                      "invented_action", "extra_code"])
def test_model_cannot_omit_duplicate_or_invent_element_operations(failure):
    source, knowledge, caps = evidence()
    baseline = elements.prepare(source, knowledge, caps)
    ids = [x["occurrence_id"] for x in baseline["elements"]]
    choices = [{"occurrence_id": item["occurrence_id"], "action": "report_only"}
               for item in baseline["elements"]]
    if failure == "omission":
        choices.pop()
    if failure == "duplicate":
        choices[1]["occurrence_id"] = choices[0]["occurrence_id"]
    if failure == "wrong_id":
        choices[0]["occurrence_id"] = "E99999"
    if failure == "invented_action":
        choices[0]["action"] = "import_unreal; destroy_project()"
    if failure == "extra_code":
        choices[0]["python"] = "import unreal"
    with pytest.raises(elements.ElementPlanError):
        elements.apply_choices(baseline, choices, expected_ids=ids)


def test_regrounded_verification_rejects_tampering_even_with_recomputed_digest():
    source, knowledge, caps = evidence()
    baseline = elements.prepare(source, knowledge, caps)
    selections = [
        {"occurrence_id": row["occurrence_id"], "action": "report_only"}
        for row in baseline["elements"]
    ]
    reviewed = elements.apply_choices(
        baseline, selections,
        expected_ids=[row["occurrence_id"] for row in baseline["elements"]],
    )
    falsified = copy.deepcopy(reviewed)
    falsified["elements"][0]["candidate_actions"] = ["destroy_level"]
    falsified.pop("element_plan_sha256")
    falsified["element_plan_sha256"] = elements._digest(falsified)
    with pytest.raises(elements.ElementPlanError, match="schema|changed"):
        elements.verify(falsified, source, knowledge, caps)
    source["entities"][0]["ced_type"] = "entity.camera"
    with pytest.raises(elements.ElementPlanError):
        elements.verify(reviewed, source, knowledge, caps)


def test_large_source_is_inventoried_but_model_review_budget_fails_closed():
    source = {"entities": [{"ced_type": "entity.camera"} for _ in range(257)]}
    caps = {"cine_camera_actor": True}
    knowledge = ced.retrieve_all(source, target_capabilities=caps)
    plan = elements.prepare(source, knowledge, caps)
    assert plan["source_occurrence_count"] == 257
    class Model:
        def complete_json(self, **kwargs):
            pytest.fail("Oversize model review must refuse before model invocation")
    with pytest.raises(elements.ElementPlanError, match="budget"):
        elements.review_with_model(plan, provider=Model())


def test_malformed_timeline_does_not_silently_disappear_from_inventory():
    source, knowledge, caps = evidence()
    source["tracks"][0]["sections"] = {"hidden": "not a list"}
    with pytest.raises(elements.ElementPlanError, match="section"):
        elements.prepare(source, knowledge, caps)



def test_versioned_element_contract_rejects_extra_fields_even_if_rehashed():
    source, knowledge, caps = evidence()
    plan = elements.prepare(source, knowledge, caps)
    tampered = copy.deepcopy(plan)
    tampered["elements"][0]["unsafe_native_code"] = "import unreal"
    tampered.pop("element_plan_sha256")
    tampered["element_plan_sha256"] = elements._digest(tampered)
    with pytest.raises(elements.ElementPlanError, match="schema"):
        elements.verify(tampered, source, knowledge, caps)
    source_path = (ROOT / "packages/contracts/agent/element-conversion-plan-v1.schema.json")
    schema = json.loads(source_path.read_text())
    assert schema["properties"]["no_native_execution_permission"]["const"] is True
    assert schema["properties"]["native_conversion_executed"]["const"] is False
    assert "destroy_project" not in json.dumps(schema)
