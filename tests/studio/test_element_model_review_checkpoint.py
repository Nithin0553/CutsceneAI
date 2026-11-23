"""Element 3.2 durable, source-bound, redacted model-page replay."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
for name in ("studio", "ced"):
    sys.path.insert(0, str(ROOT / "packages" / name))

import ced_agent_knowledge as ced
import studio_element_plan as elements
import studio_element_review_checkpoint as checkpoints


def _scenario(count: int = 26):
    scene = {"cutscene_id": "PRIVATE_MASTER_SEQUENCE", "entities": [
        {"entity_id": f"PRIVATE_CAMERA_{i}", "ced_type": "entity.camera"}
        for i in range(count)
    ]}
    caps = {"cine_camera_actor": True}
    knowledge = ced.retrieve_all(scene, target_capabilities=caps)
    return scene, knowledge, caps, elements.prepare(scene, knowledge, caps)


class Model:
    def __init__(self):
        self.calls = []

    def complete_json(self, **kwargs):
        payload = kwargs["payload"]
        self.calls.append(payload["page_index"])
        return SimpleNamespace(
            answer={"choices": [
                {"occurrence_id": row["occurrence_id"],
                 "action": row["candidate_actions"][0]
                 if row["candidate_actions"] else "report_only"}
                for row in payload["elements"]
            ]},
            response_sha256="c" * 64,
        )


def test_checkpoint_resumes_from_first_missing_page_without_repeating_calls(tmp_path):
    source, knowledge, caps, plan = _scenario()
    path = tmp_path / "review.json"
    first = Model()
    with pytest.raises(elements.ElementPlanError, match="resumable"):
        elements.review_with_model(
            plan, provider=first, checkpoint_path=path,
            model_identity="ollama/qwen2.5:7b-instruct", max_new_pages=1,
        )
    assert first.calls == [0]
    assert path.is_file()
    assert not (tmp_path / "review.json.lock").exists()
    checkpoint_body = path.read_text(encoding="utf-8")
    assert "PRIVATE_MASTER_SEQUENCE" not in checkpoint_body
    assert "PRIVATE_CAMERA" not in checkpoint_body
    resumed = Model()
    reviewed, hashes = elements.review_with_model(
        plan, provider=resumed, checkpoint_path=path,
        model_identity="ollama/qwen2.5:7b-instruct", max_new_pages=2,
    )
    assert resumed.calls == [1, 2]
    assert hashes == ["c" * 64] * 3
    assert reviewed["model_reviewed_count"] == 26
    elements.verify(reviewed, source, knowledge, caps)
    fully_cached = Model()
    again, cached_hashes = elements.review_with_model(
        plan, provider=fully_cached, checkpoint_path=path,
        model_identity="ollama/qwen2.5:7b-instruct", max_new_pages=1,
    )
    assert fully_cached.calls == []
    assert cached_hashes == hashes
    assert again == reviewed


def test_checkpoint_rejects_stale_source_or_model_identity(tmp_path):
    _, _, _, plan = _scenario(13)
    path = tmp_path / "review.json"
    elements.review_with_model(
        plan, provider=Model(), checkpoint_path=path,
        model_identity="ollama/model-a",
    )
    with pytest.raises(checkpoints.CheckpointError, match="match"):
        elements.review_with_model(
            plan, provider=Model(), checkpoint_path=path,
            model_identity="ollama/model-b",
        )
    _, _, _, changed_plan = _scenario(14)
    with pytest.raises(checkpoints.CheckpointError, match="match"):
        elements.review_with_model(
            changed_plan, provider=Model(), checkpoint_path=path,
            model_identity="ollama/model-a",
        )


def test_checkpoint_replay_revalidates_actions_not_only_recomputed_checksum(tmp_path):
    _, _, _, plan = _scenario(13)
    path = tmp_path / "review.json"
    elements.review_with_model(
        plan, provider=Model(), checkpoint_path=path,
        model_identity="ollama/model-a",
    )
    forged = json.loads(path.read_text(encoding="utf-8"))
    forged["pages"][0]["choices"][0]["action"] = "destroy_all_unreal_assets"
    forged["pages"][0]["answer_sha256"] = checkpoints._digest({
        "choices": forged["pages"][0]["choices"]
    })
    forged["checkpoint_sha256"] = checkpoints._digest({
        k: v for k, v in forged.items() if k != "checkpoint_sha256"
    })
    path.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(elements.ElementPlanError, match="unregistered"):
        elements.review_with_model(
            plan, provider=Model(), checkpoint_path=path,
            model_identity="ollama/model-a",
        )


def test_checkpoint_exclusive_lock_fails_closed(tmp_path):
    _, _, _, plan = _scenario(13)
    path = tmp_path / "review.json"
    lock = tmp_path / "review.json.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with pytest.raises(checkpoints.CheckpointError, match="Another review"):
            elements.review_with_model(
                plan, provider=Model(), checkpoint_path=path,
                model_identity="ollama/model-a",
            )
    finally:
        os.close(fd)
        lock.unlink()


def test_graph_blocker_disallows_proposed_native_choice(tmp_path):
    _, _, _, plan = _scenario(13)
    blocked = plan["elements"][0]["occurrence_id"]
    class MaliciousModel(Model):
        def complete_json(self, **kwargs):
            result = super().complete_json(**kwargs)
            result.answer["choices"][0]["action"] = "camera_setup"
            return result

    model = MaliciousModel()
    with pytest.raises(elements.ElementPlanError, match="blocked"):
        elements.review_with_model(
            plan, provider=model,
            blocked_occurrences={blocked: "OWNERSHIP_CONFLICT"},
            checkpoint_path=tmp_path / "review.json",
            model_identity="ollama/model-a",
        )
    assert model.calls == [0]
    assert not (tmp_path / "review.json").exists()
