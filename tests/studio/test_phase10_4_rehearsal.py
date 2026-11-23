"""Phase 10.4 first synthetic suite/receipt contract; never an editor acceptance."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"tools"))

import phase10_4_rehearse as rehearsal


def _repo(tmp_path):
    root=tmp_path/"studio"
    required = {}
    for _, _, entries in rehearsal.scenario_matrix.SCENARIOS:
        for node in entries:
            source, function = node.split("::", 1)
            required.setdefault(source, set()).add(function)
    for relative in (*rehearsal.TEST_MODULES, rehearsal.NODE_TEST):
        item=root/relative
        item.parent.mkdir(parents=True,exist_ok=True)
        if relative==rehearsal.NODE_TEST:
            names=rehearsal.scenario_matrix.JS_SCENARIOS
            code="\n".join("async function "+name+"(){}" for name in names)
            code+="\nasync function invoke(){\n"
            code+="\n".join("await "+name+"();" for name in names)
            code+="\n}\n"
        else:
            names=sorted(required.get(relative,{"test_fixture_synthetic"}))
            code="\n".join("def "+name+"():\n    assert True\n" for name in names)
        item.write_text(code,encoding="utf-8")
    return root


def test_phase10_4_executes_bounded_python_and_node_rehearsals(tmp_path):
    repo=_repo(tmp_path)
    calls=[]
    exact_nodes={
        entry for _,_,cases in rehearsal.scenario_matrix.SCENARIOS
        for entry in cases
    }
    def runner(cmd,**kwargs):
        calls.append((cmd,kwargs))
        return SimpleNamespace(returncode=0,stdout=(
            "\n".join(node+" PASSED [100%]" for node in sorted(exact_nodes))+
            "\n37 passed, 2 skipped" if len(calls)==1 else
            "Cinematic + advanced UI backend contract: 25 scenarios passed"
        ),stderr="")
    path=tmp_path/"rehearsal.json"
    report=rehearsal.run(repo,output=path,runner=runner)
    assert report["status"]=="SYNTHETIC_REHEARSAL_PASSED_ENGINE_ACCEPTANCE_PENDING"
    assert len(report["plan"]["stage_and_interruption_gates"])==9
    assert report["scenario_gate_count"]==19
    assert report["exact_matrix_all_gates_exercised"] is True
    assert report["plan"]["exact_scenario_matrix"]["required_python_test_count"]>=20
    assert len(calls)==2
    assert calls[0][0][1:4]==["-m","pytest","-vv"]
    assert report["required_python_tests_individually_passed"]==len(exact_nodes)
    assert report["required_python_tests_total"]==len(exact_nodes)
    assert calls[1][0]==["node",rehearsal.NODE_TEST]
    assert calls[0][1]["cwd"]==repo
    assert report["native_replay_authorized"] is False
    assert report["unreal_editor_executed"] is False
    assert report["release_candidate_ready"] is False
    assert json.loads(path.read_text())["runs"][0]["test_summary"]=="37 passed, 2 skipped"


def test_phase10_4_failing_regression_does_not_report_pass(tmp_path):
    repo=_repo(tmp_path)
    def fail(cmd,**kwargs):
        return SimpleNamespace(
            returncode=1 if "pytest" in cmd else 0,
            stdout="1 failed, 36 passed" if "pytest" in cmd else "25 scenarios passed",
            stderr="native job must not replay",
        )
    result=rehearsal.run(repo,runner=fail)
    assert result["status"]=="SYNTHETIC_REHEARSAL_FAILED"
    assert result["runs"][0]["exit_code"]==1
    assert result["native_replay_authorized"] is False
    assert result["post_reopen_fidelity_verified"] is False


def test_phase10_4_refuses_replay_or_file_overwrite(tmp_path):
    repo=_repo(tmp_path)
    report=tmp_path/"record.json"
    report.write_text("original",encoding="utf-8")
    with pytest.raises(rehearsal.RehearsalError,match="replace"):
        rehearsal.run(repo,output=report,runner=lambda *a,**kw:None)
    assert report.read_text()=="original"


def test_phase10_4_source_fixture_change_updates_exact_manifest_sha(tmp_path):
    repo=_repo(tmp_path)
    before=rehearsal.plan(repo)
    selected=repo/rehearsal.TEST_MODULES[0]
    selected.write_text(
        selected.read_text(encoding="utf-8")+"\n# changed source test expectations\n",
        encoding="utf-8",
    )
    after=rehearsal.plan(repo)
    assert before["test_modules"][0]["sha256"] != after["test_modules"][0]["sha256"]
    assert after["native_replay_authorized"] is False


def test_phase10_4_matrix_rejects_a_missing_fault_scenario(tmp_path):
    repo=_repo(tmp_path)
    selected=repo/"tests/studio/test_studio_autopilot.py"
    selected.write_text("def test_unrelated():\n    pass\n",encoding="utf-8")
    with pytest.raises(rehearsal.scenario_matrix.MatrixError,match="scenario missing"):
        rehearsal.plan(repo)


def test_phase10_4_matrix_rejects_uninvoked_node_scenario(tmp_path):
    repo=_repo(tmp_path)
    path=repo/rehearsal.NODE_TEST
    existing=path.read_text(encoding="utf-8")
    name=rehearsal.scenario_matrix.JS_SCENARIOS[-1]
    path.write_text(existing.replace("await "+name+"();",""),encoding="utf-8")
    with pytest.raises(rehearsal.scenario_matrix.MatrixError,match="defined and invoked"):
        rehearsal.plan(repo)


def test_phase10_4_empty_success_output_is_not_a_pass(tmp_path):
    repo=_repo(tmp_path)
    result=rehearsal.run(
        repo,runner=lambda *args,**kw:SimpleNamespace(
            returncode=0,stdout="everything seems fine",stderr="",
        ),
    )
    assert result["status"]=="SYNTHETIC_REHEARSAL_FAILED"
    assert result["exact_matrix_all_gates_exercised"] is False


def test_phase10_4_detects_source_change_between_subprocesses(tmp_path):
    repo=_repo(tmp_path)
    selected=repo/"tests/studio/test_studio_autopilot.py"
    calls=[]
    def change_source(command,**kwargs):
        calls.append(command)
        if len(calls)==1:
            selected.write_text(
                selected.read_text(encoding="utf-8")+"\n# altered midway\n",
                encoding="utf-8",
            )
        return SimpleNamespace(returncode=0,stdout=(
            "37 passed" if len(calls)==1 else "26 scenarios passed"
        ),stderr="")
    with pytest.raises(rehearsal.RehearsalError,match="changed during execution"):
        rehearsal.run(repo,runner=change_source)
