"""Single native camera-cut section frame-boundary repair (guarded).

Requires user feedback, exact source CSIR and original saved CineTwin target
capture, exactly one camera-cut track and section, unchanged native binding,
one newly staged source camera, no subsequences, and <=8 frame correction.

Never changes cut bindings, adds/deletes sections, edits subscenes or animation,
overwrites a separate sequence, retries a native generation, or claims render
equivalence. Native section re-read happens immediately; independent reopened
CineTwin remains REQUIRED after save.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT / "packages" / "studio", ROOT / "integrations" / "unreal"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import cinetwin_camera_cuts
import studio_camera_cut_evidence as evidence


class CameraCutRepairError(ValueError):
    """Native camera-cut section cannot be safely edited in this editor."""


def _load(path: Path) -> dict:
    return evidence.readback._safe_json(path)[0]


def _get_exact_section(api: Any, sequence: Any) -> Any:
    get_tracks = getattr(
        getattr(api, "MovieSceneSequenceExtensions", None), "get_tracks", None,
    )
    class_type = getattr(api, "MovieSceneCameraCutTrack", None)
    if class_type is None or not callable(get_tracks):
        raise CameraCutRepairError("Unreal has no verified camera-cut track inspection.")
    try:
        tracks = list(get_tracks(sequence))
        if len(tracks) > 1000:
            raise CameraCutRepairError("Native Sequencer track list is unsafe.")
        for track in tracks:
            name = str(track.get_class().get_name())
            if ("SubTrack" in name or "CinematicShot" in name):
                raise CameraCutRepairError(
                    "Nested shots require a separate source-bound adapter."
                )
        cuts = [row for row in tracks if isinstance(row, class_type)]
        if len(cuts) != 1:
            raise CameraCutRepairError("One native camera-cut track is required.")
        sections = list(cuts[0].get_sections())
        if len(sections) != 1:
            raise CameraCutRepairError("Only one native cut section is eligible.")
        return sections[0]
    except CameraCutRepairError:
        raise
    except (AttributeError, TypeError, RuntimeError, ValueError) as exc:
        raise CameraCutRepairError(
            "Native Sequencer cut track structure could not be inspected."
        ) from exc


def _observed_one(api: Any, sequence: Any, label: str) -> tuple[int, int]:
    sample = cinetwin_camera_cuts.inspect(sequence, api)
    rows = sample.get("sections")
    if (sample.get("status") != "OBSERVED"
            or sample.get("binding_provenance")
            != "NATIVE_SEQUENCE_CAMERA_BINDING_ID"
            or not isinstance(rows, list) or len(rows) != 1
            or rows[0].get("actor_label") != label):
        raise CameraCutRepairError(
            "Saved Sequencer camera-cut binding identity was not observed."
        )
    first = rows[0].get("start_frame")
    last = rows[0].get("end_frame")
    if (type(first) is not int or type(last) is not int
            or first < 0 or last <= first):
        raise CameraCutRepairError("Native camera cut has invalid frame bounds.")
    return first, last


def attempt(api: Any, workspace: Path, job: dict, request: dict) -> dict:
    candidate = Path(job["candidate_dir"]).resolve()
    if request.get("strategy") != "restore_single_camera_cut_timing":
        raise CameraCutRepairError("Wrong native camera-cut repair strategy.")
    feedback_id = str(request.get("feedback_id") or "")
    if re.fullmatch(r"[a-f0-9]{32}", feedback_id) is None:
        raise CameraCutRepairError("An explicit current camera-cut user request is required.")
    active = _load(candidate / ("user-feedback-active-" + job["job_id"] + ".json"))
    comment = _load(candidate / ("user-feedback-" + feedback_id + ".json"))
    if (active.get("feedback_id") != feedback_id
            or active.get("job_id") != job["job_id"]
            or active.get("candidate_id") != job["candidate_id"]
            or comment.get("kind") != "cutsceneai.studio.user_feedback"
            or comment.get("feedback_id") != feedback_id
            or comment.get("job_id") != job["job_id"]
            or comment.get("candidate_id") != job["candidate_id"]
            or not evidence.message_requests_cut(comment.get("message"))):
        raise CameraCutRepairError("Stale or unapproved camera-cut user feedback.")
    proof = evidence.build(workspace, job)
    if request.get("camera_cut_repair_sha256") != proof["camera_cut_repair_sha256"]:
        raise CameraCutRepairError(
            "The native camera-cut evidence changed since source-bound AI review."
        )
    setup = Path(str(job.get("setup_receipt_file") or "")).resolve()
    if (setup.is_symlink() or setup.parent != candidate or not setup.is_file()):
        raise CameraCutRepairError("Exact newly staged CineCamera receipt missing.")
    created = [
        row for row in _load(setup).get("actors_created", [])
        if isinstance(row, dict)
        and row.get("kind") == "entity.camera"
        and row.get("name") == proof["source_camera_name"]
        and row.get("label") == proof["target_camera_actor_label"]
    ]
    if len(created) != 1:
        raise CameraCutRepairError(
            "Only the original newly staged source camera may own the cut."
        )
    sequence = api.load_asset(job["sequence_path"])
    if sequence is None:
        raise CameraCutRepairError("Source-bound native Level Sequence is missing.")
    section = _get_exact_section(api, sequence)
    before = _observed_one(api, sequence, proof["target_camera_actor_label"])
    if before != (proof["native_start_frame"], proof["native_end_frame"]):
        raise CameraCutRepairError("The native camera cut moved after source capture.")
    start = proof["expected_start_frame"]
    end = proof["expected_end_frame"]
    if end <= start:
        raise CameraCutRepairError("The proposed source camera cut is not a valid interval.")
    changed = False
    saved = False
    try:
        changed = True
        section.set_range(start, end)
        after = _observed_one(
            api, sequence, proof["target_camera_actor_label"],
        )
        if after != (start, end):
            raise CameraCutRepairError(
                "Native camera-cut readback differs from source-authored frames."
            )
        editor_assets = getattr(api, "EditorAssetLibrary", None)
        save = getattr(editor_assets, "save_loaded_asset", None)
        if not callable(save) or save(sequence) is not True:
            raise CameraCutRepairError(
                "Native Level Sequence save did not return a verified success."
            )
        saved = True
        return {
            "status": "CAMERA_SINGLE_CUT_SECTION_SAVED_REOPENED_CINETWIN_PENDING",
            "camera_cut_repair_sha256": proof["camera_cut_repair_sha256"],
            "target_entity": proof["source_camera_name"],
            "changes": 1,
            "native_cut_before": list(before),
            "native_cut_after": list(after),
            "native_section_binding_readback_verified": True,
            "persistence_after_editor_restart_verified": False,
            "cinetwin_reopened_time_grid_verified_after_repair": False,
            "rendered_camera_switching_verified": False,
            "full_cutscene_fidelity_verified": False,
        }
    finally:
        if changed and not saved:
            # Do not leave an unverified unsaved timeline modification.
            section.set_range(*before)
