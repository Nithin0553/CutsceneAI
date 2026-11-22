"""Exact two-shot native Sequencer boundary repair, with atomic-ish rollback.

Only one shared switch between two already-bound newly staged cameras is
corrected. No section is inserted/deleted, no binding modified and no
subsequence, nested shot, camera animation, skeletal track or event rewritten.
Editor APIs and independent reopened CineTwin MUST still be real-engine tested.

Unreal is NOT a database: two setter calls are not atomic. Edits are ordered
to create at most a transient gap, never an overlapping camera cut, and both
original sections are restored if either call/readback/save fails. A failed
disk save is not proof that persisted state was rolled back.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
for path in (ROOT / "packages/studio", ROOT / "integrations/unreal"):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import cinetwin_camera_cuts
import studio_two_shot_cut_evidence as evidence


class TwoShotNativeRepairError(ValueError):
    """Two-shot native binding, frame or editor ownership is unverified."""


def _load(path: Path) -> dict:
    return evidence.readback._safe_json(path)[0]


def _section_range(api: Any, section: Any) -> tuple[int, int]:
    extensions = getattr(api, "MovieSceneSectionExtensions", None)
    if (not callable(getattr(extensions, "get_start_frame", None))
            or not callable(getattr(extensions, "get_end_frame", None))):
        raise TwoShotNativeRepairError(
            "Native section boundary API unavailable."
        )
    try:
        first = extensions.get_start_frame(section)
        last = extensions.get_end_frame(section)
        first = getattr(first, "value", first)
        last = getattr(last, "value", last)
        if (type(first) is not int or type(last) is not int
                or first < 0 or first >= last
                or last > evidence.MAX_FRAME_INDEX):
            raise TwoShotNativeRepairError(
                "Native cut has invalid or subframe boundaries."
            )
        return first, last
    except TwoShotNativeRepairError:
        raise
    except (AttributeError, TypeError, RuntimeError, ValueError) as exc:
        raise TwoShotNativeRepairError(
            "Native camera-cut section readback failed."
        ) from exc


def _native_sections(api: Any, sequence: Any) -> tuple[Any, Any]:
    ext = getattr(api, "MovieSceneSequenceExtensions", None)
    klass = getattr(api, "MovieSceneCameraCutTrack", None)
    if (klass is None or not callable(getattr(ext, "get_tracks", None))
            or not callable(getattr(ext, "get_bindings", None))):
        raise TwoShotNativeRepairError(
            "Complete native camera-cut Sequencer inventory unavailable."
        )
    try:
        root = list(ext.get_tracks(sequence))
        bindings = list(ext.get_bindings(sequence))
        if not 1 <= len(root) <= 1000 or len(bindings) > 10000:
            raise TwoShotNativeRepairError("Native track inventory is unbounded.")
        cameras = [track for track in root if isinstance(track, klass)]
        if len(cameras) != 1:
            raise TwoShotNativeRepairError(
                "One native camera-cut master track required."
            )
        # A nested shot or time-remapping owner may change how section
        # boundaries are evaluated. Unknown master tracks are not trusted.
        for track in root:
            if str(track.get_class().get_name()) != "MovieSceneCameraCutTrack":
                raise TwoShotNativeRepairError(
                    "Other master track may own the camera-cut time base."
                )
        for binding in bindings:
            tracks = list(binding.get_tracks())
            if len(tracks) > 1000:
                raise TwoShotNativeRepairError(
                    "Nested native bound track inventory is unbounded."
                )
            for track in tracks:
                name = str(track.get_class().get_name())
                if ("SubTrack" in name or "CinematicShot" in name
                        or "TimeWarp" in name or "TimeDilation" in name):
                    raise TwoShotNativeRepairError(
                        "Nested or warped shot timing is not source-proven."
                    )
        sections = list(cameras[0].get_sections())
        if len(sections) != 2:
            raise TwoShotNativeRepairError(
                "Native Sequence no longer contains exactly two cut sections."
            )
        measured = sorted(
            [(section, _section_range(api, section)) for section in sections],
            key=lambda row: (row[1][0], row[1][1]),
        )
        if measured[0][1][1] != measured[1][1][0]:
            raise TwoShotNativeRepairError(
                "Native two-shot source boundary is no longer contiguous."
            )
        return measured[0][0], measured[1][0]
    except TwoShotNativeRepairError:
        raise
    except (AttributeError, TypeError, RuntimeError, ValueError) as exc:
        raise TwoShotNativeRepairError(
            "Native Sequencer two-shot section ownership unobservable."
        ) from exc


def _observed(api: Any, sequence: Any, shots: list[dict], *,
              expected_key: str) -> tuple[tuple[int, int], tuple[int, int]]:
    sample = cinetwin_camera_cuts.inspect(sequence, api)
    rows = sample.get("sections")
    if (sample.get("status") != "OBSERVED"
            or sample.get("binding_provenance")
            != "NATIVE_SEQUENCE_CAMERA_BINDING_ID"
            or not isinstance(rows, list) or len(rows) != 2):
        raise TwoShotNativeRepairError(
            "Native source-mapped camera binding cannot be observed."
        )
    before = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise TwoShotNativeRepairError("Native camera section is malformed.")
        shot = shots[i]
        if row.get("actor_label") != shot["target_actor_label"]:
            raise TwoShotNativeRepairError(
                "Reopened native section/camera pairing changed."
            )
        times = (row.get("start_frame"), row.get("end_frame"))
        if (any(type(x) is not int for x in times)
                or times != (
                    shot[expected_key + "_start_frame"],
                    shot[expected_key + "_end_frame"],
                )):
            raise TwoShotNativeRepairError(
                "Native section frames differ from the exact source-bound report."
            )
        before.append(times)
    if before[0][1] != before[1][0]:
        raise TwoShotNativeRepairError(
            "Native camera-cut switch no longer has one shared boundary."
        )
    return before[0], before[1]


def _live_staged_cameras(api: Any, created: list[dict],
                         shots: list[dict]) -> None:
    actor_cls = getattr(api, "EditorActorSubsystem", None)
    if actor_cls is None:
        raise TwoShotNativeRepairError(
            "Native staged camera object identity inventory unavailable."
        )
    try:
        level = api.get_editor_subsystem(actor_cls)
        actors = list(level.get_all_level_actors())
        if len(actors) > 10000:
            raise TwoShotNativeRepairError("Native actor inventory is unbounded.")
        for shot in shots:
            label = shot["target_actor_label"]
            matching = [row for row in created
                        if isinstance(row, dict)
                        and row.get("kind") == "entity.camera"
                        and row.get("name") == shot["source_camera_name"]
                        and row.get("label") == label]
            actors_named = [actor for actor in actors
                            if str(actor.get_actor_label()) == label]
            if len(matching) != 1 or len(actors_named) != 1:
                raise TwoShotNativeRepairError(
                    "Newly staged native camera mapping is ambiguous."
                )
            expected = matching[0].get("native_actor_path")
            actor = actors_named[0]
            path = getattr(actor, "get_path_name", None)
            if (not isinstance(expected, str)
                    or not expected.startswith("/Game/")
                    or len(expected) > 1024 or not callable(path)
                    or str(path()) != expected
                    or str(actor.get_class().get_name()) != "CineCameraActor"):
                raise TwoShotNativeRepairError(
                    "Live CineCamera UObject differs from newly staged source identity."
                )
    except TwoShotNativeRepairError:
        raise
    except (AttributeError, TypeError, RuntimeError, ValueError) as exc:
        raise TwoShotNativeRepairError(
            "Live native staged-camera object identity unavailable."
        ) from exc


def _verify_exact_bound_camera_objects(
        api: Any, sequence: Any, sections: tuple[Any, Any],
        shots: list[dict], staged_rows: list[dict]) -> None:
    """Resolve camera-cut binding GUIDs to the SAME two staged UObject paths.

    A display label or an independently resolved section interval does not
    prove the native binding owner is the source-created camera. This must be
    verified in the active editor world before any section setter.
    """
    ext = getattr(api, "MovieSceneSequenceExtensions", None)
    lookup = getattr(ext, "get_bindings", None)
    locate = getattr(ext, "locate_bound_objects", None)
    binding_id = getattr(ext, "get_binding_id", None)
    editor_type = getattr(api, "UnrealEditorSubsystem", None)
    if (editor_type is None or not all(callable(x) for x in (
            lookup, locate, binding_id))):
        raise TwoShotNativeRepairError(
            "Native two-shot binding-to-staged-object API is unavailable."
        )
    try:
        bindings = list(lookup(sequence))
        if not 1 <= len(bindings) <= 10000:
            raise TwoShotNativeRepairError(
                "Native binding-to-camera inventory is unbounded."
            )
        world = api.get_editor_subsystem(editor_type).get_editor_world()
        for section, shot in zip(sections, shots):
            expected_rows = [row for row in staged_rows
                             if isinstance(row, dict)
                             and row.get("kind") == "entity.camera"
                             and row.get("name") == shot["source_camera_name"]
                             and row.get("label") == shot["target_actor_label"]]
            if len(expected_rows) != 1:
                raise TwoShotNativeRepairError(
                    "Exact source staging receipt has ambiguous camera objects."
                )
            expected_path = expected_rows[0].get("native_actor_path")
            section_id = section.get_camera_binding_id()
            matches = [row for row in bindings
                       if binding_id(sequence, row) == section_id]
            if len(matches) != 1:
                raise TwoShotNativeRepairError(
                    "Native two-shot section binding ID is ambiguous."
                )
            owners = list(locate(sequence, matches[0], world))
            if len(owners) != 1:
                raise TwoShotNativeRepairError(
                    "Native cut binding does not resolve to one staged camera."
                )
            bound = owners[0]
            if (str(bound.get_path_name()) != expected_path
                    or str(bound.get_actor_label())
                    != shot["target_actor_label"]
                    or str(bound.get_class().get_name()) != "CineCameraActor"):
                raise TwoShotNativeRepairError(
                    "Native camera-cut GUID binds a different UObject than staged."
                )
    except TwoShotNativeRepairError:
        raise
    except (AttributeError, TypeError, RuntimeError, ValueError) as exc:
        raise TwoShotNativeRepairError(
            "Cannot independently resolve native two-shot binding objects."
        ) from exc


def attempt(api: Any, workspace: Path, job: dict, request: dict) -> dict:
    candidate = Path(job["candidate_dir"]).resolve()
    if request.get("strategy") != "restore_two_shot_camera_switch":
        raise TwoShotNativeRepairError("Wrong native two-shot repair strategy.")
    fid = str(request.get("feedback_id") or "")
    if re.fullmatch(r"[a-f0-9]{32}", fid) is None:
        raise TwoShotNativeRepairError(
            "Current explicit camera-cut feedback ID is required."
        )
    active = _load(candidate / ("user-feedback-active-" + job["job_id"] + ".json"))
    message = _load(candidate / ("user-feedback-" + fid + ".json"))
    if (active.get("feedback_id") != fid
            or active.get("job_id") != job["job_id"]
            or active.get("candidate_id") != job["candidate_id"]
            or message.get("kind") != "cutsceneai.studio.user_feedback"
            or message.get("feedback_id") != fid
            or message.get("job_id") != job["job_id"]
            or message.get("candidate_id") != job["candidate_id"]
            or not evidence.message_requests_two_shot(message.get("message"))):
        raise TwoShotNativeRepairError(
            "Stale or unrelated camera-switch user consent."
        )
    proof = evidence.build(workspace, job)
    if request.get("two_shot_cut_repair_sha256") != proof["two_shot_cut_repair_sha256"]:
        raise TwoShotNativeRepairError(
            "Source camera-switch proof changed after agent review."
        )
    setup = Path(str(job.get("setup_receipt_file") or ""))
    if (setup.is_symlink() or not setup.is_file()
            or setup.resolve().parent != candidate):
        raise TwoShotNativeRepairError(
            "Exact newly staged CineCamera receipt missing."
        )
    rows = _load(setup).get("actors_created")
    if not isinstance(rows, list):
        raise TwoShotNativeRepairError(
            "Newly staged native camera actor inventory missing."
        )
    _live_staged_cameras(api, rows, proof["shots"])
    sequence = api.load_asset(job["sequence_path"])
    if sequence is None:
        raise TwoShotNativeRepairError("Source-bound native Level Sequence missing.")
    first, second = _native_sections(api, sequence)
    _verify_exact_bound_camera_objects(
        api, sequence, (first, second), proof["shots"], rows,
    )
    originals = _observed(api, sequence, proof["shots"], expected_key="native")
    expected = (
        (proof["shots"][0]["expected_start_frame"],
         proof["shots"][0]["expected_end_frame"]),
        (proof["shots"][1]["expected_start_frame"],
         proof["shots"][1]["expected_end_frame"]),
    )
    if (_section_range(api, first) != originals[0]
            or _section_range(api, second) != originals[1]
            or originals[0][0] != expected[0][0]
            or originals[1][1] != expected[1][1]
            or expected[0][1] != expected[1][0]):
        raise TwoShotNativeRepairError(
            "Native two-shot section objects changed after bound readback."
        )
    old_switch = originals[0][1]
    new_switch = expected[0][1]
    changed = False
    saved = False
    try:
        # The first setter can mutate before raising; mark rollback needed
        # before calling it, not after. Move the boundary on the shrinking
        # section FIRST so no transient overlapping camera cuts are created.
        changed = True
        if new_switch > old_switch:
            second.set_range(new_switch, originals[1][1])
            first.set_range(originals[0][0], new_switch)
        else:
            first.set_range(originals[0][0], new_switch)
            second.set_range(new_switch, originals[1][1])
        if (_section_range(api, first) != expected[0]
                or _section_range(api, second) != expected[1]):
            raise TwoShotNativeRepairError(
                "Edited native section bounds differ from approved switch."
            )
        after = _observed(api, sequence, proof["shots"], expected_key="expected")
        if after != expected:
            raise TwoShotNativeRepairError(
                "Native two-shot binding readback changed after repair."
            )
        save = getattr(getattr(api, "EditorAssetLibrary", None),
                       "save_loaded_asset", None)
        if not callable(save) or save(sequence) is not True:
            raise TwoShotNativeRepairError(
                "Native two-shot Level Sequence save was not verified."
            )
        saved = True
        return {
            "status": "TWO_SHOT_SWITCH_SAVED_REOPENED_CINETWIN_PENDING",
            "two_shot_cut_repair_sha256": proof["two_shot_cut_repair_sha256"],
            "changes": 2,
            "source_camera_count": 2,
            "native_switch_frame_before": old_switch,
            "native_switch_frame_after": new_switch,
            "native_section_binding_readback_verified": True,
            "native_shot_order_preserved": True,
            "persistence_after_editor_restart_verified": False,
            "cinetwin_reopened_time_grid_verified_after_repair": False,
            "rendered_camera_switching_verified": False,
            "full_cutscene_fidelity_verified": False,
        }
    finally:
        if changed and not saved:
            try:
                # Original frames and bindings are independently inspected
                # after rollback. A disk-write failure still requires a
                # separate editor reopen before claiming saved persistence.
                # Rollback also shrinks before extending so a failed
                # two-section correction never *intentionally* creates
                # an overlapping camera cut during compensation.
                if old_switch > new_switch:
                    second.set_range(*originals[1])
                    first.set_range(*originals[0])
                else:
                    first.set_range(*originals[0])
                    second.set_range(*originals[1])
                if (_section_range(api, first) != originals[0]
                        or _section_range(api, second) != originals[1]
                        or _observed(
                            api, sequence, proof["shots"], expected_key="native"
                        ) != originals):
                    raise TwoShotNativeRepairError(
                        "Two-shot rollback could not be verified."
                    )
            except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
                raise TwoShotNativeRepairError(
                    "Two-shot rollback is unverified; inspect editor manually."
                ) from exc
