"""Phase 10.2: exactly one two-shot camera switch boundary correction.

A multi-cut timing edit is safe only when every camera identity and BOTH outer
edges already agree with the independently reopened native capture. Exactly
two consecutive, non-overlapping source camera-cut sections are supported;
one shared boundary may drift by at most eight integer Sequencer frames.

The proof has NO native execution authority; the editor must recheck exact
newly staged camera object identity, live bindings and current consent.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import studio_camera_cut_evidence as single
import studio_element7_readback as readback
import studio_element8_repair as repair
import studio_element9_outcome as outcome

KIND = "cutsceneai.studio.two_shot_camera_boundary_review"
MAX_FRAME_SHIFT = single.MAX_FRAME_SHIFT
MAX_FRAME_INDEX = 2**30


class TwoShotEvidenceError(ValueError):
    """The two-shot switch or its source/native identity is not proven."""


def message_requests_two_shot(message: Any) -> bool:
    return bool(
        single.message_requests_cut(message)
        and not re.search(
            r"\b(?:single|one|all|every|many|multiple|third|three|"
            r"insert|remove|delete|add|replace|reorder|"
            r"retarget|binding|subsequence|nested|multi.track)\b",
            message, re.I,
        )
    )


def _exact_two(rows: Any, *, native: bool) -> list[dict]:
    if not isinstance(rows, list) or len(rows) != 2:
        raise TwoShotEvidenceError(
            "Only an exact two-shot schedule with one shared switch is supported."
        )
    result = []
    for row in rows:
        if not isinstance(row, dict):
            raise TwoShotEvidenceError("Invalid camera-cut source/native section.")
        first, last = row.get("start_frame"), row.get("end_frame")
        if (type(first) is not int or type(last) is not int
                or first < 0 or first >= last or last > MAX_FRAME_INDEX
                or (not native and (
                    row.get("status") != "FRAME_ALIGNED"
                    or not isinstance(row.get("source_section_id"), str)
                    or not row.get("source_section_id")
                ))):
            raise TwoShotEvidenceError(
                "Unverified or subframe camera-cut boundary is not repairable."
            )
        result.append(row)
    result.sort(key=lambda r: (r["start_frame"], r["end_frame"]))
    if (result[0]["end_frame"] != result[1]["start_frame"]
            or result[0]["start_frame"] == result[1]["start_frame"]):
        raise TwoShotEvidenceError(
            "Source/native cuts must be contiguous, gap-free and non-overlapping."
        )
    return result


def build(workspace: Path, job: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(job, dict):
        raise TwoShotEvidenceError("One exact Studio native job is required.")
    try:
        root, candidate, current, csir, mapping, _ = outcome._context(
            workspace, job.get("job_id"),
        )
        if current != job:
            raise TwoShotEvidenceError("Native camera job changed since preparation.")
        folders = outcome.discover(root, job["job_id"])
        if not folders:
            raise TwoShotEvidenceError("Independent reopened native cut capture missing.")
        last = folders[-1]
        bounded = repair.build(root, job["job_id"], folders)
        native = readback.build(root, job["job_id"], last)
        sampling, _ = readback._safe_json(last / "sampling-plan.json")
        target, _ = readback._safe_json(last / "target-behavior.json")
    except TwoShotEvidenceError:
        raise
    except (readback.Element7ReadbackError, repair.BoundedRepairError,
            outcome.OutcomeError, OSError, ValueError, KeyError, TypeError) as exc:
        raise TwoShotEvidenceError(
            "The exact source-bound native two-shot evidence is missing or stale."
        ) from exc
    if (bounded.get("status") in {
            "STOP_MEASURED_REGRESSION_OR_NO_PROGRESS",
            "STOP_REMEASUREMENT_BUDGET_EXHAUSTED",
        }
            or native.get("native_attempt", {}).get("native_builder_completed") is not True
            or native.get("distinct_reopened_editor_observed") is not True
            or native.get("camera_cuts_status") != "FAIL"
            or native.get("camera_lens_status") != "PASS"):
        raise TwoShotEvidenceError(
            "No independently verified isolated native cut-timing discrepancy."
        )
    observed = target.get("camera_cut_sections")
    if (not isinstance(observed, dict)
            or observed.get("status") != "OBSERVED"
            or observed.get("binding_provenance")
            != "NATIVE_SEQUENCE_CAMERA_BINDING_ID"):
        raise TwoShotEvidenceError(
            "Native two-shot camera binding provenance is missing."
        )
    source = _exact_two(sampling.get("camera_cuts"), native=False)
    measured = _exact_two(observed.get("sections"), native=True)
    # A true two-shot source schedule has exactly TWO distinct cameras and
    # one camera-cut authored section per track. Ignore no muted unknown track:
    # ambiguous source owners are forbidden, even if sampling omits them.
    source_tracks = [t for t in csir.get("tracks", [])
                     if isinstance(t, dict) and t.get("ced_type") == "camera.cut"]
    if (len(source_tracks) != 2 or any(
            t.get("muted") is True
            or len(t.get("sections", [])) != 1
            for t in source_tracks
    ) or len({t.get("track_id") for t in source_tracks}) != 2
            or len({t.get("binding_entity_id") for t in source_tracks}) != 2):
        raise TwoShotEvidenceError(
            "Source has ambiguous, muted, repeated or nested cut ownership."
        )
    cameras = []
    camera_entities = [e for e in csir.get("entities", [])
                       if isinstance(e, dict) and e.get("ced_type") == "entity.camera"]
    for i, (src, dst) in enumerate(zip(source, measured)):
        ident = src.get("source_entity_id")
        matching = [e for e in camera_entities if e.get("entity_id") == ident]
        if len(matching) != 1:
            raise TwoShotEvidenceError("Source shot camera identity is not unique.")
        name = matching[0].get("name")
        mapping_entry = (mapping.get("entities") or {}).get(name)
        label = mapping_entry.get("actor_label") if isinstance(mapping_entry, dict) else None
        if (not isinstance(name, str) or not name or len(name) > 128
                or not isinstance(label, str) or not label or len(label) > 256
                or dst.get("actor_label") != label
                or (src.get("source_section_id")
                    != source_tracks[0 if source_tracks[0].get("binding_entity_id")
                                     == ident else 1].get("sections", [{}])[0].get(
                                         "section_id"))):
            raise TwoShotEvidenceError(
                "Source section identity or native camera binding differs."
            )
        cameras.append({
            "source_entity_id": ident,
            "source_camera_name": name,
            "target_actor_label": label,
            "source_section_id_sha256": single._hash(src["source_section_id"]),
            "expected_start_frame": src["start_frame"],
            "expected_end_frame": src["end_frame"],
            "native_start_frame": dst["start_frame"],
            "native_end_frame": dst["end_frame"],
        })
    if (cameras[0]["source_entity_id"] == cameras[1]["source_entity_id"]
            or cameras[0]["target_actor_label"] == cameras[1]["target_actor_label"]):
        raise TwoShotEvidenceError(
            "Source switch must connect exactly two unique approved cameras."
        )
    if (source[0]["start_frame"] != measured[0]["start_frame"]
            or source[1]["end_frame"] != measured[1]["end_frame"]):
        raise TwoShotEvidenceError(
            "Outer shot start/end frames differ; only one shared switch is editable."
        )
    delta = source[0]["end_frame"] - measured[0]["end_frame"]
    if not 1 <= abs(delta) <= MAX_FRAME_SHIFT:
        raise TwoShotEvidenceError(
            "Shared switch is aligned or differs by too many frames."
        )
    report = {
        "kind": KIND,
        "eligible": True,
        "camera_count": 2,
        "switch_count": 1,
        "maximum_frame_boundary_error": abs(delta),
        "job_id_sha256": single._hash(job["job_id"]),
        "shots": cameras,
        "element7_readback_sha256": native["readback_sha256"],
        "element8_repair_sha256": bounded["repair_plan_sha256"],
        "native_edit_authorized": False,
        "model_can_supply_frame_values": False,
        "rendered_camera_switching_verified": False,
        "full_cutscene_fidelity_verified": False,
    }
    report["two_shot_cut_repair_sha256"] = single._hash(report)
    return report
