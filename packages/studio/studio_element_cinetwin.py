"""Element 3.5 — independently recomputed CineTwin occurrence attribution.

This adapter reuses the existing CineTwin measurement and *does not* execute
native repairs. An entity can be measured directly; an associated Timeline
track, section, curve, relationship or asset is at most a diagnostic context,
never a proven cause. Readback cannot establish visual/audio/full fidelity.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import studio_element_plan as element_plan

CINETWIN = str(Path(__file__).resolve().parents[1] / "cinetwin")
if CINETWIN not in sys.path:
    sys.path.insert(0, CINETWIN)

from behavior_compare import BehavioralComparisonError, compare
from sampling_plan import SamplingPlanError, build_plan

VERSION = "1"
MAX_REMEASURE_ATTEMPTS = 2
_SHA = re.compile(r"[a-f0-9]{64}\Z")

# Known measurement categories from the established CineTwin comparator.
ACTOR_FLAGS = frozenset({
    "WORLD_POSITION_OUTSIDE_TOLERANCE", "WORLD_ROTATION_OUTSIDE_TOLERANCE",
    "SOURCE_MOVES_BUT_TARGET_ACTOR_STATIC",
})
RIG_FLAGS = frozenset({
    "SOURCE_BONES_MOVE_BUT_TARGET_BONES_STATIC",
    "SKELETAL_WORLD_JOINT_POSITION_MISMATCH",
    "SKELETAL_JOINT_ANGULAR_MOTION_PROFILE_MISMATCH",
    "CALIBRATED_SKELETAL_JOINT_ORIENTATION_MISMATCH",
    "CHARACTER_MESH_ANATOMICAL_FORWARD_MISMATCH",
})
DOMAINS = ("actor_transform", "skeletal_motion", "camera_lens", "camera_cuts")


class ElementCineTwinError(ValueError):
    """Missing, foreign, incomplete or altered native comparison evidence."""


def _digest(value: Any) -> str:
    return element_plan._digest(value)


def _bound_rows(csir: dict, conversion: dict) -> list[dict]:
    """Bind anonymous occurrences to their original, exact source locations."""
    if not isinstance(csir, dict) or not isinstance(conversion, dict):
        raise ElementCineTwinError("Source and exact-source element plan are required.")
    try:
        element_plan._validate_contract(conversion)
        rows = element_plan._rows(csir)
    except element_plan.ElementPlanError as exc:
        raise ElementCineTwinError("Invalid source conversion occurrence contract.") from exc
    if (conversion.get("no_native_execution_permission") is not True
            or conversion.get("native_conversion_executed") is not False
            or conversion.get("source_csir_sha256") != _digest(csir)
            or conversion.get("element_plan_sha256") != _digest({
                k: v for k, v in conversion.items()
                if k != "element_plan_sha256"
            })
            or len(rows) != conversion["source_occurrence_count"]
            or len(conversion["elements"]) != len(rows)):
        raise ElementCineTwinError("Source occurrence plan is stale, forged or incomplete.")
    for index, (observed, expected) in enumerate(zip(conversion["elements"], rows)):
        if (observed["occurrence_id"] != f"E{index:05d}"
                or observed["source_kind"] != expected["kind"]
                or observed["source_location"] != expected["source_location"]):
            raise ElementCineTwinError("Source occurrence identities are not aligned.")
    return rows


def _sampling(csir: dict, sampling: dict) -> None:
    if not isinstance(sampling, dict) or sampling.get("kind") != "cinetwin.sampling_plan":
        raise ElementCineTwinError("A CineTwin source sampling plan is required.")
    csir_sha = sampling.get("source", {}).get("csir_sha256")
    if not isinstance(csir_sha, str) or not _SHA.fullmatch(csir_sha):
        raise ElementCineTwinError("CineTwin sampling plan lacks a source bytes digest.")
    try:
        expected = build_plan(csir, csir_sha256=csir_sha)
    except (SamplingPlanError, KeyError, TypeError, ValueError) as exc:
        raise ElementCineTwinError("Source CineTwin sampling plan cannot be rebuilt.") from exc
    if expected != sampling:
        raise ElementCineTwinError("Sampling plan is stale or belongs to different source CSIR.")


def _number(value: Any, label: str) -> float:
    # CineTwin already validates finite metrics; do not permit type coercion
    # of malicious strings/bools if its result is ever extended.
    if type(value) not in (int, float) or not (0 <= value < 1_000_000):
        raise ElementCineTwinError("Invalid CineTwin " + label + " measurement.")
    return float(value)


def _target_identity(target: dict) -> str | None:
    """Recognize an attested target project/sequence identity if present.

    The behavior capture schema does not require a persistence/readback receipt.
    Omission is explicit and prevents a verified engine recovery claim.
    """
    value = target.get("target")
    if not isinstance(value, dict):
        return None
    project = value.get("project_identity_sha256")
    sequence = value.get("sequence_asset_path")
    if (not isinstance(project, str) or not _SHA.fullmatch(project)
            or not isinstance(sequence, str)
            or not re.fullmatch(r"/Game/(?:[A-Za-z0-9_]+/)*[A-Za-z0-9_]+", sequence)):
        return None
    return _digest({"project_identity_sha256": project,
                    "sequence_asset_path": sequence})


def _status_from_actor(actor: dict | None, rig: dict | None,
                       lens: dict | None) -> tuple[str, list[str], dict]:
    if actor is None:
        return "INCOMPLETE_TARGET_UNMAPPED", ["TARGET_ENTITY_UNMAPPED"], {}
    aflags = actor.get("flags", [])
    rflags = rig.get("flags", []) if rig is not None else []
    if (not isinstance(aflags, list) or not set(aflags) <= ACTOR_FLAGS
            or not isinstance(rflags, list) or not set(rflags) <= RIG_FLAGS):
        raise ElementCineTwinError("CineTwin returned an unrecognized measured discrepancy.")
    flags = set(aflags) | set(rflags)
    lens_status = lens["status"] if lens is not None else "NOT_APPLICABLE"
    if lens_status not in {"PASS", "FAIL", "INCOMPLETE", "NOT_APPLICABLE"}:
        raise ElementCineTwinError("CineTwin camera status is invalid.")
    if lens_status == "FAIL":
        flags.add("CAMERA_NATIVE_LENS_DIFFERENCE")
    measures = {
        "actor_position_cm": _number(actor["max_world_position_error_cm"], "position"),
        "actor_rotation_degrees": _number(
            actor["max_world_rotation_error_degrees"], "orientation"
        ),
    }
    if rig is not None:
        joint = rig.get("joint_positions", {})
        if joint.get("status") not in {"PASS", "FAIL", "INCOMPLETE"}:
            raise ElementCineTwinError("Invalid native skeletal joint evidence.")
        measures["skeletal_joint_status"] = joint["status"]
    if lens is not None:
        measures["camera_lens_status"] = lens_status
        if lens.get("max_vertical_fov_error_degrees") is not None:
            measures["camera_lens_error_degrees"] = _number(
                lens["max_vertical_fov_error_degrees"], "lens"
            )
    if flags:
        return "DIRECT_MEASURED_DIFFERENCE", sorted(flags), measures
    if (lens_status == "INCOMPLETE"
            or rig is not None and (
                rig.get("joint_positions", {}).get("status") != "PASS"
                or rig.get("joint_angular_motion", {}).get("status") != "PASS"
            )):
        return "DIRECT_MEASUREMENT_INCOMPLETE", [], measures
    return "DIRECT_MEASURED_NO_FLAGGED_DIFFERENCE", [], measures


def build(csir: dict, conversion: dict, sampling: dict,
          source_capture: dict, target_capture: dict) -> dict:
    """Recompute original CineTwin measurements before any attribution."""
    rows = _bound_rows(csir, conversion)
    _sampling(csir, sampling)
    if not isinstance(source_capture, dict) or not isinstance(target_capture, dict):
        raise ElementCineTwinError("Both raw source/target measurements are required.")
    try:
        comparison = compare(sampling, source_capture, target_capture)
    except (BehavioralComparisonError, KeyError, TypeError, ValueError) as exc:
        raise ElementCineTwinError(
            "Independent CineTwin source/target observations failed validation: "
            + str(exc)[:220]
        ) from exc
    if comparison.get("kind") != "cinetwin.behavior_comparison":
        raise ElementCineTwinError("Unexpected CineTwin behavior comparator.")
    if comparison.get("evaluation", {}).get("overall_cutscene_fidelity") != "NOT_ESTABLISHED":
        raise ElementCineTwinError("A source sample cannot claim whole-cutscene fidelity.")
    by_eid = {row["entity_id"]: row for row in comparison["entities"]}
    rigs = {row["entity_id"]: row for row in comparison["rig_motion_diagnostics"]}
    optics = {row["source_entity_id"]: row
              for row in comparison["camera_optics"]["per_camera"]}
    unmapped = {row["entity_id"] for row in comparison["unmapped_source_entities"]}
    if (len(by_eid) != len(comparison["entities"])
            or len(rigs) != len(comparison["rig_motion_diagnostics"])
            or len(optics) != len(comparison["camera_optics"]["per_camera"])):
        raise ElementCineTwinError("CineTwin comparison duplicated source identity.")
    # Entity indices never equal occurrence indices if source assets precede
    # entities. Use the independently checked location/occurrence pairs.
    eid_to_occurrence: dict[str, str] = {}
    for row, item in zip(rows, conversion["elements"]):
        if row["kind"] == "entities" and row["raw_id"] is not None:
            if row["raw_id"] in eid_to_occurrence:
                raise ElementCineTwinError("Duplicated source entity identity.")
            eid_to_occurrence[row["raw_id"]] = item["occurrence_id"]
    if (set(by_eid) | unmapped) != set(eid_to_occurrence):
        raise ElementCineTwinError("CineTwin observation omitted source entities.")
    # Infer only which track is *bound* to which source entity, not which
    # track caused a measured actor or skeletal discrepancy.
    tracks = csir.get("tracks", [])
    output = []
    for row, item in zip(rows, conversion["elements"]):
        kind, location = row["kind"], row["source_location"]
        direct_entity = row["raw_id"] if kind == "entities" else None
        binding = None
        if kind == "tracks":
            binding = row["item"].get("binding_entity_id")
        elif kind in {"sections", "curves"}:
            match = re.match(r"tracks\[(\d+)\]", location)
            track_index = int(match.group(1)) if match else -1
            if not 0 <= track_index < len(tracks):
                raise ElementCineTwinError("Section/curve no longer has a source track.")
            binding = tracks[track_index].get("binding_entity_id")
        linked = eid_to_occurrence.get(binding) if isinstance(binding, str) else None
        flags: list[str] = []
        metric: dict = {}
        if kind == "entities":
            actor = by_eid.get(direct_entity)
            rig = rigs.get(direct_entity)
            lens = optics.get(direct_entity)
            status, flags, metric = _status_from_actor(actor, rig, lens)
            if direct_entity in unmapped and actor is not None:
                raise ElementCineTwinError("Mapped/unmapped source entity conflict.")
        elif kind in {"tracks", "sections", "curves"}:
            status = "LINKED_CONTEXT_NOT_CAUSAL_ATTRIBUTION" if linked else "NOT_DIRECTLY_MEASURED"
            bound_actor = by_eid.get(binding)
            if bound_actor and bound_actor["flags"]:
                flags.append("BOUND_ENTITY_HAS_MEASURED_DIFFERENCE")
            if kind in {"tracks", "sections"} and (
                row["item"].get("ced_type") == "camera.cut"
                or (kind == "sections" and tracks[int(
                    re.match(r"tracks\[(\d+)\]", location).group(1)
                )].get("ced_type") == "camera.cut")
            ):
                if comparison["camera_cut_timing"]["status"] == "FAIL":
                    flags.append("GLOBAL_CAMERA_CUT_TIMING_DIFFERENCE")
                elif comparison["camera_cut_timing"]["status"] == "INCOMPLETE":
                    flags.append("GLOBAL_CAMERA_CUT_READBACK_INCOMPLETE")
        else:
            status = "NOT_DIRECTLY_MEASURED"
        # Non-entity source types are never declared measured/converted from
        # actor observations alone. Unknown entities are also unresolved.
        if kind == "entities" and item["state"] in {
            "UNKNOWN_SEMANTIC_INVESTIGATE", "UNRESOLVED_SOURCE_DEPENDENCY"
        }:
            if status in {
                "INCOMPLETE_TARGET_UNMAPPED", "DIRECT_MEASURED_DIFFERENCE",
            }:
                # Preserve native coverage and observed differences. Unknown
                # semantics are additional investigation evidence, never an
                # excuse to hide a measured mismatch or missing target actor.
                flags.append("SOURCE_SEMANTIC_OR_DEPENDENCY_UNRESOLVED")
            else:
                status = "SOURCE_SEMANTIC_OR_DEPENDENCY_UNRESOLVED"
        if (kind == "entities" and status == "DIRECT_MEASURED_DIFFERENCE"
                and item["ced"] == "entity.character"
                and by_eid.get(direct_entity, {}).get("motion_diagnostic")
                == "INITIAL_PLACEMENT_OFFSET_DOMINATES"):
            repair_hint = "INSPECT_EXISTING_USER_AUTHORIZED_CHARACTER_OFFSET_POLICY"
        else:
            repair_hint = "DIAGNOSTIC_REVIEW_ONLY"
        output.append({
            "occurrence_id": item["occurrence_id"],
            "source_kind": kind,
            "ced": item["ced"] if item["state"] != "UNKNOWN_SEMANTIC_INVESTIGATE"
            else "unknown.unclassified",
            "measurement_status": status,
            "discrepancy_flags": sorted(set(flags)),
            "measured": metric,
            "bound_entity_occurrence": linked,
            "recovery_hint": repair_hint,
            "native_repair_authorized": False,
            "full_cutscene_fidelity_verified": False,
        })
    report = {
        "kind": "cutsceneai.studio.element_cinetwin_attribution",
        "schema_version": VERSION,
        "source_csir_sha256": conversion["source_csir_sha256"],
        "element_plan_sha256": conversion["element_plan_sha256"],
        "sampling_plan_sha256": _digest(sampling),
        "source_capture_sha256": _digest(source_capture),
        "target_capture_sha256": _digest(target_capture),
        "target_identity_sha256": _target_identity(target_capture),
        "cinetwin_comparison_sha256": _digest(comparison),
        "source_occurrence_count": len(output),
        "native_repair_authorized": False,
        "full_cutscene_fidelity_verified": False,
        "unverified_domains": sorted(set(comparison.get("unverified_domains", []))),
        "occurrences": output,
    }
    report["attribution_sha256"] = _digest(report)
    return report


def verify(report: dict, csir: dict, conversion: dict, sampling: dict,
           source_capture: dict, target_capture: dict) -> None:
    """Not a checksum-only gate: compare again from original raw captures."""
    if not isinstance(report, dict) or report != build(
        csir, conversion, sampling, source_capture, target_capture,
    ):
        raise ElementCineTwinError("CineTwin attribution is stale, incomplete or tampered.")


def _measured_progress(before: dict, after: dict) -> bool:
    """Compare only numeric native measurements, not a model's progress claim."""
    if set(before["discrepancy_flags"]) - set(after["discrepancy_flags"]):
        return True
    for key, threshold in (
        ("actor_position_cm", 0.01),
        ("actor_rotation_degrees", 0.1),
        ("camera_lens_error_degrees", 0.1),
    ):
        a = before["measured"].get(key)
        b = after["measured"].get(key)
        if (type(a) in (float, int) and type(b) in (float, int)
                and a - b >= threshold):
            return True
    if (before["measured"].get("skeletal_joint_status") == "FAIL"
            and after["measured"].get("skeletal_joint_status") == "PASS"):
        return True
    return False


def remeasure(csir: dict, conversion: dict, sampling: dict,
              source_capture: dict, target_captures: list[dict]) -> dict:
    """Recompare baseline + <=2 independent target observations (no writes).

    A later JSON snapshot is not proof that the engine was repaired. Distinct
    measured input is required; observations without an independently bound
    target project/sequence remain explicitly provenance-incomplete.
    """
    if (not isinstance(target_captures, list)
            or not 2 <= len(target_captures) <= MAX_REMEASURE_ATTEMPTS + 1):
        raise ElementCineTwinError(
            "Recovery requires a baseline and at most two new target captures."
        )
    reports = [build(csir, conversion, sampling, source_capture, capture)
               for capture in target_captures]
    target_digests = [report["target_capture_sha256"] for report in reports]
    if len(target_digests) != len(set(target_digests)):
        raise ElementCineTwinError(
            "A reused target capture cannot count as independent remeasurement."
        )
    identities = [report["target_identity_sha256"] for report in reports]
    if any(identities) and len(set(identities)) != 1:
        raise ElementCineTwinError("Remeasurement targets a different or unverified target sequence.")
    independent_identity = all(identities)
    records = []
    stop = False
    for idx, original in enumerate(reports[0]["occurrences"]):
        current = reports[-1]["occurrences"][idx]
        if (current["occurrence_id"] != original["occurrence_id"]
                or current["source_kind"] != original["source_kind"]):
            raise ElementCineTwinError("Remeasurement changed source occurrence identity.")
        had = original["measurement_status"] == "DIRECT_MEASURED_DIFFERENCE"
        ended = current["measurement_status"]
        prev = [report["occurrences"][idx] for report in reports]
        error_before = original["measured"].get("actor_position_cm")
        error_after = current["measured"].get("actor_position_cm")
        flags_before = set(original["discrepancy_flags"])
        flags_after = set(current["discrepancy_flags"])
        no_progress = had and not _measured_progress(original, prev[1])
        introduced = flags_after - flags_before
        if original["source_kind"] != "entities":
            result = "NOT_DIRECTLY_ATTESTABLE"
        elif not had:
            result = ("REGRESSED_AFTER_REMEASUREMENT" if ended == "DIRECT_MEASURED_DIFFERENCE"
                      else "NO_BASELINE_MEASURED_DIFFERENCE")
        elif no_progress:
            result = "STOP_REPEATED_NO_MEASURED_IMPROVEMENT"
        elif introduced:
            result = "REGRESSED_AFTER_REMEASUREMENT"
        elif ended == "DIRECT_MEASURED_NO_FLAGGED_DIFFERENCE":
            result = ("MEASURED_FLAGS_CLEARED_PERSISTENCE_UNVERIFIED"
                      if independent_identity else
                      "MEASURED_IMPROVEMENT_TARGET_PROVENANCE_INCOMPLETE")
        elif ended == "DIRECT_MEASURED_DIFFERENCE":
            result = "PARTIAL_OR_DIFFERENT_MEASURED_DISCREPANCY_REMAINS"
        else:
            result = "REMEASUREMENT_INCOMPLETE"
        if result in {"STOP_REPEATED_NO_MEASURED_IMPROVEMENT",
                      "REGRESSED_AFTER_REMEASUREMENT"}:
            stop = True
        records.append({
            "occurrence_id": original["occurrence_id"],
            "result": result,
            "baseline_discrepancy_flags": sorted(flags_before),
            "latest_discrepancy_flags": sorted(flags_after),
            "baseline_actor_position_error_cm": error_before,
            "latest_actor_position_error_cm": error_after,
            "native_repair_authorized": False,
            "full_cutscene_fidelity_verified": False,
        })
    if len(target_captures) - 1 >= MAX_REMEASURE_ATTEMPTS:
        stop = True
    if not any(row["result"] in {
        "PARTIAL_OR_DIFFERENT_MEASURED_DISCREPANCY_REMAINS"
    } for row in records):
        stop = True
    summary = {
        "kind": "cutsceneai.studio.element_cinetwin_remeasurement",
        "schema_version": VERSION,
        "source_csir_sha256": conversion["source_csir_sha256"],
        "element_plan_sha256": conversion["element_plan_sha256"],
        "sampling_plan_sha256": _digest(sampling),
        "source_capture_sha256": _digest(source_capture),
        "target_capture_sha256s": target_digests,
        "baseline_attribution_sha256": reports[0]["attribution_sha256"],
        "latest_attribution_sha256": reports[-1]["attribution_sha256"],
        "remeasurement_attempts": len(target_captures) - 1,
        "target_project_and_sequence_identity_claim_consistent": bool(independent_identity),
        "further_automatic_repair_or_retry_authorized": False,
        "next_attempt_recommended": not stop,
        "full_cutscene_fidelity_verified": False,
        "per_occurrence": records,
    }
    summary["remeasurement_sha256"] = _digest(summary)
    return summary


def verify_remeasurement(report: dict, csir: dict, conversion: dict,
                         sampling: dict, source_capture: dict,
                         target_captures: list[dict]) -> None:
    if not isinstance(report, dict) or report != remeasure(
        csir, conversion, sampling, source_capture, target_captures,
    ):
        raise ElementCineTwinError("CineTwin remeasurement was forged, stale or incomplete.")
