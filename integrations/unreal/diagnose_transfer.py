"""Read-only Unreal runtime diagnostics for the current CSIR -> Sequencer adapter.

Run via Tools > Execute Python Script with run(...). This does not generate
a Level Sequence, attach actors, save a level, or change actor transforms.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sys
import traceback
from typing import Any

import unreal

HERE = Path(__file__).resolve().parent
for directory in (HERE, HERE.parents[1] / "packages" / "cinetwin"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import build_level_sequence
import csir_plan
import scene_prep
import transfer_readiness


def _fingerprint(path: str | os.PathLike[str]) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(
    csir_path: str,
    mapping_path: str,
    report_path: str,
    *,
    expected_project: str | None = None,
    expected_level: str | None = None,
) -> dict[str, Any]:
    """Run guarded mapping/capability checks and write a machine-readable report.

    No generator entrypoint is called: even a READY result is not permission to
    claim source-target fidelity, only to attempt a separate staged generation.
    """
    report: dict[str, Any] = {
        "report_kind": "cutsceneai.unreal_runtime_diagnostic",
        "status": "BLOCKED",
        "stage": "start",
        "target_mutated": False,
        "source_csir": str(csir_path),
        "target_mapping": str(mapping_path),
        "expected_project": expected_project,
        "expected_level": expected_level,
    }
    try:
        report["stage"] = "source_and_mapping"
        report["csir_sha256"] = _fingerprint(csir_path)
        report["mapping_sha256"] = _fingerprint(mapping_path)
        csir = csir_plan.load_json(csir_path)
        mapping = csir_plan.load_json(mapping_path)

        report["stage"] = "source_coverage"
        coverage = transfer_readiness.audit(csir, mapping)
        report["source_readiness"] = coverage
        if coverage["generation"] == "BLOCKED":
            raise RuntimeError("Source semantic coverage or planner is BLOCKED. See source_readiness.")

        report["stage"] = "target_project"
        project_path = str(unreal.Paths.get_project_file_path())
        report["actual_project"] = project_path
        if expected_project and os.path.normcase(os.path.abspath(project_path)) != os.path.normcase(
            os.path.abspath(expected_project)
        ):
            raise RuntimeError(
                f"Wrong Unreal project: {project_path}; expected {expected_project}"
            )

        report["stage"] = "target_level"
        world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
        level = str(world.get_path_name()).split(".")[0]
        report["actual_level"] = level
        if expected_level and level != expected_level:
            raise RuntimeError(f"Wrong level: {level}; expected {expected_level}")

        report["stage"] = "source_frame_zero"
        placements = scene_prep.build_scene_prep(csir, mapping)
        report["mapped_actor_placements"] = len(placements)
        report["placement_provenance"] = sorted(set(p["source"] for p in placements))

        report["stage"] = "engine_capabilities_and_assets"
        # This preflight probes the real Unreal runtime, mapped level actors,
        # imported animations/audio and root-motion sampler without mutation.
        plan = csir_plan.build_plan(csir, mapping)
        build_level_sequence._preflight(plan)
        report["planned_action_counts"] = coverage["planned_actions"]
        report["status"] = "READY_FOR_STAGED_GENERATION"
        report["stage"] = "complete"
    except Exception as exc:
        report["exception"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(),
        }
        unreal.log_error(
            f"[CutSceneAI] Diagnostic BLOCKED at {report['stage']}: "
            f"{type(exc).__name__}: {exc}"
        )
    finally:
        output = Path(report_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        unreal.log(
            f"[CutSceneAI] Diagnostic status={report['status']} stage={report['stage']} "
            f"report={output}. No Unreal assets modified."
        )
    return report
