"""Phase 10.5 cross-run software package acceptance, not engine fidelity.

Combines Ubuntu's source-bound Phase 10.4/10.5 artifacts and independent
Windows extracted-ZIP install + actual localhost Studio startup receipt.
Refuses unverifiable, foreign-commit or missing runs. Cannot authorize final
production release, native retries, engine acceptance or package mutation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path

HEX40=re.compile(r"[0-9a-f]{40}\Z")
HEX64=re.compile(r"[0-9a-f]{64}\Z")
STARTUP_CHECKS={
    "actual_server_process_started","isolated_workspace_no_source",
    "session_token_required","html_and_js_available",
    "source_bound_workflow_diagnostics","no_forged_release_readiness",
    "foreign_host_rejected","no_native_job_created",
}


class PackageAcceptanceError(ValueError):
    pass


def _read(path:Path)->dict:
    if path.is_symlink() or not path.is_file() or not (0<path.stat().st_size<=8*1024*1024):
        raise PackageAcceptanceError("Missing, redirected or oversized release evidence.")
    try:
        raw=json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError,ValueError) as exc:
        raise PackageAcceptanceError("Malformed release acceptance JSON.") from exc
    if not isinstance(raw,dict):
        raise PackageAcceptanceError("Release evidence is not a JSON object.")
    return raw


def _require(flag:bool,message:str)->None:
    if not flag:
        raise PackageAcceptanceError(message)


def assess(*,commit:str,preflight:Path,startup:Path,bundle:Path,
           rehearsal:Path)->dict:
    _require(bool(HEX40.fullmatch(commit)),"Exact 40-character commit required.")
    handoff=_read(preflight)
    smoke=_read(startup)
    tests=_read(rehearsal)
    _require(handoff.get("kind")=="cutsceneai.studio.phase10_5.pre_engine_freeze_preflight"
             and handoff.get("source_git_sha")==commit
             and handoff.get("status")=="PRE_ENGINE_SOFTWARE_HANDOFF_READY",
             "Phase 10.5 preflight belongs to another commit or is incomplete.")
    _require(handoff.get("production_release_ready") is False
             and handoff.get("final_freeze_authorized") is False
             and handoff.get("engine_fidelity_verified") is False,
             "Software handoff falsely claims real-engine release authority.")
    checks=handoff.get("software_checks")
    _require(isinstance(checks,dict)
             and checks.get("exact_commit_and_clean_tracked_tree")=="PASS"
             and checks.get("phase10_4_all_software_gates")=="PASS"
             and checks.get("source_bundle_sha256_verified")=="PASS"
             and checks.get("native_replay_contract")=="PASS_NO_REPLAY"
             and checks.get("phase10_4_scenario_count")==19,
             "Source/acceptance software matrix is incomplete.")
    _require(smoke.get("kind")=="cutsceneai.studio.phase10_5.localhost_startup_smoke"
             and smoke.get("status")==
                 "LIVE_LOCALHOST_AND_UI_SMOKE_PASSED_ENGINE_UNVERIFIED",
             "Clean Windows source package did not successfully start Studio.")
    _require(isinstance(smoke.get("checks"),dict)
             and set(smoke["checks"])==STARTUP_CHECKS
             and all(value=="PASS" for value in smoke["checks"].values()),
             "Windows Studio startup checks are missing or failing.")
    _require(smoke.get("native_editor_started") is False
             and smoke.get("unity_editor_started") is False
             and smoke.get("model_invoked") is False
             and smoke.get("full_cutscene_fidelity_verified") is False
             and smoke.get("production_release_ready") is False,
             "Windows smoke data falsely claims model or engine acceptance.")
    _require(tests.get("kind")=="cutsceneai.studio.phase10_4.synthetic_rehearsal"
             and tests.get("status")==
                 "SYNTHETIC_REHEARSAL_PASSED_ENGINE_ACCEPTANCE_PENDING"
             and tests.get("scenario_gate_count")==19
             and tests.get("exact_matrix_all_gates_exercised") is True
             and tests.get("release_candidate_ready") is False
             and tests.get("native_replay_authorized") is False,
             "Source-only end-to-end rehearsal is missing or overclaims approval.")
    path=Path(bundle)
    _require(path.is_file() and not path.is_symlink() and path.stat().st_size>0,
             "Verified source distribution ZIP is missing.")
    archive_sha=hashlib.sha256(path.read_bytes()).hexdigest()
    _require(bool(HEX64.fullmatch(archive_sha))
             and checks.get("source_bundle_sha256")==archive_sha,
             "Source ZIP bytes differ from the exact-commit freeze audit.")
    # Windows checkout may apply CRLF to source text and ZIP compression can
    # differ. Compare every file's LF-normalized content SHA while preserving
    # separately checked raw Windows/Linux archive+manifest hashes.
    windows_zip_sha=smoke.get("source_distribution_sha256")
    manifest_sha=checks.get("source_manifest_sha256")
    windows_manifest_sha=smoke.get("source_manifest_sha256")
    portable_sha=checks.get("portable_source_manifest_sha256")
    _require(all(HEX64.fullmatch(str(value or "")) for value in (
        windows_zip_sha, manifest_sha, windows_manifest_sha, portable_sha)),
        "Either Windows or Ubuntu lacks raw source ZIP/manifest provenance.")
    _require(smoke.get("portable_source_manifest_sha256")==portable_sha,
             "Windows packaged Studio normalized source content differs from the reviewed checkout.")
    return {
        "kind":"cutsceneai.studio.phase10_5.cross_platform_software_package_acceptance",
        "schema_version":"1",
        "source_git_sha":commit,
        "status":"SOFTWARE_PACKAGE_READY_FOR_ENGINE_TEST",
        "verified": {
            "source_distribution_sha256":archive_sha,
            "source_manifest_sha256":manifest_sha,
            "windows_manifest_sha256":windows_manifest_sha,
            "portable_source_manifest_sha256":portable_sha,
            "windows_archive_sha256":windows_zip_sha,
            "phase10_4_source_only_gates":19,
            "windows_clean_source_zip_installed":True,
            "actual_packaged_studio_localhost_started":True,
            "local_mutation_security_and_source_readonly_checks":"PASS",
            "ci_handoff_commit_bound":"PASS",
        },
        "next_action":"Open Studio on a backed-up Windows workstation, connect actual Unity/Unreal companions, and collect authentic engine acceptance.",
        "full_cutscene_fidelity_verified":False,
        "native_replay_authorized":False,
        "real_engine_acceptance_complete":False,
        "final_release_frozen":False,
        "production_release_ready":False,
    }


def main(argv=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit",required=True)
    parser.add_argument("--preflight",type=Path,required=True)
    parser.add_argument("--startup",type=Path,required=True)
    parser.add_argument("--bundle",type=Path,required=True)
    parser.add_argument("--rehearsal",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    args=parser.parse_args(argv)
    try:
        report=assess(commit=args.commit,preflight=args.preflight,
                      startup=args.startup,bundle=args.bundle,rehearsal=args.rehearsal)
        if args.output.exists() or args.output.is_symlink():
            raise PackageAcceptanceError("Refusing to overwrite an existing handoff.")
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open("x",encoding="utf-8") as output:
            json.dump(report,output,indent=2,sort_keys=True)
            output.write("\n")
    except (PackageAcceptanceError,ValueError,OSError) as exc:
        parser.error(str(exc))
    print(json.dumps({"status":report["status"],
                      "production_release_ready":False,
                      "real_engine_acceptance_complete":False,
                      "source_git_sha":report["source_git_sha"]},sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
