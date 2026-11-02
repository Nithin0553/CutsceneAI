"""Evaluate native Unreal and CineTwin evidence after a Studio transfer.

Produces a source-grounded repair *decision report*, not fabricated automated
repairs or an unconditional conversion pass. The result is immutable evidence.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any


class EvidenceError(ValueError):
    """Untrusted or incompatible evidence, never a transfer PASS."""


def evaluate(
    diagnostic: dict[str, Any] | None,
    visual: dict[str, Any] | None,
    *,
    max_motion_error_cm: float = 2.0,
    repair_iterations: int = 0,
) -> dict[str, Any]:
    """Propose only existing CED-driven strategy domains, never guess fixes."""
    if isinstance(repair_iterations, bool) or not isinstance(repair_iterations, int) or not 0 <= repair_iterations <= 2:
        raise EvidenceError('Repair iteration count must be between 0 and 2.')
    if not math.isfinite(max_motion_error_cm) or max_motion_error_cm <= 0:
        raise EvidenceError("A finite positive motion tolerance is required.")
    issues: list[dict[str, Any]] = []
    measured = False
    if diagnostic:
        if diagnostic.get("kind") != "cutsceneai.cinetwin.unreal_world_pose_diagnostic":
            raise EvidenceError("Wrong CineTwin diagnostic kind.")
        measured = True
        for name, row in sorted((diagnostic.get("entities") or {}).items()):
            if row.get("status") != "READY":
                issues.append({
                    "category": "SOURCE_TARGET_ACTOR_MAPPING",
                    "source": name, "status": "INCOMPLETE",
                    "action": "Reconstruct a source-verified unique actor mapping",
                    "automatic_repair_allowed": False,
                })
                continue
            for mode in ("actor_world", "skeletal_root_world"):
                measurements = row.get(mode) or {}
                error = measurements.get("max_offset_removed_motion_error_cm")
                if not isinstance(error, (float, int)) or not math.isfinite(error):
                    continue
                if error > max_motion_error_cm:
                    issues.append({
                        "category": "CED_ANIMATION_TRANSFORM_FIDELITY",
                        "source": name, "domain": mode,
                        "error_cm": round(error, 4), "tolerance_cm": max_motion_error_cm,
                        "status": "MEASURED_MISMATCH",
                        "action": "Compare source root-motion ownership, reference orientation, and animation offset strategy",
                        "automatic_repair_allowed": False,
                    })
        if diagnostic.get("source", {}).get("missing_source_frames"):
            issues.append({
                "category": "CINETWIN_SOURCE_SAMPLE_COVERAGE",
                "status": "INCOMPLETE", "action": "Capture the missing source frames",
                "automatic_repair_allowed": False,
            })
        for message in diagnostic.get("errors") or []:
            issues.append({
                "category": "CINETWIN_NATIVE_EVALUATION", "status": "INCOMPLETE",
                "detail": str(message), "automatic_repair_allowed": False,
            })
    else:
        issues.append({
            "category": "CINETWIN_EVIDENCE_MISSING", "status": "INCOMPLETE",
            "action": "Capture source behavior and run source/target CineTwin comparison",
            "automatic_repair_allowed": False,
        })
    if visual:
        if visual.get("kind") != "cutsceneai.studio.visual_readback_audit":
            raise EvidenceError("Wrong native visual audit kind.")
        for code in visual.get("visual_issues") or []:
            issues.append({
                "category": "VISUAL_NATIVE_READBACK",
                "status": "NATIVE_GAP",
                "code": str(code),
                "action": ("Recover exact source-backed Unity material/texture assignment"
                           if "MATERIAL" in str(code) else
                           "Compare source lighting/environment before reconstructing target"),
                "automatic_repair_allowed": False,
            })
    else:
        issues.append({
            "category": "VISUAL_NATIVE_AUDIT_MISSING", "status": "INCOMPLETE",
            "automatic_repair_allowed": False,
        })
    # Even zero detected issues do not prove pixel-level rendering, audio,
    # full joint motion, events, or source shader parity. No unknown repair is
    # safe to apply to a user's staged scene without source-backed semantics.
    return {
        "kind": "cutsceneai.studio.closed_loop_evaluation",
        "schema_version": "0.1.0",
        "status": "REVIEW_REQUIRED" if issues else "MEASURED_DOMAINS_WITHIN_TOLERANCE_OTHER_DOMAINS_UNVERIFIED",
        "cinetwin_measured": measured,
        "issue_count": len(issues),
        "issues": issues,
        "automatic_repair_executed": repair_iterations > 0,
        "repair_iterations_executed": repair_iterations,
        "fidelity_verified": False,
        "unverified_domains": ["rendered_frame_parity", "camera_framing", "all_skeletal_joints",
                               "audio_waveform_and_timing", "signal_side_effects",
                               "materials_and_URP_shader_equivalence",
                               "save_reopen_independent_persistence"],
        "next_action": "Only source-backed, independently measurable, non-destructive strategies may enter a future bounded retry; no automatic in-place modification was attempted.",
    }


def write_new(path: str | Path, report: dict[str, Any]) -> None:
    """Never replace immutable transfer evidence."""
    target = Path(path)
    with target.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
