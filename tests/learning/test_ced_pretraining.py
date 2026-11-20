"""CED pretraining uses the full taxonomy without inventing native success."""
from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "learning"))

import ced_pretraining as trainer


@pytest.fixture(scope="module")
def trained():
    return trainer.train()


def test_ced_vocabulary_is_actually_fitted_with_all_735_concepts(trained):
    assert trained["kind"] == trainer.MODEL_KIND
    assert trained["stats"]["ced_concepts"] == 735
    assert trained["stats"]["ced_categories"] == 63
    assert trained["stats"]["registered_rule_examples"] == 5
    assert trained["stats"]["independent_native_reward_examples"] == 0
    assert len(trained["concept_vectors"]) == 735
    assert len(trained["idf"]) > 100
    assert all(abs(sum(weight * weight for weight in vec.values()) - 1) < 1e-6
               for vec in trained["concept_vectors"].values())
    assert trained["native_conversion_authorized"] is False
    assert trained["trained_on_real_unreal_rewards"] is False


def test_zero_shot_alias_evaluation_is_not_mistaken_for_native_fidelity(trained):
    quality = trained["evaluation"]
    assert quality["method"] == "CED_ONLY_ZERO_SHOT_NATIVE_ALIAS_RETRIEVAL"
    assert quality["alias_holdout_count"] >= 15
    assert 0 <= quality["top1_hits"] <= quality["top3_hits"]
    assert quality["top3_hits"] <= quality["alias_holdout_count"]
    assert quality["accuracy_is_not_native_conversion_success"] is True


def test_training_uses_real_preflight_refusals_not_just_ced_names(trained):
    assert trained["stats"]["preflight_domain_labels"] >= 20
    assert trained["stats"]["preflight_partial_or_unsupported_labels"] >= 8
    assert trained["preflight_capability_states"]["tracks"]["event.state"] == (
        "KNOWN_UNSUPPORTED")
    assert trained["preflight_capability_states"]["tracks"]["audio.track"] == (
        "KNOWN_PARTIAL")
    assert trained["preflight_capability_states"]["tracks"]["animation.track"] == (
        "SUPPORTED_UNVERIFIED")
    matched = trainer.suggest(trained,
                              "UnityEngine.Timeline.AnimationPlayableAsset",
                              engine="unity")
    assert matched[0]["ced"] == "animation.section"
    assert matched[0]["preflight_states"]["sections"] == "SUPPORTED_UNVERIFIED"
    assert matched[0]["native_conversion_authorized"] is False


def test_trained_mapping_cannot_forge_unsupported_to_supported(trained):
    forged = copy.deepcopy(trained)
    forged["preflight_capability_states"]["tracks"]["event.state"] = (
        "SUPPORTED_UNVERIFIED")
    forged["payload_sha256"] = trainer._sha({
        key: value for key, value in forged.items() if key != "payload_sha256"})
    with pytest.raises(trainer.CEDPretrainingError, match="reproduce"):
        trainer.validate(forged)


def test_approved_rule_associations_are_restricted_to_registered_ids(trained):
    assert trained["registered_rule_ids"]["transform.rotation"] == [
        "unity-unreal-transform-rotation-semantic-fields"]
    assert "character.quadruped" not in trained["registered_rule_ids"]
    for ids in trained["registered_rule_ids"].values():
        assert all(rule_id.startswith("unity-unreal-") for rule_id in ids)


def test_exact_native_aliases_are_not_native_conversion_authorizations(trained):
    matches = trainer.suggest(trained, "TimelineAsset", engine="unity")
    assert matches[0]["ced"] == "sequence.root"
    assert matches[0]["match"] == "DRAFT_NATIVE_ALIAS"
    assert matches[0]["native_conversion_authorized"] is False
    target = trainer.suggest(trained, "CineCameraActor", engine="unreal")
    assert target[0]["ced"] == "entity.camera"
    assert target[0]["match"] == "DRAFT_NATIVE_ALIAS"
    assert target[0]["native_conversion_authorized"] is False
    assert trainer.suggest(trained, "ZZZImpossibleUnknownNative", engine="unity") == []


def test_pretraining_is_reproducible_and_tamper_proof(trained):
    assert trainer.train() == trained
    trainer.validate(trained)
    modified = copy.deepcopy(trained)
    modified["concept_vectors"]["camera.fov"]["camera"] = 1
    with pytest.raises(trainer.CEDPretrainingError, match="modified"):
        trainer.validate(modified)
    modified = copy.deepcopy(trained)
    modified["native_conversion_authorized"] = True
    modified["payload_sha256"] = trainer._sha({
        key: value for key, value in modified.items() if key != "payload_sha256"})
    with pytest.raises(trainer.CEDPretrainingError, match="authorize"):
        trainer.validate(modified)


def test_pretraining_blocks_unknown_ced_in_native_dictionary():
    inputs, hashes = trainer.read_sources()
    inputs["unity"]["mappings"][0]["ced"] = "unknown.not_in_ced"
    with pytest.raises(trainer.CEDPretrainingError, match="Unknown CED"):
        trainer.fit(inputs, input_hashes=hashes)


def test_pretraining_blocks_stale_source_hash(tmp_path, trained):
    source = trainer.CONTRACT_DIR
    for filename in trainer.SOURCES.values():
        (tmp_path / filename).write_bytes((source / filename).read_bytes())
    path = tmp_path / trainer.SOURCES["ced"]
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(trainer.CEDPretrainingError, match="stale"):
        trainer.validate(trained, folder=tmp_path)


def test_unknown_engine_and_oversized_or_empty_queries_fail_closed(trained):
    with pytest.raises(trainer.CEDPretrainingError, match="scope"):
        trainer.suggest(trained, "TimelineAsset", engine="godot")
    with pytest.raises(trainer.CEDPretrainingError, match="empty"):
        trainer.suggest(trained, " ", engine="unity")
    with pytest.raises(trainer.CEDPretrainingError, match="bounded"):
        trainer.suggest(trained, "A" * 500, engine="unreal")


def test_cli_generates_real_versioned_model_and_refuses_overwrite(tmp_path):
    model = tmp_path / "ced-model.json"
    report = tmp_path / "ced-training-report.json"
    command = [
        sys.executable, str(ROOT / "tools" / "train_ced_policy.py"),
        "train", "--output", str(model), "--summary", str(report),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    trained = json.loads(model.read_text(encoding="utf-8"))
    summary = json.loads(report.read_text(encoding="utf-8"))
    assert trainer.validate(trained) is trained
    assert summary["model_payload_sha256"] == trained["payload_sha256"]
    assert summary["trained_native_reinforcement_policy"] is False
    verify = subprocess.run([
        sys.executable, str(ROOT / "tools" / "train_ced_policy.py"),
        "verify", "--model", str(model),
    ], capture_output=True, text=True, check=False)
    assert verify.returncode == 0, verify.stderr
    suggestion = subprocess.run([
        sys.executable, str(ROOT / "tools" / "train_ced_policy.py"),
        "suggest", "--model", str(model), "--engine", "unity",
        "--native-name", "TimelineAsset",
    ], capture_output=True, text=True, check=False)
    assert suggestion.returncode == 0, suggestion.stderr
    assert json.loads(suggestion.stdout)["suggestions"][0]["ced"] == "sequence.root"
    rerun = subprocess.run(command, capture_output=True, text=True, check=False)
    assert rerun.returncode == 2
    assert "overwrite" in rerun.stderr
