"""Element 2 completion: strict contracts, cross-page agent reasoning and signed review."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[2]
for folder in ("ced", "studio", "readiness", "learning", "tools"):
    sys.path.insert(0, str(ROOT / "packages" / folder)
                    if folder != "tools" else str(ROOT / "tools"))

import ced_knowledge
import ced_rulebook
import contracts
import knowledge_service
import review_queue
import shared_distribution
import shared_review
import strategy_ranking
import strategy_recipes
import studio_transfer_ai
from studio_model_provider import ModelResult


def _model_result(answer):
    return ModelResult(
        answer=answer, provider="OLLAMA_LOCAL", model="qwen-local",
        response_id="", response_sha256="d" * 64,
    )


def _large_source(count=79):
    return {
        "source": {"engine": "unity", "engine_version": "6000.3"},
        "entities": [{"ced_type": f"VendorPrivate.Concept{i:03d}",
                      "entity_id": f"private/{i}"} for i in range(count)],
        "tracks": [{"ced_type": "camera.fov", "sections": []}],
    }


def _keys(directory: Path, role: str):
    private = Ed25519PrivateKey.generate()
    private_path = directory / (role + ".private.pem")
    public_path = directory / (role + ".public.pem")
    private_path.write_bytes(private.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))
    public_path.write_bytes(private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ))
    return private_path, public_path, private.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw,
    )


def _bundle(tmp_path: Path):
    baseline = json.loads(ced_rulebook.BASE_RULES.read_text())["rules"][0]
    rule = copy.deepcopy(baseline)
    rule["rule_id"] = "reviewed-hybrid-candidate"
    rule["ced"] = "transform.quaternion"
    rule["priority"] = 120
    store = tmp_path / "private"
    cid = ced_rulebook.propose(
        store, rule, origin="USER", feature_sha256="c" * 64,
    )
    native = store / "native_evidence" / "comparison.json"
    native.write_text(json.dumps({
        "kind": "cinetwin.behavior_comparison",
        "acceptance_status": "STRUCTURE_AND_MEASURED_MOTION_WITHIN_TOLERANCE",
        "native_persistence_status": "STRUCTURAL_READBACK_PASS_DIFFERENT_EDITOR_PROCESS",
        "generation_editor_pid": 101, "observation_editor_pid": 202,
        "evaluation": {"status": "NO_FLAGGED_DIFFERENCES",
                       "overall_cutscene_fidelity": "NOT_ESTABLISHED"},
    }))
    ced_rulebook.promote(
        store, cid, evidence_name="comparison.json",
        reviewer="qa-reviewer", held_out_passed=True, regression_passed=True,
    )
    output = tmp_path / "staged.json"
    shared_review.stage_for_review(
        store, output, candidate_ids=[cid], explicit_sharing_consent=True,
    )
    return output, rule


def _reviewed_bundle(tmp_path):
    bundle, rule = _bundle(tmp_path)
    e = tmp_path / "native.json"
    h = tmp_path / "heldout.json"
    r = tmp_path / "regression.json"
    for path, value in ((e, "native"), (h, "heldout"), (r, "regression")):
        path.write_text(json.dumps({"report": value, "scope": "manual-review-only"}))
    reviewer_keys = {}
    approvals = []
    for reviewer, role in (
        ("independent-native", "NATIVE_EVIDENCE"),
        ("independent-privacy", "PRIVACY"),
    ):
        private, _, public = _keys(tmp_path, reviewer)
        reviewer_keys[reviewer] = public
        approvals.append(review_queue.sign_review(
            bundle, reviewer=reviewer, role=role,
            reviewer_private_key=private, native_evidence=e,
            heldout_report=h, regression_report=r,
            explicitly_approved=True,
        ))
    publisher_private, publisher_public, _ = _keys(tmp_path, "publisher")
    return bundle, rule, reviewer_keys, approvals, publisher_private, publisher_public


def test_runtime_contract_rejects_invalid_recipe_and_untrusted_manifest():
    manifest = json.loads((
        ROOT / "packages/contracts/dictionary/ced-shared-manifest-v1.json"
    ).read_text())
    assert contracts.validate_manifest(manifest) == manifest
    invalid = dict(manifest, runtime_execution_authority=True)
    with pytest.raises(contracts.ContractError, match="manifest"):
        contracts.validate_manifest(invalid)
    invalid = dict(manifest, invented_execution_permission=True)
    with pytest.raises(contracts.ContractError, match="Additional properties"):
        contracts.validate_manifest(invalid)
    rule = next(row for row in json.loads(
        ced_rulebook.BASE_RULES.read_text())["rules"] if row["ced"] == "camera.fov")
    recipe = strategy_recipes.from_rule(
        rule, origin="BASELINE_REGISTERED_UNVERIFIED",
        related_semantics=[{"relation": "depends_on", "concept": "entity.camera"}],
        installed_actions=["camera_fov"],
    )
    portable = {key: value for key, value in recipe.items()
                if key not in {"execution_authorized", "resolver_reference",
                               "verified_case_ids", "recipe_sha256"}}
    assert contracts.validate_recipe(portable) == portable
    bad = copy.deepcopy(portable)
    bad["relationships"][0]["to"] = "unregistered.secret"
    with pytest.raises(contracts.ContractError, match="missing concept"):
        contracts.validate_recipe(bad)
    bad = copy.deepcopy(portable)
    bad["native_code"] = "import unreal"
    with pytest.raises(contracts.ContractError, match="Additional properties"):
        contracts.validate_recipe(bad)


def test_every_source_concept_across_multiple_pages_is_accounted_for():
    source = _large_source()
    response = knowledge_service.retrieve_all(source, target_capabilities={})
    assert response["source_ced_count"] == 80
    assert response["source_page_count"] == 2
    assert response["retrieved_count"] == 80
    assert response["omitted_count"] == 0
    assert response["retrieval_complete"] and response["all_pages_retrieved"]
    assert len(response["source_page_sha256"]) == 2
    assert len({row["ced"] for row in response["entries"]}) == 80
    assert any(row["unknown_investigation"] == []
               for row in response["entries"] if row["ced"].startswith("VendorPrivate"))
    redacted = knowledge_service.redact_for_model(response)
    assert "VendorPrivate" not in json.dumps(redacted)
    assert "unknown.unclassified." in json.dumps(redacted)


def test_large_transfer_model_must_assess_every_batch_without_private_identifiers(
        monkeypatch):
    response = knowledge_service.retrieve_all(_large_source(), target_capabilities={})
    observed = []

    def fake_model(**kwargs):
        observed.append(kwargs)
        payload = kwargs["payload"]
        if kwargs["task"] == "cutsceneai_ced_page_review":
            assert "VendorPrivate" not in json.dumps(payload)
            return _model_result({
                "page_index": payload["page_index"],
                "risks": "Unknown custom components remain investigation-only",
                "candidate_approaches": "Use only evidence-backed installed adapters",
            })
        assert kwargs["task"] == "cutsceneai_pretransfer_choice"
        assert len(payload["ced_knowledge"]["page_analyses"]) == 4
        assert payload["ced_knowledge"]["pages_reviewed"] == 4
        return _model_result({
            "strategy": "native_source", "reason": "Registered native plan"
        })

    import studio_model_provider
    monkeypatch.setattr(studio_model_provider, "complete_json", fake_model)
    answer = studio_transfer_ai._model_choose({
        "summary": {"source_entity_count": 79},
        "allowed_strategies": ["native_source"],
        "ced_knowledge": response,
    })
    assert answer["strategy"] == "native_source"
    assert len(observed) == 5


def test_local_ranker_penalizes_distinct_failures_and_never_confuses_one_project():
    baseline = [{"rule_id": "candidate-action", "origin": "BASELINE_REGISTERED_UNVERIFIED",
                 "status": "RULE_CANDIDATE_REQUIRES_PREFLIGHT",
                 "capabilities_not_observed": [], "source_capabilities_not_observed": []}]
    def event(index, outcome):
        return {
            "kind": "cutsceneai.ced.mapping_experience", "schema_version": "1",
            "case_sha256": hashlib.sha256(f"case{index}".encode()).hexdigest(),
            "project_group_sha256": hashlib.sha256(f"project{index}".encode()).hexdigest(),
            "ced": "camera.fov", "rule_id": "candidate-action",
            "source_engine": "unity", "target_engine": "unreal",
            "source_version": "6000.3", "target_version": "5.8",
            "test_outcome": outcome, "native_readback_verified": outcome == "PASS",
            "human_reviewed": outcome == "PASS",
            "evidence_sha256": hashlib.sha256(f"proof{index}".encode()).hexdigest(),
        }
    few = strategy_ranking.rank_rules(
        baseline, ced="camera.fov", source_version="6000.3",
        target_version="5.8", feedback=[event(1, "PASS")],
    )[0]
    many = strategy_ranking.rank_rules(
        baseline, ced="camera.fov", source_version="6000.3",
        target_version="5.8",
        feedback=[event(i, "PASS") for i in range(4)],
    )[0]
    failures = strategy_ranking.rank_rules(
        baseline, ced="camera.fov", source_version="6000.3",
        target_version="5.8",
        feedback=[event(3, "FAIL"), event(4, "FAIL")],
    )[0]
    score = lambda item: item["advisory_ranking"]["context_score"]
    assert score(many) > score(few) > score(failures)
    assert many["advisory_ranking"]["independent_experience"][
        "evidence_level"] == "MULTI_PROJECT_REVIEWED"
    assert many["advisory_ranking"]["native_tool_authority"] is False


def test_review_queue_and_signed_release_install_revocation_and_no_downgrade(tmp_path):
    bundle, rule, trust, decisions, publisher_key, publisher_public = _reviewed_bundle(tmp_path)
    queue = tmp_path / "queue"
    queue.mkdir()
    with pytest.raises(review_queue.ReviewError, match="consent"):
        review_queue.submit(bundle, queue, explicit_consent=False)
    queued = review_queue.submit(bundle, queue, explicit_consent=True)
    assert queued["status"] == "PENDING_INDEPENDENT_REVIEW"
    assert review_queue.submit(bundle, queue, explicit_consent=True) == queued
    staged = review_queue.validated_bundle(review_queue.read(bundle))
    assert len(review_queue.verify_reviews(staged, decisions, trust)) == 2
    tampered = copy.deepcopy(decisions)
    tampered[0]["decision"] = "NOT_APPROVED"
    with pytest.raises(review_queue.ReviewError):
        review_queue.verify_reviews(staged, tampered, trust)
    first_file = tmp_path / "release1.json"
    with pytest.raises(shared_distribution.DistributionError, match="consent"):
        shared_distribution.sign_release(
            bundle, review_decisions=decisions, trusted_reviewers=trust,
            publisher_private_key=publisher_key, revision=1,
            previous_release_sha256=None, revoked_rule_ids=[],
            output_file=first_file, explicit_release_consent=False,
        )
    signed = shared_distribution.sign_release(
        bundle, review_decisions=decisions, trusted_reviewers=trust,
        publisher_private_key=publisher_key, revision=1,
        previous_release_sha256=None, revoked_rule_ids=[],
        output_file=first_file, explicit_release_consent=True,
    )
    store = tmp_path / "installed"
    store.mkdir()
    assert len(shared_distribution.verify_release(
        signed, shared_distribution._publisher_key(publisher_public))["rules"]) == 1
    with pytest.raises(shared_distribution.DistributionError, match="consent"):
        shared_distribution.install_release(
            first_file, trust_key_file=publisher_public, store=store,
            explicit_install_consent=False,
        )
    shared_distribution.install_release(
        first_file, trust_key_file=publisher_public, store=store,
        explicit_install_consent=True,
    )
    assert shared_distribution.installed_rules(
        store, trust_key_file=publisher_public)[0]["rule_id"] == rule["rule_id"]
    old_body = json.loads(first_file.read_text())
    old_body["rules"][0]["rule_id"] = "tampered-after-signature"
    forged = tmp_path / "forged.json"
    forged.write_text(json.dumps(old_body))
    with pytest.raises(shared_distribution.DistributionError, match="signature"):
        shared_distribution.install_release(
            forged, trust_key_file=publisher_public, store=store,
            explicit_install_consent=True,
        )
    second_file = tmp_path / "release2.json"
    shared_distribution.sign_release(
        bundle, review_decisions=decisions, trusted_reviewers=trust,
        publisher_private_key=publisher_key, revision=2,
        previous_release_sha256=review_queue.digest(signed),
        revoked_rule_ids=[rule["rule_id"]],
        output_file=second_file, explicit_release_consent=True,
    )
    shared_distribution.install_release(
        second_file, trust_key_file=publisher_public, store=store,
        explicit_install_consent=True,
    )
    assert shared_distribution.installed_rules(store, trust_key_file=publisher_public) == []
    with pytest.raises(shared_distribution.DistributionError, match="stale"):
        shared_distribution.install_release(
            first_file, trust_key_file=publisher_public, store=store,
            explicit_install_consent=True,
        )


def test_untrusted_external_signer_cannot_publish(tmp_path):
    bundle, _rule, trust, decisions, private_key, _public = _reviewed_bundle(tmp_path)
    forged_trust = dict(trust)
    forged_trust["independent-native"] = _keys(tmp_path, "attacker")[2]
    with pytest.raises(shared_distribution.DistributionError, match="reviewer"):
        shared_distribution.sign_release(
            bundle, review_decisions=decisions, trusted_reviewers=forged_trust,
            publisher_private_key=private_key, revision=1,
            previous_release_sha256=None, revoked_rule_ids=[],
            output_file=tmp_path / "untrusted.json",
            explicit_release_consent=True,
        )



def test_signed_distribution_rejects_unknown_private_capability_tokens():
    rule = copy.deepcopy(json.loads(ced_rulebook.BASE_RULES.read_text())["rules"][0])
    rule["rule_id"] = "signed-public-case"
    rule["ced"] = "transform.quaternion"
    rule["source"]["capabilities_all"].append("PrivateClient.RigInternalSecret")
    with pytest.raises(shared_distribution.DistributionError, match="private unknown"):
        shared_distribution._validate_rules([rule])



def test_signed_release_can_resume_exact_pending_bytes_and_reinstall_idempotently(tmp_path):
    bundle, _rule, trust, decisions, publisher_key, publisher_public = _reviewed_bundle(
        tmp_path
    )
    release_file = tmp_path / "release1.json"
    release = shared_distribution.sign_release(
        bundle, review_decisions=decisions, trusted_reviewers=trust,
        publisher_private_key=publisher_key, revision=1,
        previous_release_sha256=None, revoked_rule_ids=[],
        output_file=release_file, explicit_release_consent=True,
    )
    store = tmp_path / "resumed-install"
    store.mkdir()
    serialized = json.dumps(release, indent=2, sort_keys=True) + "\n"
    (store / "release-000001.json").write_text(serialized)
    (store / "active.pending").write_text(serialized)
    result = shared_distribution.install_release(
        release_file, trust_key_file=publisher_public,
        store=store, explicit_install_consent=True,
    )
    assert result["status"] == "SIGNED_SHARED_KNOWLEDGE_INSTALLED"
    assert not (store / "active.pending").exists()
    assert (store / "active.json").read_text() == serialized
    repeated = shared_distribution.install_release(
        release_file, trust_key_file=publisher_public,
        store=store, explicit_install_consent=True,
    )
    assert repeated["status"] == "SIGNED_SHARED_KNOWLEDGE_ALREADY_INSTALLED"
    assert len(list(store.glob("release-*.json"))) == 1


def test_signed_release_rejects_conflicting_interrupted_data(tmp_path):
    bundle, _rule, trust, decisions, publisher_key, publisher_public = _reviewed_bundle(
        tmp_path
    )
    release_file = tmp_path / "release1.json"
    shared_distribution.sign_release(
        bundle, review_decisions=decisions, trusted_reviewers=trust,
        publisher_private_key=publisher_key, revision=1,
        previous_release_sha256=None, revoked_rule_ids=[],
        output_file=release_file, explicit_release_consent=True,
    )
    store = tmp_path / "conflicting-install"
    store.mkdir()
    (store / "active.pending").write_text('{"forged":"different"}')
    with pytest.raises(shared_distribution.DistributionError, match="Conflicting"):
        shared_distribution.install_release(
            release_file, trust_key_file=publisher_public,
            store=store, explicit_install_consent=True,
        )
    assert not (store / "active.json").exists()
    assert not list(store.glob("release-*.json"))


def test_review_signing_cli_refuses_to_replace_existing_decision(tmp_path):
    bundle, _rule, _trust, _decisions, _publisher_key, _publisher_public = _reviewed_bundle(
        tmp_path
    )
    reviewer_key, _pub, _raw = _keys(tmp_path, "separate-reviewer")
    output = tmp_path / "existing-review.json"
    output.write_text("DO NOT OVERWRITE")
    with pytest.raises(FileExistsError):
        ced_knowledge.main([
            "sign-review",
            "--bundle", str(bundle),
            "--reviewer", "independent-verify",
            "--role", "NATIVE_EVIDENCE",
            "--private-key", str(reviewer_key),
            "--native-evidence", str(tmp_path / "native.json"),
            "--heldout-report", str(tmp_path / "heldout.json"),
            "--regression-report", str(tmp_path / "regression.json"),
            "--output", str(output),
            "--explicit-review-approval",
        ])
    assert output.read_text() == "DO NOT OVERWRITE"
