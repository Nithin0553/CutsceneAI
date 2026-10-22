"""The model must learn only validated human-reviewed rules, not its own guesses."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "learning"))

import case_memory


def csir(*, camera=False, group="unity-project-a"):
    tracks = [{
        "ced_type": "animation.track", "name": "Animated Item",
        "sections": [{"ced_type": "animation.section",
                      "payload": {"animation": {"curves": [
                          {"canonical_semantic": "transform.position.x"},
                          {"canonical_semantic": "transform.rotation.w"},
                      ]}}}],
    }]
    if camera:
        tracks.append({"ced_type": "camera.cut", "sections": [
            {"ced_type": "camera.cut", "payload": {}}]})
    return {
        "source": {"engine": "unity", "project_fingerprint": group},
        "cutscene_id": "unity-cutscene-" + group,
        "entities": [{"ced_type": "entity.prop", "name": "Item"}],
        "tracks": tracks,
    }


def mapping():
    return {"entities": {"Item": {"actor_label": "ItemActor"}},
            "assets": {}, "sequence_asset_path": "/Game/Tests/Sequence"}


def resolved(*, valid=True):
    return {"version": "0.1.0", "entries": [
        {"ced": "transform.rotation", "status": "RESOLVED" if valid else "NEEDS_EVIDENCE",
         "outcome": "CONVERTED", "resolver": "canonical.rotation.to_unreal",
         "parameters": {"semantic_fields": True}},
    ]}


def validation(*, passed=True):
    return {"status": "PASS" if passed else "FAIL",
            "summary": {"passed": 1 if passed else 0, "failed": 0 if passed else 1,
                        "incomplete": 0},
            "checks": [{"status": "PASS" if passed else "FAIL",
                        "id": "spatial.rotation", "domain": "SPATIAL"}]}


def review(source, target, *, approved=True, decision=None, report=None):
    return {
        "approve_mapping_examples": approved,
        "reviewer": "human-verifier",
        "source_sha256": case_memory._digest(source),
        "mapping_sha256": case_memory._digest(target),
        "resolved_sha256": case_memory._digest(decision or resolved()),
        "validation_sha256": case_memory._digest(report or validation()),
    }


def checked_case(*, group="unity-project-a", camera=False):
    source = csir(camera=camera, group=group)
    target = mapping()
    return case_memory.build_case(
        source, target, resolved(), validation=validation(),
        review=review(source, target),
    )


def test_pass_validation_without_review_does_not_become_training_label():
    source = csir()
    example = case_memory.build_case(
        source, mapping(), resolved(), validation=validation()
    )
    assert example["status"] == "CANDIDATE"
    assert example["structural_validation_pass"] is True
    assert example["review_approved"] is False


def test_failed_validation_stays_diagnostic_even_with_human_approval():
    source = csir()
    target = mapping()
    example = case_memory.build_case(
        source, target, resolved(), validation=validation(passed=False),
        review=review(source, target, report=validation(passed=False)),
    )
    assert example["status"] == "DIAGNOSTIC_ONLY"
    assert example["fidelity_scope"] == "MAPPING_RULES_ONLY_NOT_FULL_CUTSCENE_PARITY"


def test_wrong_review_hash_must_not_poison_memory():
    source = csir()
    target = mapping()
    signed = review(source, target)
    signed["mapping_sha256"] = "wrong"
    example = case_memory.build_case(
        source, target, resolved(), validation=validation(), review=signed
    )
    assert example["status"] == "CANDIDATE"
    assert example["review_approved"] is False


def test_unresolved_mapping_decisions_cannot_be_trained():
    source = csir()
    target = mapping()
    example = case_memory.build_case(
        source, target, resolved(valid=False),
        validation=validation(), review=review(source, target, decision=resolved(valid=False)),
    )
    assert example["status"] == "CANDIDATE"
    assert example["review_approved"] is True
    assert example["unresolved_decisions"] == 1
    assert example["mapping_labels"] == []


def test_verified_mapping_is_eligible_but_not_claimed_as_full_fidelity():
    example = checked_case()
    assert example["status"] == "MAPPING_VERIFIED"
    assert len(example["mapping_labels"]) == 1
    assert example["fidelity_scope"] == "MAPPING_RULES_ONLY_NOT_FULL_CUTSCENE_PARITY"
    assert "curve:transform.position.x" in example["features"]


def test_similar_cutscenes_retrieve_only_verified_proposals():
    verified = checked_case(group="unity-project-a", camera=True)
    source = csir(group="unity-project-new", camera=True)
    unverified = case_memory.build_case(csir(), mapping(), resolved())
    results = case_memory.suggest(source, [unverified, verified])
    assert len(results) == 1
    assert results[0]["case_id"] == verified["case_id"]
    assert results[0]["proposal_only"] is True
    assert results[0]["fidelity_verified"] is False
    assert results[0]["similarity"] == 1.0


def test_previous_project_can_be_excluded_for_holdout_testing():
    verified = checked_case()
    assert case_memory.suggest(
        csir(), [verified], exclude_project_fingerprint="unity-project-a"
    ) == []


def test_a_case_id_is_immutable_and_duplicate_safe(tmp_path):
    example = checked_case()
    path = case_memory.save_case(example, tmp_path)
    assert case_memory.save_case(example, tmp_path) == path
    assert len(case_memory.list_cases(tmp_path)) == 1
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(case_memory.LearningDataError, match="conflicting content"):
        case_memory.save_case(example, tmp_path)


def test_only_verified_examples_export_to_supervised_dataset(tmp_path):
    verified = checked_case()
    candidate = case_memory.build_case(csir(group="candidate-project"), mapping(), resolved())
    exported = tmp_path / "train.jsonl"
    n = case_memory.export_training_jsonl([candidate, verified], exported)
    assert n == 1
    data = case_memory.read_json  # exercise supported public API independently
    import json

    row = json.loads(exported.read_text(encoding="utf-8").strip())
    assert row["group_id"] == "unity-project-a"
    assert row["task"] == "suggest_ced_transfer_mapping"
    assert row["scope"] == "mapping_only"
    assert row["target"][0]["resolver"] == "canonical.rotation.to_unreal"
    assert callable(data)
    with pytest.raises(case_memory.LearningDataError, match="overwrite"):
        case_memory.export_training_jsonl([verified], exported)


def test_same_cutscene_project_group_required_for_learning():
    source = csir(group="")
    source["source"].pop("project_fingerprint")
    target = mapping()
    case = case_memory.build_case(
        source, target, resolved(), validation=validation(),
        review=review(source, target)
    )
    assert case["status"] == "CANDIDATE"


def test_muted_tracks_excluded_from_feature_learning():
    source = csir()
    source["tracks"][0]["muted"] = True
    features = case_memory._track_features(source)
    assert "track:animation.track" not in features["features"]
    assert features["track_counts"] == {}



def test_learning_health_requires_independent_project_groups():
    first = checked_case(group="project-x")
    another_scene_same_project = checked_case(group="project-x", camera=True)
    same_project = case_memory.dataset_health([first, another_scene_same_project])
    assert same_project["verified_cases"] == 2
    assert same_project["distinct_source_projects"] == 1
    assert same_project["independent_project_holdout_possible"] is False
    assert same_project["recommendation"] == "COLLECT_INDEPENDENT_PROJECTS"

    truly_separate_project = checked_case(group="project-y")
    independent = case_memory.dataset_health([first, truly_separate_project])
    assert independent["distinct_source_projects"] == 2
    assert independent["independent_project_holdout_possible"] is True
    assert independent["model_finetuning_performed"] is False
