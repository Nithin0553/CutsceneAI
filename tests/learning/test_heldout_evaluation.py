"""Held-out mapping evaluation must not leak across projects or reward abstention."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "packages" / "learning"))

import case_memory
import heldout_evaluation as heldout


def approved(project: str, *, feature: str = "camera.cut", resolver: str = "camera.native"):
    source = {
        "source": {"engine": "unity", "project_fingerprint": project},
        "cutscene_id": project + ":scene",
        "entities": [{"ced_type": "entity.prop"}],
        "tracks": [{"ced_type": feature, "sections": [{"ced_type": feature, "payload": {}}]}],
    }
    mapping = {"entities": {"actor": {"actor_label": "target"}}}
    resolved = {"version": "0.1.0", "entries": [{
        "ced": feature, "resolver": resolver, "outcome": "CONVERTED",
        "status": "RESOLVED", "parameters": {},
    }]}
    validation = {
        "status": "PASS", "summary": {"failed": 0, "incomplete": 0},
        "checks": [{"status": "PASS"}],
    }
    review = {
        "approve_mapping_examples": True, "reviewer": "Independent reviewer",
        "source_sha256": case_memory._digest(source),
        "mapping_sha256": case_memory._digest(mapping),
        "resolved_sha256": case_memory._digest(resolved),
        "validation_sha256": case_memory._digest(validation),
    }
    return case_memory.build_case(source, mapping, resolved, validation=validation, review=review)


def corpus():
    return [
        approved("source-a"),
        approved("source-b"),
        approved("source-c"),
        approved("source-d"),
        approved("source-e"),
        approved("source-f"),
    ]


def test_split_is_deterministic_and_groups_never_overlap():
    cases = corpus()
    a = heldout.build_manifest(cases, seed="test123")
    b = heldout.build_manifest(list(reversed(cases)), seed="test123")
    assert a == b
    splits = a["splits"]
    groups = [set(splits[p]["project_fingerprints"]) for p in ("train", "validation", "holdout")]
    assert all(groups)
    assert all(not groups[i] & groups[j] for i in range(3) for j in range(i + 1, 3))
    assert len(set.union(*groups)) == 6
    assert sum(len(x["case_ids"]) for x in splits.values()) == 6
    assert a["model_trained"] is False


def test_fewer_than_three_independent_groups_is_blocked():
    with pytest.raises(heldout.EvaluationError, match="three independent"):
        heldout.build_manifest([approved("a"), approved("b")])
    with pytest.raises(heldout.EvaluationError, match="three independent"):
        heldout.build_manifest([
            approved("a"), approved("a", feature="light.animation"), approved("b"),
        ])


def test_candidate_and_incomplete_cases_do_not_train():
    cases = corpus()
    candidate = copy.deepcopy(cases[0])
    candidate["status"] = "CANDIDATE"
    candidate["case_id"] = case_memory._digest(
        {k: v for k, v in candidate.items() if k != "case_id"}
    )[:24]
    manifest = heldout.build_manifest(cases + [candidate])
    assert manifest["verified_cases"] == 6
    bad = copy.deepcopy(cases)
    bad[0]["review_approved"] = False
    with pytest.raises(heldout.EvaluationError, match="review evidence"):
        heldout.build_manifest(bad)


def test_same_source_bytes_in_two_groups_is_rejected():
    cases = corpus()
    changed = copy.deepcopy(cases[0])
    changed["source"]["project_fingerprint"] = cases[1]["source"]["project_fingerprint"]
    changed["case_id"] = case_memory._digest(
        {k: v for k, v in changed.items() if k != "case_id"}
    )[:24]
    with pytest.raises(heldout.EvaluationError, match="different project groups"):
        heldout.build_manifest(cases + [changed])


def test_data_export_only_contains_training_project_cases(tmp_path):
    cases = corpus()
    manifest = heldout.build_manifest(cases)
    result = heldout.export_training(cases, manifest, tmp_path / "batch")
    assert result["training_examples"] == len(manifest["splits"]["train"]["case_ids"])
    ids = [
        json.loads(line)["case_id"]
        for line in (tmp_path / "batch" / "train.jsonl").read_text().splitlines()
    ]
    assert set(ids) == set(manifest["splits"]["train"]["case_ids"])
    assert not (set(ids) & set(manifest["splits"]["holdout"]["case_ids"]))
    # Only reviewed policy identifiers may train: never ship executable
    # parameters or arbitrary source/target asset paths in the JSONL.
    exported = (tmp_path / "batch" / "train.jsonl").read_text()
    assert '"parameters"' not in exported
    assert "local_path" not in exported
    with pytest.raises(heldout.EvaluationError, match="overwrite"):
        heldout.export_training(cases, manifest, tmp_path / "batch")


def test_retrieval_baseline_is_strictly_train_only():
    cases = corpus()
    manifest = heldout.build_manifest(cases)
    pred = heldout.retrieval_predictions(cases, manifest, split="holdout")
    assert len(pred) == len(manifest["splits"]["holdout"]["case_ids"])
    result = heldout.evaluate_predictions(cases, manifest, pred, split="holdout")
    assert result["total_cases"] > 0
    assert result["coverage"] == 1.0
    assert result["exact_match_on_attempted"] == 1.0
    assert result["engine_fidelity_tested"] is False
    assert result["release_authorized"] is False


def test_policy_eval_tracks_wrong_predictions_and_abstentions():
    cases = corpus()
    manifest = heldout.build_manifest(cases)
    chosen = manifest["splits"]["validation"]["case_ids"]
    predictions = [
        {"case_id": cid, "abstain": False,
         "labels": [{"ced": "camera.cut", "resolver": "incorrect.strategy", "outcome": "CONVERTED"}]}
        for cid in chosen
    ]
    result = heldout.evaluate_predictions(cases, manifest, predictions, split="validation")
    assert result["coverage"] == 1.0
    assert result["exact_match_on_attempted"] == 0.0
    assert result["false_positive_labels"] == len(chosen)
    abstained = [{"case_id": cid, "abstain": True, "labels": []} for cid in chosen]
    result = heldout.evaluate_predictions(cases, manifest, abstained, split="validation")
    assert result["coverage"] == 0.0
    assert result["exact_match_on_attempted"] == 0.0


def test_wrong_split_and_executable_parameters_blocked():
    cases = corpus()
    manifest = heldout.build_manifest(cases)
    validation_id = manifest["splits"]["validation"]["case_ids"][0]
    train_id = manifest["splits"]["train"]["case_ids"][0]
    with pytest.raises(heldout.EvaluationError, match="wrong-split"):
        heldout.evaluate_predictions(cases, manifest, [
            {"case_id": train_id, "abstain": True, "labels": []}
        ], split="validation")
    with pytest.raises(heldout.EvaluationError, match="Only ced/resolver/outcome"):
        heldout.evaluate_predictions(cases, manifest, [
            {"case_id": validation_id, "abstain": False, "labels": [{
                "ced": "camera.cut", "resolver": "native", "outcome": "CONVERTED",
                "parameters": {"shell": "unsafe"}
            }]}
        ], split="validation")


def test_manifest_tampering_and_later_corpus_must_fail():
    cases = corpus()
    manifest = heldout.build_manifest(cases)
    changed = copy.deepcopy(manifest)
    changed["splits"]["train"]["case_ids"] = []
    with pytest.raises(heldout.EvaluationError, match="manifest"):
        heldout.retrieval_predictions(cases, changed, split="holdout")
    with pytest.raises(heldout.EvaluationError, match="dataset"):
        heldout.retrieval_predictions(cases + [approved("another")], manifest, split="holdout")


def test_rejects_leaked_partitions_even_if_manifest_hash_recomputed():
    cases = corpus()
    manifest = heldout.build_manifest(cases)
    forged = copy.deepcopy(manifest)
    forged["splits"]["train"]["project_fingerprints"] = list(
        forged["splits"]["validation"]["project_fingerprints"]
    )
    forged["manifest_sha256"] = heldout._digest({
        k: v for k, v in forged.items() if k != "manifest_sha256"
    })
    with pytest.raises(heldout.EvaluationError, match="misassigned|leakage"):
        heldout.retrieval_predictions(cases, forged, split="holdout")


def test_prediction_jsonl_is_restricted_and_reports_are_immutable(tmp_path):
    p = tmp_path / "predictions.jsonl"
    p.write_text(json.dumps({
        "case_id": "a", "abstain": True, "labels": []
    }) + "\n")
    assert heldout.load_predictions(p)[0]["abstain"] is True
    out = tmp_path / "report.json"
    heldout.write_new(out, {"release_authorized": False})
    with pytest.raises(FileExistsError):
        heldout.write_new(out, {"release_authorized": True})
