"""Revalidate and read back one AI-selected character strategy inside Unreal."""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

import animation_conversion_policy as policy
import studio_character_probe
import studio_ik_retarget
import studio_transfer_ai


def preflight(api, job: dict, decision: dict, mapping: dict, plan: dict, manifest: dict, *, worker: dict) -> dict:
    """Recompute the source report and re-observe the actual editor before mutation."""
    root = Path(job["candidate_dir"])
    report_file = root / policy.REPORT_FILE
    report = policy.compatibility.read_json(report_file)
    if (policy.compatibility.file_digest(report_file) != job.get("character_compatibility_sha256")
            or policy.compatibility.digest(report) != decision.get("character_compatibility_sha256")
            or not job.get("automatic_setup") or (root / policy.NATIVE_FILE).exists()):
        raise RuntimeError("Missing, stale, or already executed AI character candidate evidence.")
    context = report["context"]
    if (manifest["source_project"] != context["unity_project"] or manifest["source_scope"] != context["source_scope"]
            or job.get("expected_project") != context["unreal_project"]
            or job.get("expected_level") != context["destination_level"]
            or bool(job.get("create_level")) != context["create_level"]):
        raise RuntimeError("AI character source project, scope, or Unreal destination changed.")
    config = {"csir": job["csir"], "capture": job["capture"], "mapping": job["character_original_mapping"],
              "unity_project": manifest["source_project"], "source_scope": manifest["source_scope"],
              "target_project": job["expected_project"], "level_path": job["expected_level"],
              "auto_create_level": bool(job.get("create_level"))}
    original = policy.compatibility.read_json(Path(config["mapping"]))
    csir = policy.compatibility.read_json(Path(config["csir"]))
    request = policy.make_probe_request(config, csir, original, run_id=decision["character_probe_run_id"])
    observed = studio_character_probe.inspect(api, request, project=worker["project"], level=worker["level"])
    studio_transfer_ai.verify(decision, config, mapping["source_feature_surface_path"], worker,
                              native_character_probe=observed)
    choice = decision["animation_conversion"]
    row = policy.verify_plan(report, choice, mapping, plan, manifest)
    registry = api.EditorAssetLibrary
    if not callable(getattr(registry, 'does_directory_exist', None)):
        raise RuntimeError('Unreal package-directory inspection is unavailable for guarded character staging.')
    destinations = [job["sequence_path"]]
    for item in manifest["imports"]:
        destinations.append(item["target_asset_path"])
        if item.get("source_animation_path"):
            destinations.append(item["source_animation_path"])
    if (len({path.casefold() for path in destinations}) != len(destinations)
            or any(registry.does_asset_exist(path) for path in destinations)
            or registry.does_directory_exist(manifest["target_folder"])):
        raise RuntimeError("AI character conversion refuses an occupied or ambiguous asset destination.")
    if not job.get("create_level"):
        actors = api.get_editor_subsystem(api.EditorActorSubsystem).get_all_level_actors()
        existing = {str(actor.get_actor_label()).casefold() for actor in actors}
        if any(item["label"].casefold() in existing for item in manifest["actors"]):
            raise RuntimeError("AI character conversion refuses to reuse or overwrite existing target actors.")
    return row


def _path(asset) -> str:
    return str(asset.get_path_name()).split(".", 1)[0]


def _native_sections(api, sequence, actor) -> list[dict]:
    extensions = api.MovieSceneSequenceExtensions
    world = api.get_editor_subsystem(api.UnrealEditorSubsystem).get_editor_world()
    frequency = extensions.get_tick_resolution(sequence)
    ticks_per_second = float(frequency.numerator) / float(frequency.denominator)
    rows = []
    for binding in extensions.get_bindings(sequence):
        owners = list(extensions.locate_bound_objects(sequence, binding, world))
        if len(owners) != 1 or owners[0].get_path_name() != actor.get_path_name():
            continue
        for track in binding.get_tracks():
            if not isinstance(track, api.MovieSceneSkeletalAnimationTrack):
                continue
            for section in track.get_sections():
                params = section.get_editor_property("params")
                clip = params.get_editor_property("animation")
                rate = params.get_editor_property("play_rate")
                trim = params.get_editor_property("start_frame_offset")
                section_api = api.MovieSceneSectionExtensions
                rows.append({"clip": _path(clip), "start_frame": int(section_api.get_start_frame(section)),
                             "end_frame": int(section_api.get_end_frame(section)),
                             "clip_duration_seconds": float(clip.get_play_length()),
                             "time_scale": round(float(rate if isinstance(rate, (float, int)) else rate.to_fixed_play_rate()), 6),
                             "source_trim_ticks": int(trim if isinstance(trim, int) else trim.value),
                             "ticks_per_second": ticks_per_second})
    return rows


def record(api, job: dict, plan: dict, selected: dict, sequence, *, path: Path | None = None, reopened=False) -> dict:
    """Save the stage receipt after native asset and section readback."""
    report = {"kind": "cutsceneai.studio.character_native_readback", "schema_version": "1",
              "job_id": job["job_id"], "sequence_path": job["sequence_path"],
              "decision_file_sha256": job["ai_conversion_decision_sha256"],
              "compatibility_file_sha256": job["character_compatibility_sha256"],
              "source_entity_id": selected["source_entity_id"], "status": "INSUFFICIENT_EVIDENCE",
              "measured_scope": "NATIVE_SKELETON_AND_SECTION_READBACK", "reopened": bool(reopened),
              "target_playback_sample_status": "AWAITING_INDEPENDENT_CINETWIN", "fidelity_verified": False}
    try:
        api_actor = api.get_editor_subsystem(api.EditorActorSubsystem)
        actors = [a for a in api_actor.get_all_level_actors() if str(a.get_actor_label()) == selected["target_actor_label"]]
        if len(actors) != 1 or _path(sequence) != job["sequence_path"]:
            raise RuntimeError("Wrong candidate sequence or character actor in native readback.")
        actor, = actors
        expected = [a for a in plan["actions"] if a["kind"] == "skeletal_animation"
                    and a.get("entity_name") == selected["source_entity_name"]]
        clips = sorted({a["unreal_asset_path"] for a in expected})
        skeleton = studio_ik_retarget.inspect(api, selected["approved_profile"], clips, actor)
        sections = _native_sections(api, sequence, actor)
        tick_rate = sections[0]["ticks_per_second"] if sections else 1
        expected_ranges = Counter((row["unreal_asset_path"], row["start_frame"], row["end_frame"],
                                   round(row["time_scale"], 6), round(row["source_offset_seconds"] * tick_rate))
                                  for row in expected)
        observed_ranges = Counter((row["clip"], row["start_frame"], row["end_frame"],
                                   row["time_scale"], row["source_trim_ticks"]) for row in sections)
        source_clips = {row["planned_target_clip"]: row["timing"] for row in selected["clips"]}
        durations_match = all(row["clip"] in source_clips and math.isfinite(row["clip_duration_seconds"])
                              and math.isclose(row["clip_duration_seconds"], source_clips[row["clip"]]["duration_seconds"],
                                               rel_tol=0, abs_tol=1 / source_clips[row["clip"]]["source_fps"])
                              for row in sections)
        passed = skeleton["status"] == "PASS" and bool(expected_ranges) and expected_ranges == observed_ranges and durations_match
        report.update(status="PASS" if passed else "FAIL", skeleton=skeleton, observed_sections=sections,
                      expected_sections=[{"clip": key[0], "start_frame": key[1], "end_frame": key[2],
                                          "time_scale": key[3], "source_trim_ticks": key[4], "count": n}
                                         for key, n in sorted(expected_ranges.items())], duration_match=durations_match)
    except (KeyError, AttributeError, RuntimeError, ValueError, TypeError) as exc:
        report["reason"] = str(exc)
    output = path if path is not None else Path(job["candidate_dir"]) / policy.NATIVE_FILE
    with output.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
        handle.write("\n")
    return report
