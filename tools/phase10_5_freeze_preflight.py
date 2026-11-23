"""Phase 10.5 pre-engine software freeze/handoff decision; never release parity.

Requires exact checked-out commit, independently SHA-verified source bundle,
unaltered Phase 10.4 matrix, and a real successful synthetic test receipt.
Real Unity/Unreal acceptance remains a distinct mandatory release blocker.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"packages"/"studio"))
sys.path.insert(0,str(ROOT/"tools"))

import studio_phase10_4_matrix as matrix
import build_studio_bundle as bundle
import phase10_4_rehearse as rehearsal

SHA_RE=re.compile(r"[a-f0-9]{40}\Z")


class FreezeError(ValueError):
    """Evidence/commit mismatch; do not freeze or publish."""


def _read(path:Path)->dict:
    if (path.is_symlink() or not path.is_file()
            or path.stat().st_size>8*1024*1024):
        raise FreezeError("Missing, redirected or oversized software evidence.")
    try:
        data=json.loads(path.read_text(encoding="utf-8"))
    except (ValueError,UnicodeError) as exc:
        raise FreezeError("Malformed immutable software evidence.") from exc
    if not isinstance(data,dict):
        raise FreezeError("Software evidence must be a JSON object.")
    return data


def _git_head(repo:Path)->str:
    try:
        result=subprocess.run(
            ["git","-C",str(repo),"rev-parse","HEAD"],
            capture_output=True,text=True,timeout=15,check=True,
        )
        status=subprocess.run(
            ["git","-C",str(repo),"status","--porcelain","--untracked-files=no"],
            capture_output=True,text=True,timeout=15,check=True,
        )
    except (OSError,subprocess.SubprocessError) as exc:
        raise FreezeError("Cannot independently identify the local git HEAD.") from exc
    if status.stdout.strip():
        raise FreezeError("Tracked files changed after the inspected commit.")
    return result.stdout.strip()


def _check(condition:bool,message:str)->None:
    if not condition:
        raise FreezeError(message)


def assess(repo:Path,*,bundle_path:Path,rehearsal_path:Path,
           expected_sha:str,head_reader:Callable[[Path],str]=_git_head)->dict[str,Any]:
    root=Path(repo)
    if root.is_symlink() or not root.is_dir():
        raise FreezeError("Studio source checkout is missing or redirected.")
    root=root.resolve()
    _check(bool(SHA_RE.fullmatch(expected_sha)),
           "Require the exact 40-character git commit SHA.")
    observed=head_reader(root)
    _check(observed==expected_sha,
           "Frozen source commit differs from independently observed HEAD.")
    built=bundle.verify_exact_checkout(root,Path(bundle_path))
    _check(built.get("status")=="SOURCE_BUNDLE_HASHES_VERIFIED_ENGINE_PENDING"
           and built.get("exact_checked_out_source_verified") is True,
           "Distribution source hashes do not match the inspected Git commit.")
    evidence=_read(Path(rehearsal_path))
    _check(evidence.get("kind")=="cutsceneai.studio.phase10_4.synthetic_rehearsal",
           "Wrong rehearsal evidence type.")
    _check(evidence.get("status")==
           "SYNTHETIC_REHEARSAL_PASSED_ENGINE_ACCEPTANCE_PENDING",
           "Phase 10.4 did not pass.")
    _check(evidence.get("exact_matrix_all_gates_exercised") is True,
           "Required test scenarios were not proven to execute.")
    _check(evidence.get("native_replay_authorized") is False and
           evidence.get("release_candidate_ready") is False and
           evidence.get("post_reopen_fidelity_verified") is False and
           evidence.get("unreal_editor_executed") is False and
           evidence.get("unity_editor_executed") is False,
           "Synthetic evidence is claiming native execution or unsafe replay.")
    plan=evidence.get("plan")
    _check(isinstance(plan,dict),"Rehearsal plan evidence missing.")
    expected=rehearsal.plan(root)
    _check(plan==expected,"Rehearsal test/source bytes differ from this commit.")
    exact=matrix.verify(root)
    _check(exact==plan.get("exact_scenario_matrix"),
           "Required synthetic acceptance matrix is stale.")
    runs=evidence.get("runs")
    _check(isinstance(runs,list) and len(runs)==2
           and [v.get("command_category") for v in runs if isinstance(v,dict)]==[
               "python_synthetic_regressions","node_ui_interruption_regressions"
           ] and all(v.get("exit_code")==0 and
                     v.get("test_summary") not in (None,"NO_TEST_SUMMARY")
                     for v in runs if isinstance(v,dict)),
           "Missing successful Python or UI test execution proof.")
    for label in ("python_synthetic_regressions","node_ui_interruption_regressions"):
        entry=next(v for v in runs if v["command_category"]==label)
        _check(re.fullmatch(r"[0-9a-f]{64}",str(entry.get("stdout_sha256") or "")) is not None,
               "Rehearsal output SHA256 missing.")
    return {
        "kind":"cutsceneai.studio.phase10_5.pre_engine_freeze_preflight",
        "schema_version":"1",
        "source_git_sha":expected_sha,
        "software_checks":{
            "exact_commit_and_clean_tracked_tree":"PASS",
            "phase10_4_all_software_gates":"PASS",
            "phase10_4_scenario_count":exact["total_gates"],
            "source_bundle_sha256_verified":"PASS",
            "source_bundle_sha256":built["sha256"],
            "source_manifest_sha256":built["source_manifest_sha256"],
            "portable_source_manifest_sha256":built["portable_source_manifest_sha256"],
            "source_bundle_file_count":built["file_count"],
            "native_replay_contract":"PASS_NO_REPLAY",
        },
        "status":"PRE_ENGINE_SOFTWARE_HANDOFF_READY",
        "real_engine_acceptance":{
            "unity_package_compile":"INCOMPLETE",
            "unreal_worker_startup_and_native_reopen":"INCOMPLETE",
            "real_model_and_agent_action":"INCOMPLETE",
            "rendered_audio_effect_skeletal_parity":"INCOMPLETE",
            "heldout_cutscene_verification":"INCOMPLETE",
            "clean_external_workstation_installer":"INCOMPLETE",
        },
        "production_release_ready":False,
        "engine_fidelity_verified":False,
        "final_freeze_authorized":False,
        "native_replay_authorized":False,
        "next_action":(
            "Review this exact source SHA and the archived source bundle and "
            "Phase 10.4 receipt. Complete independently observed Editor and "
            "workstation acceptance before authorizing a release freeze."
        ),
    }


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo",type=Path,default=ROOT)
    parser.add_argument("--bundle",type=Path,required=True)
    parser.add_argument("--rehearsal",type=Path,required=True)
    parser.add_argument("--commit",required=True,
                        help="Exact 40-character Git commit being reviewed")
    parser.add_argument("--output",type=Path,required=True,
                        help="New immutable JSON receipt path outside checkout")
    args=parser.parse_args(argv)
    try:
        report=assess(args.repo,bundle_path=args.bundle,
                      rehearsal_path=args.rehearsal,expected_sha=args.commit)
        dest=args.output
        if dest.is_symlink() or dest.exists():
            raise FreezeError("Refusing to replace an existing freeze preflight.")
        if dest.resolve().is_relative_to(args.repo.resolve()):
            raise FreezeError("Preflight evidence must be stored outside the checkout.")
        dest.parent.mkdir(parents=True,exist_ok=True)
        with dest.open("x",encoding="utf-8") as stream:
            json.dump(report,stream,indent=2,sort_keys=True,allow_nan=False)
            stream.write("\n")
    except (FreezeError,ValueError,KeyError,TypeError,OSError) as exc:
        parser.error(str(exc))
    print(json.dumps({
        "status":report["status"],
        "source_git_sha":report["source_git_sha"],
        "production_release_ready":False,
        "final_freeze_authorized":False,
        "engine_fidelity_verified":False,
    },sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
