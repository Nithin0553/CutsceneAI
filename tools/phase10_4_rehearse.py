#!/usr/bin/env python3
"""Phase 10.4 — run bounded synthetic end-to-end Studio interruption rehearsals.

This tool executes existing, real Python/Node regressions against the actual
Studio modules and local mock engine endpoints. It never launches Unity,
Unreal, a browser, a model, or a native transfer. A passing rehearsal is NOT
engine acceptance and cannot authorize a native job retry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

TEST_MODULES = (
    "tests/studio/test_studio_autopilot.py",
    "tests/studio/test_studio_unity_bridge.py",
    "tests/studio/test_studio_destination_preflight.py",
    "tests/studio/test_studio_generation_recovery.py",
    "tests/studio/test_element9_final_outcome.py",
    "tests/studio/test_phase10_3_companion_and_flow.py",
    "tests/studio/test_phase10_3_distribution.py",
)
NODE_TEST = "tests/studio/test_cinematic_ui.cjs"
CATEGORY_GATES = (
    "unity_source_and_cinetwin_capture",
    "ced_planning_and_source_provenance",
    "pre_native_candidate_approval",
    "unreal_worker_disconnection_and_wrong_level",
    "native_partial_import_and_no_replay",
    "unreal_reopen_and_source_readback",
    "repair_and_terminal_outcome",
    "browser_and_job_switch_recovery",
    "companion_and_workstation_setup",
)


class RehearsalError(ValueError):
    pass


def _sha(payload:bytes)->str:
    return hashlib.sha256(payload).hexdigest()


def plan(repo:Path)->dict:
    root=repo.resolve()
    checks=[]
    for relative in (*TEST_MODULES,NODE_TEST):
        path=root/relative
        if (path.is_symlink() or not path.is_file()
                or not path.resolve().is_relative_to(root)):
            raise RehearsalError("Synthetic source module missing or redirected: "+relative)
        data=path.read_bytes()
        if not data or len(data)>2*1024*1024:
            raise RehearsalError("Invalid synthetic regression fixture size.")
        checks.append({"path":relative,"sha256":_sha(data)})
    return {
        "kind":"cutsceneai.studio.phase10_4.synthetic_rehearsal_plan",
        "schema_version":"1",
        "phase10_3_setup_and_workflow_requirements_included":True,
        "stage_and_interruption_gates":list(CATEGORY_GATES),
        "test_modules":checks,
        "unreal_editor_required":False,
        "unity_editor_required":False,
        "native_replay_authorized":False,
        "full_cutscene_fidelity_verified":False,
    }


def run(repo:Path, *, output:Path | None=None,
        runner=subprocess.run)->dict:
    root=repo.resolve()
    selected=plan(root)
    if output is not None and (output.exists() or output.is_symlink()):
        raise RehearsalError("Refusing to replace a prior immutable rehearsal receipt.")
    python_call=[sys.executable,"-m","pytest","-q",*TEST_MODULES]
    node_call=["node",NODE_TEST]
    result=[]
    for command in (python_call,node_call):
        try:
            proc=runner(command,cwd=root,capture_output=True,text=True,
                        timeout=300,check=False)
        except (OSError,subprocess.TimeoutExpired) as exc:
            raise RehearsalError(
                "Synthetic rehearsal unavailable or exceeded its 300-second bound."
            ) from exc
        stdout=str(proc.stdout or "")
        stderr=str(proc.stderr or "")
        outcome={
            "command_category":"python_synthetic_regressions" if command==python_call
                else "node_ui_interruption_regressions",
            "exit_code":int(proc.returncode),
            "stdout_sha256":_sha(stdout.encode("utf-8")),
            "stderr_sha256":_sha(stderr.encode("utf-8")),
            "test_summary":(
                re.search(r"\d+ passed(?:, \d+ skipped)?",stdout) or
                re.search(r"\d+ failed[^\n]*",stdout) or
                re.search(r"\d+ scenarios[^\n]*",stdout)
            ).group(0) if (
                re.search(r"\d+ passed(?:, \d+ skipped)?",stdout) or
                re.search(r"\d+ failed[^\n]*",stdout) or
                re.search(r"\d+ scenarios[^\n]*",stdout)
            ) else "NO_TEST_SUMMARY",
        }
        result.append(outcome)
    report={
        "kind":"cutsceneai.studio.phase10_4.synthetic_rehearsal",
        "schema_version":"1",
        "plan":selected,
        "runs":result,
        "status":("SYNTHETIC_REHEARSAL_PASSED_ENGINE_ACCEPTANCE_PENDING"
                  if all(r["exit_code"]==0 for r in result)
                  else "SYNTHETIC_REHEARSAL_FAILED"),
        "unreal_editor_executed":False,
        "unity_editor_executed":False,
        "post_reopen_fidelity_verified":False,
        "native_replay_authorized":False,
        "release_candidate_ready":False,
    }
    if output is not None:
        output.parent.mkdir(parents=True,exist_ok=True)
        if output.resolve().is_relative_to(root):
            raise RehearsalError("Rehearsal report cannot be written into source tree.")
        with output.open("x",encoding="utf-8") as file:
            json.dump(report,file,sort_keys=True,indent=2,allow_nan=False)
            file.write("\n")
    return report


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo",type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument("--output",type=Path,
                        help="An immutable report JSON path outside the source checkout")
    args=parser.parse_args(argv)
    try:
        report=run(args.repo,output=args.output)
    except (RehearsalError,OSError,ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({
        "status":report["status"],
        "test_suites":len(report["runs"]),
        "stage_gates":len(report["plan"]["stage_and_interruption_gates"]),
        "native_replay_authorized":False,
        "full_cutscene_fidelity_verified":False,
    },sort_keys=True))
    return 0 if report["status"].startswith("SYNTHETIC_REHEARSAL_PASSED") else 1


if __name__=="__main__":
    sys.exit(main())
