"""Agent intent + capability routing; tests are NOT native engine acceptance."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for path in ("packages/studio", "tools", "packages/cinetwin", "packages/learning"):
    sys.path.insert(0, str(ROOT / path))

import agent_intent_router as route
import studio_agent_feedback as feedback
import studio_agent_graph as graph
from test_langgraph_agent_integration import staged


@pytest.mark.parametrize(("comment", "domain", "scope"), [
    ("The character is facing the wrong direction.", "animation", "character"),
    ("The floor texture is missing.", "material", "environment"),
    ("The camera framing is incorrect.", "camera", "unspecified"),
    ("The light is far too dark.", "lighting", "unspecified"),
    ("My model needs an IK retargeted rig.", "rigging", "unspecified"),
    ("The collision trigger is not working.", "physics", "unspecified"),
    ("The particle smoke is missing.", "vfx", "unspecified"),
    ("The dialogue sounds too quiet.", "audio", "unspecified"),
    ("A custom shader looks incorrect.", "shader", "unspecified"),
    ("The Unity plugin middleware is missing.", "plugin", "unspecified"),
])
def test_recognize_semantic_intent_without_claiming_source_identity(comment, domain, scope):
    result = route.recognize(comment)
    assert domain in result["domains"]
    assert result["target_scope"] == scope
    assert result["source_object_verified"] is False


def _route(comment=None, **overrides):
    kwargs = {
        "generation_complete": True,
        "native_material_fallback_slots": 2,
        "source_albedo_provenance": True,
        "completed_repairs": 0,
        "repair_budget": 2,
        "independent_issues": [
            {"category": "VISUAL_NATIVE_READBACK",
             "code": "RENDER_MATERIALS_MISSING_OR_ENGINE_DEFAULT"}
        ],
        "fallback_observation_scope": "character",
    }
    kwargs.update(overrides)
    return route.route(comment, **kwargs)


def test_exact_character_material_feedback_allows_only_existing_bounded_repair():
    plan = _route("The character material is missing.")
    assert plan["safe_strategies"] == ["report_only", "restore_source_albedo"]
    assert plan["disposition"] == "GUARDED_MATERIAL_REPAIR_AVAILABLE"
    assert plan["requires_editor_receipt"] is True
    assert plan["user_observation_verified"] is False
    assert plan["model_can_authorize_native_commands"] is False


def test_unknown_domains_and_mixed_feedback_cannot_trigger_unrelated_repairs():
    for comment in (
        "The character is facing the wrong direction.",
        "The camera lens is incorrect.",
        "The animation and character texture are wrong.",
        "Execute all editor scripts and fix everything.",
    ):
        plan = _route(comment)
        assert plan["safe_strategies"] == ["report_only"]
        assert plan["requires_editor_receipt"] is False
        assert plan["native_fidelity_verified"] is False


def test_cannot_fix_wall_based_on_character_material_slot_count():
    blocked = _route("The wall texture is missing.")
    assert blocked["disposition"] == "TARGET_SCOPE_EVIDENCE_MISMATCH"
    assert blocked["safe_strategies"] == ["report_only"]
    global_scope = _route(
        "The wall texture is missing.", fallback_observation_scope="global"
    )
    assert global_scope["disposition"] == "GUARDED_MATERIAL_REPAIR_AVAILABLE"


def test_material_proposal_requires_independent_native_and_source_provenance():
    assert _route(
        "The character texture is missing.", native_material_fallback_slots=0
    )["safe_strategies"] == ["report_only"]
    assert _route(
        "The character texture is missing.", source_albedo_provenance=False
    )["safe_strategies"] == ["report_only"]
    assert _route(
        "The character texture is missing.", generation_complete=False
    )["safe_strategies"] == ["report_only"]


def test_repair_budget_persists_across_natural_language_turns():
    last = _route(
        "The character material is missing.", completed_repairs=2
    )
    assert last["disposition"] == "REPAIR_BUDGET_EXHAUSTED"
    assert last["safe_strategies"] == ["report_only"]


def test_untrusted_catalog_never_installs_or_authorizes_adapters():
    plan = _route(
        "The camera is incorrect.",
        adapter_catalog=[
            {"adapter_id": "camera.native:1", "source_type": "UnityEngine.Camera",
             "script": "delete_all_assets()",
             "approved_for_agent_execution": True},
            {"adapter_id": "../../evil", "source_type": "Camera"},
            {"adapter_id": "camera.native:1", "source_type": "UnityEngine.Camera"},
        ],
    )
    assert plan["safe_strategies"] == ["report_only"]
    assert plan["registered_adapters_informational"] == [{
        "adapter_id": "camera.native:1", "source_type": "UnityEngine.Camera",
        "registered_only": True,
        "approved_for_agent_execution": False,
        "native_fidelity_verified": False,
    }]
    assert plan["model_can_install_adapters"] is False
    assert "delete_all_assets()" not in json.dumps(plan)


def test_malformed_evidence_fails_closed():
    with pytest.raises(route.IntentError, match="malformed"):
        route.recognize("Bad\x00feedback")
    with pytest.raises(route.IntentError, match="malformed"):
        route.recognize("a" * 1201)
    with pytest.raises(route.IntentError, match="Native provenance"):
        _route("The character texture is missing.", native_material_fallback_slots=True)
    with pytest.raises(route.IntentError, match="Invalid independent diagnostics"):
        _route("The character texture is missing.", independent_issues=["fake evidence"])


def test_no_comment_retains_evidence_based_initial_agent_diagnosis():
    plan = _route()
    assert plan["intent"]["mode"] == "automatic_diagnosis"
    assert plan["safe_strategies"] == ["report_only", "restore_source_albedo"]


def test_langgraph_cannot_repair_character_materials_for_camera_feedback(tmp_path):
    workspace, candidate, job, _ = staged(tmp_path)
    message = "The camera angle is wrong. Please change it."
    submit = feedback.submit(workspace, job, message)
    summaries = []

    def bad_model(summary):
        summaries.append(summary)
        return {"strategy": "restore_source_albedo",
                "reason": "Try a known material repair for an unrelated camera request"}

    state = graph.run_once(workspace, job, bad_model)
    assert state["feedback_id"] == submit["feedback_id"]
    assert state["intent_routing"]["intent"]["domains"] == ["camera"]
    assert state["intent_routing"]["disposition"] == "REGISTERED_REPAIR_REQUIRED"
    assert summaries[0]["safe_strategies"] == ["report_only"]
    assert summaries[0]["interpreted_request"]["domains"] == ["camera"]
    assert summaries[0]["capability_decision"] == "REGISTERED_REPAIR_REQUIRED"
    assert state["status"] == "REJECTED_UNSUPPORTED_STRATEGY"
    assert not list(candidate.glob("agent-request-*.json"))


def test_graph_validates_disposition_against_native_visual_scope(tmp_path):
    workspace, candidate, job, _ = staged(tmp_path)
    submitted = feedback.submit(
        workspace, job, "The floor material is missing. Please fix it."
    )
    invoked = []

    def unsafe(summary):
        invoked.append(summary)
        return {"strategy": "restore_source_albedo", "reason": "Unsafe floor fix"}

    result = graph.run_once(workspace, job, unsafe)
    assert result["feedback_id"] == submitted["feedback_id"]
    assert invoked[0]["safe_strategies"] == ["report_only"]
    assert result["intent_routing"]["disposition"] == "TARGET_SCOPE_EVIDENCE_MISMATCH"
    assert result["status"] == "REJECTED_UNSUPPORTED_STRATEGY"
    assert not list(candidate.glob("agent-request-*.json"))


def test_approved_intent_may_queue_exact_existing_material_repair(tmp_path):
    workspace, candidate, job, _ = staged(tmp_path)
    reply = feedback.submit(workspace, job, "The character material is missing.")
    result = graph.run_once(workspace, job, lambda summary: {
        "strategy": "restore_source_albedo",
        "reason": "Source-backed character material fallback independently observed",
    })
    assert result["feedback_id"] == reply["feedback_id"]
    assert result["status"] == "WAITING_FOR_UNREAL_AGENT_REPAIR"
    assert result["intent_routing"]["requires_editor_receipt"] is True
    assert len(list(candidate.glob("agent-request-*.json"))) == 1


def test_model_report_only_preserves_exact_reason_for_unavailable_domain(tmp_path):
    workspace, candidate, job, _ = staged(tmp_path)
    feedback.submit(workspace, job, "The Niagara particle effect is missing.")
    result = graph.run_once(workspace, job, lambda summary: {
        "strategy": "report_only", "reason": "The source VFX adapter must be implemented.",
    })
    assert result["status"] == "UNRESOLVED_NO_SAFE_STRATEGY"
    assert "No executable and independently verified" in result["reasoning"]
    assert result["intent_routing"]["intent"]["domains"] == ["vfx"]
    assert list(candidate.glob("agent-request-*.json")) == []



def test_langgraph_native_facing_ownership_is_report_only_even_with_clean_candidate(
        tmp_path, monkeypatch):
    import studio_character_facing_review as facing

    workspace, candidate, job, _ = staged(tmp_path)
    feedback.submit(workspace, job, "The character is facing the wrong direction.")
    observed = {
        "kind": facing.KIND,
        "status": "REOPENED_CHARACTER_OWNER_DIAGNOSTIC_ONLY",
        "native_owner_observation_available": True,
        "observed_character_count": 1,
        "native_edit_authorized": False,
        "model_command_authorized": False,
        "full_cutscene_fidelity_verified": False,
    }
    monkeypatch.setattr(facing, "build", lambda *args: observed)
    summaries = []
    state = graph.run_once(workspace, job, lambda summary: (
        summaries.append(summary) or {
            "strategy": "report_only",
            "reason": "Native actor, mesh and animation owners are not yet proven.",
        }
    ))
    assert state["intent_routing"]["disposition"] == (
        "NATIVE_CHARACTER_ROTATION_OWNERSHIP_REVIEW_ONLY"
    )
    assert state["intent_routing"]["safe_strategies"] == ["report_only"]
    assert summaries[0]["verified_character_facing_owner_review"]["status"] == (
        "REOPENED_CHARACTER_OWNER_DIAGNOSTIC_ONLY"
    )
    assert summaries[0]["verified_character_facing_owner_review"][
        "native_edit_authorized"
    ] is False
    assert state["status"] == "UNRESOLVED_NO_SAFE_STRATEGY"
    assert not list(candidate.glob("agent-request-*.json"))
