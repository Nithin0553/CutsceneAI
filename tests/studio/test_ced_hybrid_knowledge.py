"""Hybrid CED contracts: graph context, complete retrieval, local privacy and review."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for folder in ("ced", "studio", "readiness", "learning"):
    sys.path.insert(0, str(ROOT / "packages" / folder))

import case_memory
import ced_agent_knowledge as knowledge
import ced_rulebook as book
import knowledge_service as service
import semantic_graph
import shared_review
import strategy_recipes


def _source():
    return {
        "source": {"engine": "unity", "engine_version": "6000.3",
                   "project_fingerprint": "private-source"},
        "cutscene_id": "PrivateCutscene_DoNotExport",
        "entities": [
            {"entity_id": "actor-private-id", "ced_type": "entity.character",
             "name": "Customer Hero", "parent_entity_id": "root-private-id"},
            {"entity_id": "root-private-id", "ced_type": "entity.prop",
             "name": "Customer Scene Secret"},
            {"entity_id": "camera-private-id", "ced_type": "entity.camera",
             "parent_entity_id": "actor-private-id", "name": "Customer Camera"},
        ],
        "tracks": [{
            "track_id": "camera-track-private", "ced_type": "camera.transform",
            "binding_entity_id": "camera-private-id", "name": "Customer Footage",
            "sections": [
                {"section_id": "camera-first-private", "ced_type": "camera.fov",
                 "payload": {"animation": {"curves": [
                     {"ced_type": "camera.fov", "name": "Proprietary Secret"}
                 ]}}}
            ],
        }],
        "relationships": [{
            "relationship_id": "private-parent-relation",
            "ced_type": "transform.parent",
            "source_id": "actor-private-id", "target_id": "root-private-id",
        }],
    }


def _review_rule():
    baseline = json.loads(book.BASE_RULES.read_text())["rules"][0]
    rule = copy.deepcopy(baseline)
    rule["rule_id"] = "hybrid-approved-quaternion-case"
    rule["ced"] = "transform.quaternion"
    rule["priority"] = 140
    rule["notes"] = "PRIVATE MATERIAL NAME /Game/Customer/Secret_Not_For_Sharing"
    return rule


def _native_evidence(store):
    record = {
        "kind": "cinetwin.behavior_comparison",
        "acceptance_status": "STRUCTURE_AND_MEASURED_MOTION_WITHIN_TOLERANCE",
        "native_persistence_status": "STRUCTURAL_READBACK_PASS_DIFFERENT_EDITOR_PROCESS",
        "generation_editor_pid": 101, "observation_editor_pid": 202,
        "evaluation": {
            "status": "NO_FLAGGED_DIFFERENCES",
            "overall_cutscene_fidelity": "NOT_ESTABLISHED",
        },
    }
    target = store / "native_evidence" / "comparison.json"
    target.write_text(json.dumps(record))
    return target


def test_semantic_graph_follows_parent_binding_and_containment_without_source_names():
    graph = semantic_graph.analyze(_source())
    assert graph.counts["entity.character"] == 1
    assert graph.counts["camera.fov"] == 2
    assert graph.counts["transform.parent"] == 1
    assert graph.unresolved_reference_count == 0
    assert graph.edge_count >= 5
    associated = graph.relations["entity.camera"]
    assert any(row["relation"] == "parent" and row["concept"] == "entity.character"
               for row in associated)
    assert any(row["relation"] == "reverse:binds"
               and row["concept"] == "camera.transform" for row in associated)
    dump = json.dumps(graph.relations)
    assert "Customer" not in dump
    assert "actor-private-id" not in dump


def test_unified_retrieval_returns_grounded_contextual_rules_and_private_safe_ledger():
    result = knowledge.retrieve(
        _source(), target_capabilities={"camera.lens_model": True},
        source_version="6000.3", target_version="5.8",
    )
    assert result["schema_version"] == "2"
    assert result["retrieval_complete"] is True
    assert result["source_ced_count"] == len(result["coverage_ledger"])
    assert result["source_occurrence_count"] == 7
    assert result["no_native_write_permission"] is True
    assert result["shared_promotion_authorized"] is False
    by_ced = {x["ced"]: x for x in result["entries"]}
    assert by_ced["camera.fov"]["source_occurrences"] == 2
    assert by_ced["camera.fov"]["rules"][0]["rule_id"] == "unity-unreal-camera-fov"
    assert "camera_fov" in by_ced["camera.fov"]["native_action_candidates"]
    assert by_ced["entity.camera"]["related_semantics"]
    assert by_ced["camera.fov"]["execution_authorized"] is False
    content = json.dumps(result)
    for sensitive in ("Customer", "Proprietary", "PrivateCutscene", "actor-private-id"):
        assert sensitive not in content
    assert len(result["knowledge_sha256"]) == 64


def test_pagination_accounts_for_every_unseen_semantic_without_lying():
    source = {"entities": [
        {"ced_type": f"unknown.vendor.feature{i:03d}", "name": "private"}
        for i in range(71)
    ]}
    first = service.retrieve(source, target_capabilities={}, page_size=48)
    second = service.retrieve(source, target_capabilities={}, page=1, page_size=48)
    assert first["source_ced_count"] == 71
    assert first["page_count"] == second["page_count"] == 2
    assert first["retrieved_count"] == 48
    assert first["omitted_count"] == 23
    assert first["retrieval_complete"] is False
    assert first["next_page"] == 1
    assert second["retrieved_count"] == 23
    assert second["page"] == 1 and second["next_page"] is None
    all_ced = {row["ced"] for row in first["entries"] + second["entries"]}
    assert all_ced == {row["ced"] for row in first["coverage_ledger"]}
    assert all(row["resolution_state"] == "UNKNOWN_SEMANTIC_INVESTIGATE"
               for row in first["entries"] + second["entries"])
    assert not any(row["native_action_candidates"]
                   for row in first["entries"] + second["entries"])
    with pytest.raises(service.KnowledgeServiceError, match="page"):
        service.retrieve(source, target_capabilities={}, page=2)


def test_source_capability_evidence_is_not_silently_invented():
    source = {"entities": [{"ced_type": "camera.fov"}]}
    uninspected = service.retrieve(
        source, target_capabilities={"camera.lens_model": True},
    )
    inspected = service.retrieve(
        source, target_capabilities={"camera.lens_model": True},
        source_capabilities={},
    )
    rule_a = uninspected["entries"][0]["rules"][0]
    rule_b = inspected["entries"][0]["rules"][0]
    assert rule_a["source_capability_check"] == "NOT_INSPECTED"
    assert rule_b["source_capabilities_not_observed"] == ["camera.vertical_fov"]
    assert rule_b["status"] == "CAPABILITY_EVIDENCE_MISSING"
    assert uninspected["knowledge_sha256"] != inspected["knowledge_sha256"]


def test_local_verified_case_is_advisory_and_kept_out_of_shared_baseline(tmp_path):
    source = _source()
    mapping = {"entities": {}}
    resolved = {"version": "0.1.0", "entries": [{
        "ced": "camera.fov", "status": "RESOLVED", "outcome": "CONVERTED",
        "resolver": "camera.vertical_fov.to_target_lens", "parameters": {},
    }]}
    validation = {
        "status": "PASS", "summary": {"failed": 0, "incomplete": 0},
        "checks": [{"status": "PASS", "id": "camera"}],
    }
    review = {
        "approve_mapping_examples": True, "reviewer": "reviewer-private",
        "source_sha256": case_memory._digest(source),
        "mapping_sha256": case_memory._digest(mapping),
        "resolved_sha256": case_memory._digest(resolved),
        "validation_sha256": case_memory._digest(validation),
    }
    case = case_memory.build_case(
        source, mapping, resolved, validation=validation, review=review,
    )
    assert case["status"] == "MAPPING_VERIFIED"
    case_memory.save_case(case, tmp_path / "private-cases")
    result = service.retrieve(
        source, target_capabilities={},
        case_store=tmp_path / "private-cases",
    )
    suggestions = result["private_verified_case_suggestions"]
    assert len(suggestions) == 1
    assert suggestions[0]["case_id"] == case["case_id"]
    assert suggestions[0]["scope"] == "PRIVATE_VERIFIED_MAPPING_ONLY"
    assert suggestions[0]["native_execution_permission"] is False
    assert suggestions[0]["cross_project_fidelity_claim"] is False
    assert "reviewer-private" not in json.dumps(result)
    assert "PrivateCutscene" not in json.dumps(result)
    assert result["shared_promotion_authorized"] is False


def test_shared_review_requires_consent_and_an_existing_native_approval(tmp_path):
    store = tmp_path / "knowledge"
    rule = _review_rule()
    candidate_id = book.propose(store, rule, origin="USER",
                                feature_sha256="a" * 64)
    output = tmp_path / "share.json"
    with pytest.raises(shared_review.SharedReviewError, match="consent"):
        shared_review.stage_for_review(
            store, output, candidate_ids=[candidate_id],
            explicit_sharing_consent=False,
        )
    with pytest.raises(shared_review.SharedReviewError, match="reviewed CED record"):
        shared_review.stage_for_review(
            store, output, candidate_ids=[candidate_id],
            explicit_sharing_consent=True,
        )
    assert not output.exists()


def test_only_sanitized_approved_rules_can_be_staged_not_published(tmp_path):
    store = tmp_path / "knowledge"
    candidate_id = book.propose(
        store, _review_rule(), origin="USER", feature_sha256="c" * 64,
    )
    _native_evidence(store)
    book.promote(
        store, candidate_id, evidence_name="comparison.json",
        reviewer="qa-secret-identity", held_out_passed=True,
        regression_passed=True,
    )
    output = tmp_path / "review-bundle.json"
    bundle = shared_review.stage_for_review(
        store, output, candidate_ids=[candidate_id],
        explicit_sharing_consent=True,
    )
    assert bundle["status"] == "REVIEW_ONLY_NOT_TRUSTED_NOT_EXECUTABLE"
    assert bundle["verified_shared_release"] is False
    assert bundle["native_execution_permission"] is False
    assert len(bundle["bundle_sha256"]) == 64
    assert bundle["rules"][0]["rule"]["ced"] == "transform.quaternion"
    raw = output.read_text()
    for secret in ("PRIVATE MATERIAL", "/Game/Customer", "qa-secret-identity",
                   "private-source", "readback.json"):
        assert secret not in raw
    with pytest.raises(shared_review.SharedReviewError, match="new safe file"):
        shared_review.stage_for_review(
            store, output, candidate_ids=[candidate_id],
            explicit_sharing_consent=True,
        )


def test_review_bundle_rejects_untrusted_external_paths_and_strings():
    for bad in ("C:/Private/Scene.unity", "/Game/Hidden/Material",
                "https://example.invalid", "Unity Secret Value"):
        with pytest.raises(shared_review.SharedReviewError, match="Unreviewed text"):
            shared_review._public(bad)


def test_untrusted_graph_never_exposes_raw_property_or_asset_values():
    source = _source()
    source["assets"] = [{"asset_id": "asset/private/material",
                         "name": "Confidential Customer Material",
                         "source_ref": "Assets/ClientSecret.prefab",
                         "ced_type": "material.asset"}]
    source["entities"][0]["asset_id"] = "asset/private/material"
    result = knowledge.retrieve(source, target_capabilities={})
    text = json.dumps(result)
    assert "Confidential" not in text
    assert "Assets/ClientSecret" not in text
    assert any(row["relation"] == "uses_asset" and row["concept"] == "material.asset"
               for row in next(x for x in result["entries"]
                               if x["ced"] == "entity.character")["related_semantics"])



def test_strategy_recipe_uses_existing_actions_and_context_not_implicit_execution():
    registered = json.loads(book.BASE_RULES.read_text())["rules"]
    rule = next(item for item in registered if item["ced"] == "camera.fov")
    related = [{"relation": "depends_on", "concept": "entity.camera", "count": 1},
               {"relation": "reverse:contains", "concept": "camera.transform", "count": 1}]
    recipe = strategy_recipes.from_rule(
        rule, origin="BASELINE_REGISTERED_UNVERIFIED",
        related_semantics=related, installed_actions=["camera_fov"],
    )
    schema = json.loads((
        ROOT / "packages/contracts/dictionary/ced-strategy-recipe-v1.schema.json"
    ).read_text())
    portable = {key: value for key, value in recipe.items()
                if key not in {"execution_authorized", "resolver_reference",
                               "verified_case_ids", "recipe_sha256"}}
    assert set(portable) == set(schema["required"])
    assert recipe["recipe_id"] == rule["rule_id"]
    assert recipe["semantic_ids"] == ["camera.fov", "entity.camera"]
    assert recipe["alternatives"][0]["required_native_actions"] == ["camera_fov"]
    assert recipe["alternatives"][0]["verification_domains"] == ["camera", "persistence"]
    assert recipe["execution_authorized"] is False
    assert recipe["provenance"]["status"] == "BASELINE_ADVISORY"
    assert len(recipe["recipe_sha256"]) == 64

    source = _source()
    knowledge_response = knowledge.retrieve(
        source, target_capabilities={"camera.lens_model": True},
    )
    retrieved = next(item for item in knowledge_response["entries"]
                     if item["ced"] == "camera.fov")["rules"][0]
    reference = retrieved["strategy_recipe"]
    assert reference["recipe_id"] == recipe["recipe_id"]
    assert reference["required_native_actions"] == ["camera_fov"]
    assert reference["runtime_execution_authorized"] is False


def test_strategy_recipe_rejects_unregistered_or_unsafe_source_semantic():
    baseline = json.loads(book.BASE_RULES.read_text())["rules"][0]
    invalid = copy.deepcopy(baseline)
    invalid["ced"] = "Private Customer /Assets/Secret"
    with pytest.raises(strategy_recipes.StrategyRecipeError, match="identifier"):
        strategy_recipes.from_rule(
            invalid, origin="BASELINE_REGISTERED_UNVERIFIED",
            related_semantics=[], installed_actions=["transform"],
        )
    with pytest.raises(strategy_recipes.StrategyRecipeError, match="origin"):
        strategy_recipes.from_rule(
            baseline, origin="AI_ARBITRARY_CODE",
            related_semantics=[], installed_actions=["transform"],
        )



def test_model_projection_redacts_unknown_custom_class_names_and_local_ids():
    source = _source()
    source["entities"].append({
        "entity_id": "private-component-id",
        "ced_type": "ProprietaryClient.SecretAnimationSystem",
        "name": "Confidential User Script",
        "parent_entity_id": "actor-private-id",
    })
    result = knowledge.retrieve(
        source, target_capabilities={"ClientOnly.SecretNativeFeature": True}
    )
    assert any(x["ced"] == "ProprietaryClient.SecretAnimationSystem"
               for x in result["entries"]), "local inspection retains exact unknowns"
    source_rule = next(x for x in result["entries"] if x["ced"] == "camera.fov")
    source_rule["rules"][0]["parameter_fields"].append("PrivateCompany.TransformField")
    source_rule["rules"][0]["required_evidence"].append("source.CustomerSecret.asset")
    safe = knowledge.model_projection(result)
    prompt = json.dumps(safe)
    for secret in ("ProprietaryClient", "SecretAnimationSystem", "Confidential",
                   "Customer", "ClientOnly", "PrivateCompany", "actor-private-id",
                   "PrivateCutscene"):
        assert secret not in prompt
    assert "unknown.unclassified." in prompt
    assert "private_parameter" in prompt
    assert "private_evidence_requirement" in prompt
    assert safe["unrecognized_target_capability_count"] == 1
    assert safe["knowledge_sha256"] == result["knowledge_sha256"]
    assert safe["no_native_write_permission"] is True
    assert safe["shared_promotion_authorized"] is False
    assert safe["privacy_projection"].startswith("MODEL_SAFE")
    unknown = next(x for x in safe["entries"]
                   if x["ced"].startswith("unknown.unclassified."))
    assert unknown["native_action_candidates"] == []
    assert unknown["execution_authorized"] is False



def test_sparse_agent_diagnostic_does_not_require_private_case_memory(tmp_path):
    stored = tmp_path / "approved-cases"
    stored.mkdir()
    result = knowledge.retrieve(
        {"source": "test", "tracks": [{"ced_type": "transform.rotation", "sections": []}]},
        target_capabilities={}, case_store=stored,
    )
    assert result["private_verified_case_suggestions"] == []
    assert result["entries"][0]["ced"] == "transform.rotation"
    assert result["no_native_write_permission"] is True
