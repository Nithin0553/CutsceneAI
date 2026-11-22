"""Element 4: real source-bound validation decisions and bounded alternatives.

The model and engines are mocked; no simulated native action is called
a real Unity/Unreal execution or full cinematic fidelity.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
for folder in ("packages/studio", "tools", "tests/studio"):
    sys.path.insert(0, str(ROOT / folder))

import studio_element4_validation as gate
import studio_element_investigation as investigations
import studio_element_plan as plans
import studio_element_schedule as schedules
import studio_element_strategy as adaptive
from test_element_adaptive_strategy import _evidence

ALLOWED = ["native_source", "source_materials"]


def _bound(*, plan=None):
    scene, knowledge, caps, original, _schedule, _strategy = _evidence()
    selected = plan if plan is not None else original
    schedule = schedules.build(selected, scene)
    strategy = adaptive.build(selected, schedule, knowledge, scene, caps)
    cases = investigations.build(selected, schedule, strategy, knowledge, scene, caps)
    return scene, knowledge, caps, selected, schedule, strategy, cases


def _gate(case, **kwargs):
    scene, knowledge, caps, plan, schedule, strategy, cases = case
    return gate.build(
        plan, schedule, strategy, cases, knowledge, scene, caps,
        global_strategy=kwargs.get("global_strategy", "native_source"),
        allowed_strategies=kwargs.get("allowed_strategies", ALLOWED),
    )


def _select(plan, location, action):
    ident = next(row["occurrence_id"] for row in plan["elements"]
                 if row["source_location"] == location)
    return plans.apply_choices(plan, [
        {"occurrence_id": ident, "action": action},
    ], expected_ids=[ident])


def test_all_source_occurrences_are_validated_without_invented_conversion():
    case = _bound()
    report = _gate(case)
    assert report["accepted_for_source_bound_plan"] is True
    assert report["validation_status"] == "VALIDATED_WITH_REPORTED_LIMITATIONS"
    assert report["reported_limitation_count"] == case[3]["source_occurrence_count"]
    assert report["validated_candidate_count"] == 0
    assert report["rejections"] == []
    assert all(item["validation"] == "LIMITATION_RECORDED" for item in report["decisions"])
    assert report["native_execution_authorized"] is False
    assert report["full_cutscene_fidelity_verified"] is False
    gate.verify(
        report, case[3], case[4], case[5], case[6],
        case[1], case[0], case[2],
        global_strategy="native_source", allowed_strategies=ALLOWED,
    )
    payload = json.dumps(report)
    for secret in ("PRIVATE_", "PrivateCompany", "CLASSIFIED", "SECRET_MODEL"):
        assert secret not in payload


def test_source_bound_camera_action_can_be_validated_without_native_authorization():
    case = _bound()
    updated = _select(case[3], "entities[2]", "camera_setup")
    case = _bound(plan=updated)
    report = _gate(case)
    assert report["accepted_for_source_bound_plan"] is True
    assert report["validated_candidate_count"] == 1
    assert report["reported_limitation_count"] == updated["source_occurrence_count"] - 1
    assert report["validation_status"] == "VALIDATED_WITH_REPORTED_LIMITATIONS"
    assert report["native_execution_authorized"] is False
    assert all(not row["native_execution_verified"] for row in report["decisions"])


def test_selected_action_with_unplanned_parent_rejected_by_final_graph_gate():
    case = _bound()
    updated = _select(case[3], "tracks[0]", "skeletal_animation")
    case = _bound(plan=updated)
    report = _gate(case)
    problem, = report["rejections"]
    assert problem["reason_code"] == gate.REASON_BLOCKED
    assert problem["allowed_alternatives"] == ["report_only"]
    assert report["validation_status"] == "REJECTED_BOUNDED_ALTERNATIVE_REQUIRED"
    assert report["accepted_for_source_bound_plan"] is False
    assert report["rejected_count"] == 1
    assert report["native_execution_authorized"] is False


class SafeAlternatives:
    def __init__(self, *, action="report_only", malicious=False):
        self.calls = []
        self.action = action
        self.malicious = malicious

    def complete_json(self, **kwargs):
        assert kwargs["task"] == "cutsceneai_element4_bounded_alternatives"
        payload = kwargs["payload"]
        self.calls.append(copy.deepcopy(payload))
        choices = [
            {"occurrence_id": row["occurrence_id"], "action": self.action}
            for row in payload["rejected"]
        ]
        if self.malicious:
            choices[0]["python"] = "import unreal; delete_all_assets()"
        return SimpleNamespace(answer={"choices": choices},
                               response_sha256="c" * 64)


def test_bounded_reasoner_returns_only_to_source_plan_after_revalidation():
    case = _bound()
    changed = _select(case[3], "tracks[0]", "skeletal_animation")
    agent = SafeAlternatives()
    reviewed, dep, cmp, cases, result, audit = gate.reason_bounded(
        changed, case[1], case[0], case[2],
        global_strategy="native_source", allowed_strategies=ALLOWED,
        provider=agent,
    )
    assert len(agent.calls) == 1
    assert agent.calls[0]["rejected"][0]["allowed_alternatives"] == ["report_only"]
    assert reviewed["model_reviewed_count"] == 1
    assert reviewed["elements"][5]["selected_action"] == "report_only"
    assert result["accepted_for_source_bound_plan"] is True
    assert result["validation_status"] == "VALIDATED_WITH_REPORTED_LIMITATIONS"
    assert len(audit) == 1
    assert audit[0]["validated_replacement_count"] == 1
    assert audit[0]["responses"][0]["response_sha256"] == "c" * 64
    assert audit[0]["native_execution_authorized"] is False
    gate.verify(
        result, reviewed, dep, cmp, cases, case[1], case[0], case[2],
        global_strategy="native_source", allowed_strategies=ALLOWED,
    )
    payload = json.dumps(agent.calls)
    for secret in ("PRIVATE_", "PrivateCompany", "CLASSIFIED", "SECRET_MODEL"):
        assert secret not in payload


def test_absent_budget_or_no_progress_never_executes_or_overrides_plan():
    case = _bound()
    changed = _select(case[3], "tracks[0]", "skeletal_animation")
    with pytest.raises(gate.StrategyValidationError, match="exhausted"):
        gate.reason_bounded(
            changed, case[1], case[0], case[2],
            global_strategy="native_source", allowed_strategies=ALLOWED,
            provider=SafeAlternatives(), max_rounds=0,
        )
    unsafe = SafeAlternatives(action="skeletal_animation")
    with pytest.raises(gate.StrategyValidationError, match="prohibited"):
        gate.reason_bounded(
            changed, case[1], case[0], case[2],
            global_strategy="native_source", allowed_strategies=ALLOWED,
            provider=unsafe,
        )
    assert len(unsafe.calls) == 1
    assert changed["elements"][5]["selected_action"] == "skeletal_animation"


def test_malicious_or_malformed_model_choice_fails_closed():
    case = _bound()
    changed = _select(case[3], "tracks[0]", "skeletal_animation")
    with pytest.raises(gate.StrategyValidationError, match="unregistered fields"):
        gate.reason_bounded(
            changed, case[1], case[0], case[2],
            global_strategy="native_source", allowed_strategies=ALLOWED,
            provider=SafeAlternatives(malicious=True),
        )
    class RejectedModel:
        def complete_json(self, **_kwargs):
            return SimpleNamespace(answer={"choices": []},
                                   response_sha256="d" * 64)
    with pytest.raises(gate.StrategyValidationError, match="provenance"):
        gate.reason_bounded(
            changed, case[1], case[0], case[2],
            global_strategy="native_source", allowed_strategies=ALLOWED,
            provider=RejectedModel(),
        )


def test_forged_selected_action_or_rehashed_gate_never_validates():
    case = _bound()
    report = _gate(case)
    tampered = copy.deepcopy(report)
    tampered["decisions"][0]["validation"] = "ADVISORY_NATIVE_PREFLIGHT_REQUIRED"
    tampered.pop("validation_sha256")
    tampered["validation_sha256"] = plans._digest(tampered)
    with pytest.raises(gate.StrategyValidationError, match="modified"):
        gate.verify(
            tampered, case[3], case[4], case[5], case[6],
            case[1], case[0], case[2],
            global_strategy="native_source", allowed_strategies=ALLOWED,
        )
    faked = copy.deepcopy(case[5])
    faked["comparisons"][0]["alternatives"] = []
    faked.pop("comparison_sha256")
    faked["comparison_sha256"] = plans._digest(faked)
    broken = (case[0], case[1], case[2], case[3], case[4], faked, case[6])
    with pytest.raises(gate.StrategyValidationError, match="forged"):
        _gate(broken)


def test_global_strategy_must_be_explicit_and_cannot_grant_native_execution():
    case = _bound()
    with pytest.raises(gate.StrategyValidationError, match="allowed"):
        _gate(case, global_strategy="run_arbitrary_python")
    with pytest.raises(gate.StrategyValidationError, match="allowed"):
        _gate(case, allowed_strategies=["native_source", "native_source"])
    assert _gate(case)["full_cutscene_fidelity_verified"] is False
