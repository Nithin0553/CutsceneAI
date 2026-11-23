"""Element 3.4 exact-source, non-executable autonomous investigation tests."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
for directory in ("studio", "ced"):
    sys.path.insert(0, str(ROOT / "packages" / directory))

import ced_agent_knowledge as ced
import studio_element_investigation as investigator
import studio_element_plan as elements
import studio_element_schedule as scheduler
import studio_element_strategy as adaptive


def _time(ticks: int) -> dict:
    return {"value": ticks, "rate": {"numerator": 24, "denominator": 1}}


def _scene():
    return {
        "cutscene_id": "PRIVATE_PRODUCTION_SCENE",
        "source": {"engine": "unity", "engine_version": "6000.3"},
        "assets": [{"asset_id": "PRIVATE-CHAR-ASSET", "ced_type": "asset.model",
                    "name": "PRIVATE_BONE_MESH"}],
        "entities": [
            {"entity_id": "PRIVATE_ROOT", "ced_type": "entity.prop"},
            {"entity_id": "PRIVATE_ACTOR", "ced_type": "entity.character",
             "parent_entity_id": "PRIVATE_ROOT", "asset_id": "PRIVATE-CHAR-ASSET"},
            {"entity_id": "PRIVATE_CAMERA", "ced_type": "entity.camera"},
            {"entity_id": "PRIVATE_VENDOR", "ced_type": "PrivateCompany.SecretRig"},
        ],
        "tracks": [
            {"track_id": "PRIVATE_ANIMATION", "ced_type": "animation.track",
             "binding_entity_id": "PRIVATE_ACTOR", "sections": [{
                 "section_id": "PRIVATE_CLIP", "ced_type": "animation.section",
                 "start": _time(0), "end": _time(24), "payload": {},
             }]},
            {"track_id": "PRIVATE_SHOT", "ced_type": "camera.transform",
             "binding_entity_id": "PRIVATE_CAMERA", "sections": [{
                 "section_id": "PRIVATE_CAMERA_SECTION", "ced_type": "camera.fov",
                 "start": _time(0), "end": _time(24), "payload": {},
             }]},
        ],
        "relationships": [],
    }


def _evidence(source=None, caps=None):
    scene = source if source is not None else _scene()
    observed = caps if caps is not None else {
        "cine_camera_actor": True, "fbx_asset_import": True,
        "sequencer_skeletal_animation_track": True,
        "sequencer_visibility_track": True,
    }
    knowledge = ced.retrieve_all(
        scene, target_capabilities=observed,
        source_version="6000.3", target_version="5.8",
    )
    plan = elements.prepare(scene, knowledge, observed)
    schedule = scheduler.build(plan, scene)
    strategy = adaptive.build(plan, schedule, knowledge, scene, observed)
    report = investigator.build(plan, schedule, strategy, knowledge, scene, observed)
    return scene, knowledge, observed, plan, schedule, strategy, report


def _find(report, plan, location):
    identifier = next(item["occurrence_id"] for item in plan["elements"]
                      if item["source_location"] == location)
    return next(item for item in report["findings"]
                if item["occurrence_id"] == identifier)


def _verify(report, data):
    scene, knowledge, caps, plan, schedule, strategy, _ = data
    investigator.verify(report, plan, schedule, strategy, knowledge, scene, caps)


def test_every_source_occurrence_is_diagnosed_without_leaking_source_identifiers():
    data = _evidence()
    _, _, _, plan, _, _, report = data
    assert len(report["findings"]) == report["source_occurrence_count"]
    assert report["source_occurrence_count"] == plan["source_occurrence_count"]
    assert len({item["occurrence_id"] for item in report["findings"]}) == len(
        report["findings"])
    assert report["model_reviewed_count"] == 0
    assert report["native_execution_authorized"] is False
    assert report["source_and_target_fidelity_verified"] is False
    assert all(item["selected_step"] == "report_only" and
               item["model_reviewed"] is False for item in report["findings"])
    assert all(item["native_execution_authorized"] is False
               and item["current_cutscene_fidelity_verified"] is False
               for item in report["findings"])
    text = json.dumps(report)
    for secret in ("PRIVATE_", "PrivateCompany", "PRIVATE_PRODUCTION_SCENE",
                   "PRIVATE_BONE_MESH", "PRIVATE-CHAR-ASSET"):
        assert secret not in text
    _verify(report, data)


def test_unknown_semantic_stays_unknown_and_never_discovers_nonregistered_action():
    data = _evidence()
    _, _, _, plan, _, _, report = data
    unknown = _find(report, plan, "entities[3]")
    assert unknown["ced"] == "unknown.unclassified"
    assert unknown["state"] == "INVESTIGATION_REQUIRED"
    assert unknown["registered_alternatives"] == []
    assert "UNKNOWN_CED_CONCEPT" in unknown["reason_codes"]
    assert "review_ced_knowledge" in unknown["available_investigation_steps"]
    assert "review_registered_alternatives" not in unknown["available_investigation_steps"]


def test_registered_discovery_uses_only_eligible_character_route():
    data = _evidence()
    _, _, _, plan, _, strategy, report = data
    track = _find(report, plan, "tracks[0]")
    assert track["registered_alternatives"] == ["skeletal_animation"]
    assert "REGISTERED_ALTERNATIVE_NOT_SELECTED" in track["reason_codes"]
    assert "review_registered_alternatives" in track["available_investigation_steps"]
    assert "transform" not in track["registered_alternatives"]
    entry = next(item for item in strategy["comparisons"]
                 if item["occurrence_id"] == track["occurrence_id"])
    assert any(x["action"] == "transform" and
               x["eligible_for_model_proposal"] is False
               for x in entry["alternatives"])


def test_missing_target_capability_is_diagnostic_not_native_fallback():
    data = _evidence(caps={
        "cine_camera_actor": False, "fbx_asset_import": True,
        "sequencer_skeletal_animation_track": True,
    })
    _, _, _, plan, _, _, report = data
    camera = _find(report, plan, "entities[2]")
    assert camera["registered_alternatives"] == []
    assert "TARGET_CAPABILITY_MISSING" in camera["reason_codes"]
    assert "FRESH_UNREAL_CAPABILITY_PROBE" in camera["required_evidence"]
    assert "inspect_target_capabilities" in camera["available_investigation_steps"]
    _verify(report, data)


def test_source_reference_and_cyclic_blockers_never_become_repair_permissions():
    scene = _scene()
    scene["entities"][0]["parent_entity_id"] = "PRIVATE_ACTOR"
    data = _evidence(scene)
    _, _, _, plan, _, _, report = data
    actor = _find(report, plan, "entities[1]")
    root = _find(report, plan, "entities[0]")
    assert root["state"] == actor["state"] == "BLOCKED_SOURCE"
    assert "CYCLIC_SOURCE_RELATIONSHIP" in root["reason_codes"]
    assert "inspect_source_references" in actor["available_investigation_steps"]
    assert root["registered_alternatives"] == actor["registered_alternatives"] == []
    _verify(report, data)


def test_timeline_ownership_conflict_cannot_offer_registered_action_as_executable():
    scene = _scene()
    scene["tracks"].append({
        "track_id": "PRIVATE_SECOND_ANIMATION", "ced_type": "animation.track",
        "binding_entity_id": "PRIVATE_ACTOR", "sections": [{
            "section_id": "PRIVATE_SECOND_CLIP", "ced_type": "animation.section",
            "start": _time(10), "end": _time(30), "payload": {},
        }],
    })
    data = _evidence(scene)
    _, _, _, plan, _, _, report = data
    track = _find(report, plan, "tracks[0]")
    assert track["state"] == "BLOCKED_SOURCE"
    assert "TIMELINE_OWNERSHIP_UNPROVEN" in track["reason_codes"]
    assert "inspect_timeline_ownership" in track["available_investigation_steps"]
    assert track["registered_alternatives"] == []
    assert "SOURCE_TRACK_BINDING_AND_BLEND_TIMING" in track["required_evidence"]
    _verify(report, data)


def test_malicious_diagnostic_actions_and_omissions_are_refused():
    data = _evidence()
    report = data[-1]
    ids = [row["occurrence_id"] for row in report["findings"]]
    choices = [{"occurrence_id": ident, "action": "report_only"} for ident in ids]
    for variant in ("missing", "duplicate", "unknown", "invented", "extra_code"):
        malicious = copy.deepcopy(choices)
        if variant == "missing":
            malicious.pop()
        elif variant == "duplicate":
            malicious[1]["occurrence_id"] = malicious[0]["occurrence_id"]
        elif variant == "unknown":
            malicious[0]["occurrence_id"] = "E99999"
        elif variant == "invented":
            malicious[0]["action"] = "import_unreal_and_create_assets"
        elif variant == "extra_code":
            malicious[0]["python"] = "import unreal"
        with pytest.raises(investigator.ElementInvestigationError):
            investigator.apply_choices(report, malicious, expected_ids=ids)


def test_recomputed_digest_cannot_mask_forged_issues_or_selected_native_command():
    data = _evidence()
    report = data[-1]
    forged = copy.deepcopy(report)
    forged["findings"][0]["registered_alternatives"] = ["destroy_project"]
    forged.pop("investigation_sha256")
    forged["investigation_sha256"] = elements._digest(forged)
    with pytest.raises(investigator.ElementInvestigationError, match="altered"):
        _verify(forged, data)
    source, knowledge, caps, plan, schedule, strategy, _ = data
    source["cutscene_id"] = "DIFFERENT_SOURCE_SNAPSHOT"
    with pytest.raises(investigator.ElementInvestigationError):
        investigator.verify(report, plan, schedule, strategy, knowledge, source, caps)


class _Model:
    def __init__(self):
        self.pages = []

    def complete_json(self, **kwargs):
        assert kwargs["task"] == "cutsceneai_element_investigation_next_step"
        payload = kwargs["payload"]
        self.pages.append(payload["page_index"])
        assert "PRIVATE_" not in json.dumps(payload)
        return SimpleNamespace(answer={"choices": [
            {"occurrence_id": row["occurrence_id"],
             "action": row["available_investigation_steps"][0]
             if row["available_investigation_steps"] else "report_only"}
            for row in payload["cases"]
        ]}, response_sha256="c" * 64)


def _review(report, data, provider, **extra):
    source, knowledge, caps, plan, schedule, strategy, _ = data
    return investigator.review_with_model(
        report, plan=plan, schedule=schedule, strategy=strategy,
        knowledge=knowledge, csir=source, target_capabilities=caps,
        provider=provider, **extra,
    )


def test_model_investigation_covers_all_cases_with_fixed_vocabulary():
    data = _evidence()
    report = data[-1]
    model = _Model()
    reviewed, digests = _review(report, data, model)
    eligible = sum(bool(row["available_investigation_steps"])
                   for row in report["findings"])
    assert reviewed["model_reviewed_count"] == eligible
    assert len(digests) == len(model.pages)
    assert all(row["selected_step"] == "report_only" or
               row["selected_step"] in row["available_investigation_steps"]
               for row in reviewed["findings"])
    _verify(reviewed, data)


def test_resumable_pagination_does_not_replay_model_calls_or_drop_cases(tmp_path):
    source = {"entities": [
        {"entity_id": f"PRIVATE_CAM_{i}", "ced_type": "entity.camera"}
        for i in range(26)
    ]}
    data = _evidence(source)
    report = data[-1]
    checkpoint = tmp_path / "investigation.json"
    first = _Model()
    with pytest.raises(investigator.ElementInvestigationError, match="incomplete"):
        _review(report, data, first, checkpoint_path=checkpoint,
                model_identity="ollama/model-a", max_new_pages=1)
    assert first.pages == [0]
    text = checkpoint.read_text(encoding="utf-8")
    assert "PRIVATE_" not in text
    second = _Model()
    reviewed, digests = _review(
        report, data, second, checkpoint_path=checkpoint,
        model_identity="ollama/model-a", max_new_pages=2,
    )
    assert second.pages == [1, 2]
    assert len(digests) == 3
    assert reviewed["model_reviewed_count"] == 26
    _verify(reviewed, data)
    cached = _Model()
    again, _ = _review(
        report, data, cached, checkpoint_path=checkpoint,
        model_identity="ollama/model-a", max_new_pages=1,
    )
    assert cached.pages == []
    assert again == reviewed


def test_forged_checkpoint_choices_are_rechecked_even_with_recomputed_hash(tmp_path):
    data = _evidence()
    report = data[-1]
    path = tmp_path / "investigation.json"
    _review(report, data, _Model(), checkpoint_path=path, model_identity="local/model")
    from studio_element_review_checkpoint import _digest
    forged = json.loads(path.read_text(encoding="utf-8"))
    forged["pages"][0]["choices"][0]["action"] = "arbitrary_code"
    forged["pages"][0]["answer_sha256"] = _digest({
        "choices": forged["pages"][0]["choices"]
    })
    forged["checkpoint_sha256"] = _digest({
        k: v for k, v in forged.items() if k != "checkpoint_sha256"
    })
    path.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(investigator.ElementInvestigationError, match="unsupported"):
        _review(report, data, _Model(), checkpoint_path=path,
                model_identity="local/model")


def test_large_scene_investigation_covers_full_inventory_without_silent_truncation(tmp_path):
    source = {"entities": [
        {"entity_id": f"private-{i}", "ced_type": "entity.camera"}
        for i in range(270)
    ]}
    data = _evidence(source)
    report = data[-1]
    assert report["source_occurrence_count"] == 270
    model = _Model()
    path = tmp_path / "large.json"
    with pytest.raises(investigator.ElementInvestigationError, match="incomplete"):
        _review(report, data, model, checkpoint_path=path,
                model_identity="ollama/model", max_new_pages=3)
    assert model.pages == [0, 1, 2]
    next_model = _Model()
    reviewed, hashes = _review(
        report, data, next_model, checkpoint_path=path,
        model_identity="ollama/model", max_new_pages=32,
    )
    assert len(hashes) == 23
    assert next_model.pages == list(range(3, 23))
    assert reviewed["model_reviewed_count"] == 270
    _verify(reviewed, data)


def test_model_cannot_choose_an_unlisted_step_even_when_it_is_a_valid_step_elsewhere():
    data = _evidence()
    report = data[-1]
    class _Malicious(_Model):
        def complete_json(self, **kwargs):
            result = super().complete_json(**kwargs)
            result.answer["choices"][0]["action"] = "inspect_timeline_ownership"
            return result
    with pytest.raises(investigator.ElementInvestigationError, match="unsupported"):
        _review(report, data, _Malicious())
