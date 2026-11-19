"""CED rulebook: all concepts, local user feedback, approval and persistent reuse."""
from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "readiness"))

import adaptive_mapping
import ced_rulebook as book


def _rule():
    baseline = json.loads(book.BASE_RULES.read_text())["rules"][0]
    rule = copy.deepcopy(baseline)
    rule["rule_id"] = "approved-quaternion-translation-case"
    rule["ced"] = "transform.quaternion"
    rule["priority"] = 130
    return rule


def _evidence(store, filename="readback.json"):
    data = {
        "kind": "cinetwin.behavior_comparison",
        "acceptance_status": "STRUCTURE_AND_MEASURED_MOTION_WITHIN_TOLERANCE",
        "native_persistence_status": "STRUCTURAL_READBACK_PASS_DIFFERENT_EDITOR_PROCESS",
        "generation_editor_pid": 110, "observation_editor_pid": 220,
        "evaluation": {
            "status": "NO_FLAGGED_DIFFERENCES",
            "overall_cutscene_fidelity": "NOT_ESTABLISHED",
        },
    }
    path = store / "native_evidence" / filename
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _profile(engine, caps, evidence):
    return {
        "profile_id": engine + "-test",
        "engine": {"name": engine, "version": "5.8.1" if engine == "unreal" else "6000.3"},
        "capabilities": [{"id": cap, "state": "SUPPORTED"} for cap in caps],
        "evidence": [{"evidence_id": proof} for proof in evidence],
        "settings": {},
    }


def test_full_ced_taxonomy_has_explicit_unmapped_coverage():
    result = book.coverage()
    assert result["total_concepts"] > 150
    assert result["unmapped_concepts"] > 0
    by_id = {entry["ced"]: entry["mapping_status"] for entry in result["concepts"]}
    assert by_id["transform.rotation"] == "RULE_REGISTERED_NATIVE_FIDELITY_NOT_IMPLIED"
    assert by_id["character.quadruped"] == "UNMAPPED_REQUIRES_CANDIDATE"
    assert len(by_id) == result["total_concepts"]


def test_user_submission_is_persistent_but_not_usable_without_approval(tmp_path):
    store = tmp_path / "ced-knowledge"
    candidate_id = book.propose(store, _rule(), origin="USER", feature_sha256="a"*64)
    assert len(candidate_id) == 64
    assert book.propose(store, _rule(), origin="USER", feature_sha256="a"*64) == candidate_id
    assert len(list((store / "candidates").glob("*.json"))) == 1
    assert book.approved_rules(store) == []
    assert (store / "candidates" / (candidate_id + ".json")).is_file()

    source = _profile("unity", ["rotation.canonical_quaternion"], ["source.coordinate_basis"])
    target = _profile("unreal", ["rotator.semantic_fields"], ["target.rotation_semantics"])
    base = json.loads(book.BASE_RULES.read_text())
    before = adaptive_mapping.resolve_dictionary(
        ["transform.quaternion"], source, target, base, rulebook_store=store)
    assert before["entries"][0]["status"] == "BLOCKED"

    _evidence(store)
    approved = book.promote(
        store, candidate_id, evidence_name="readback.json", reviewer="qa_reviewer",
        held_out_passed=True, regression_passed=True)
    assert approved["native_render_fidelity_certified"] is False
    effective = book.approved_rules(store)
    assert len(effective) == 1
    assert effective[0]["rule_id"] == _rule()["rule_id"]
    after = adaptive_mapping.resolve_dictionary(
        ["transform.quaternion"], source, target, base, rulebook_store=store)
    assert after["entries"][0]["status"] == "RESOLVED"
    assert after["entries"][0]["rule_id"] == _rule()["rule_id"]


def test_unverified_or_invalid_evidence_cannot_approve_user_rule(tmp_path):
    store = tmp_path / "store"
    identifier = book.propose(store, _rule(), origin="USER", feature_sha256="b"*64)
    _evidence(store)
    with pytest.raises(book.CEDRulebookError, match="reviewer|required"):
        book.promote(store, identifier, evidence_name="readback.json",
                     reviewer="", held_out_passed=True, regression_passed=True)
    with pytest.raises(book.CEDRulebookError, match="reviewer|required"):
        book.promote(store, identifier, evidence_name="readback.json",
                     reviewer="qa_reviewer", held_out_passed=False, regression_passed=True)
    file = store / "native_evidence" / "readback.json"
    data = json.loads(file.read_text())
    data["observation_editor_pid"] = data["generation_editor_pid"]
    file.write_text(json.dumps(data))
    with pytest.raises(book.CEDRulebookError, match="verified pass"):
        book.promote(store, identifier, evidence_name="readback.json",
                     reviewer="qa_reviewer", held_out_passed=True, regression_passed=True)
    assert book.approved_rules(store) == []


def test_approved_rule_tampering_or_evidence_changes_fail_closed(tmp_path):
    store = tmp_path / "store"
    identifier = book.propose(store, _rule(), origin="TESTING", feature_sha256="c"*64)
    _evidence(store)
    book.promote(store, identifier, evidence_name="readback.json",
                 reviewer="qa_reviewer", held_out_passed=True, regression_passed=True)
    path = store / "native_evidence" / "readback.json"
    path.write_text(path.read_text() + " ")
    with pytest.raises(book.CEDRulebookError, match="evidence"):
        book.approved_rules(store)
    path.write_text(path.read_text().rstrip())
    # Restoring exact bytes permits reuse only when the original digest matches.
    assert len(book.approved_rules(store)) == 1
    candidate = store / "candidates" / (identifier + ".json")
    candidate.write_text(candidate.read_text().replace("transform.quaternion",
                                                        "transform.position"))
    with pytest.raises(book.CEDRulebookError, match="tampered"):
        book.approved_rules(store)


def test_unknown_new_ced_concept_needs_taxonomy_change_before_promotion(tmp_path):
    store = tmp_path / "store"
    new = _rule()
    new["ced"] = "custom.new_semantic_concept"
    candidate_id = book.propose(store, new, origin="USER", feature_sha256="d"*64)
    _evidence(store)
    with pytest.raises(book.CEDRulebookError, match="taxonomy"):
        book.promote(store, candidate_id, evidence_name="readback.json",
                     reviewer="qa_reviewer", held_out_passed=True, regression_passed=True)


def test_unregistered_resolver_cannot_run_even_with_fake_review(tmp_path):
    store = tmp_path / "store"
    new = _rule()
    new["resolution"]["resolver"] = "unsafe.custom_native_exec"
    candidate_id = book.propose(store, new, origin="TRAINING", feature_sha256="e"*64)
    _evidence(store)
    with pytest.raises(book.CEDRulebookError, match="registered"):
        book.promote(store, candidate_id, evidence_name="readback.json",
                     reviewer="qa_reviewer", held_out_passed=True, regression_passed=True)


def test_mapping_submission_rejects_invalid_engine_directions_and_symlink(tmp_path):
    store = tmp_path / "store"
    wrong = _rule()
    wrong["target"]["engine"] = "unity"
    with pytest.raises(book.CEDRulebookError, match="direction"):
        book.propose(store, wrong, origin="USER", feature_sha256="f"*64)
    other = tmp_path / "other"
    other.mkdir()
    link = tmp_path / "linked"
    try:
        link.symlink_to(other, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks unavailable on this runner.")
    with pytest.raises(book.CEDRulebookError, match="symlinks"):
        book.propose(link, _rule(), origin="USER", feature_sha256="f"*64)


def test_source_evidence_always_required_even_after_new_mapping_is_approved(tmp_path):
    store = tmp_path / "store"
    candidate_id = book.propose(store, _rule(), origin="USER", feature_sha256="1"*64)
    _evidence(store)
    book.promote(store, candidate_id, evidence_name="readback.json",
                 reviewer="qa_reviewer", held_out_passed=True, regression_passed=True)
    source = _profile("unity", ["rotation.canonical_quaternion"], [])
    target = _profile("unreal", ["rotator.semantic_fields"], [])
    entry = adaptive_mapping.resolve_dictionary(
        ["transform.quaternion"], source, target,
        json.loads(book.BASE_RULES.read_text()), rulebook_store=store)["entries"][0]
    assert entry["status"] == "NEEDS_EVIDENCE"
    assert set(entry["parameters"]["missing_evidence"]) == {
        "source.coordinate_basis", "target.rotation_semantics"}
