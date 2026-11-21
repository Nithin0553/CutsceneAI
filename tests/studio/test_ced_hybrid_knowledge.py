"""Hybrid CED contracts: graph context, complete retrieval, local privacy and review."""
from __future__ import annotations

import copy
import hashlib
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
    assert result["source_occurrence_count"] == 8
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
    with pytest.raises(book.CEDRulebookError):
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
        with pytest.raises(shared_review.SharedReviewError, match="private"):
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
