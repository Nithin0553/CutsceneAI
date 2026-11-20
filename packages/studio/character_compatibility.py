"""Bounded, local evidence for Unity character animation compatibility."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter
from pathlib import Path

import csir_plan
import character_motion
import animation_format_policy
import sampling_plan
from studio_source_identity import GUID, resolve

REPORT = "cutsceneai.studio.character_compatibility_report"
PROFILE_CATALOG = "cutsceneai.studio.approved_animation_profiles"
PROFILE_FILE = Path("Config/CutSceneAI/AnimationProfiles.json")
PACKAGE_PATH = re.compile(r"/Game(?:/[A-Za-z0-9_]+)+")
SHA256 = re.compile(r"[a-f0-9]{64}")
PATH_FIELDS = ("source_mesh_path", "target_mesh_path", "retargeter_path")
MAX_CHARACTERS = 32
MAX_SECTIONS = 64
MAX_ASSET_BYTES = 512 * 1024 * 1024
MAX_METADATA_BYTES = 4 * 1024 * 1024
STILL_CM = character_motion.STILL_CM
STILL_DEGREES = character_motion.STILL_DEGREES


class CompatibilityError(ValueError):
    pass


def read_json(path: Path, limit=64 * 1024 * 1024) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
        raise CompatibilityError("Missing or out-of-bounds animation evidence.")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise CompatibilityError("Expected an animation evidence object.")
    return data


def file_digest(path: Path, limit=MAX_ASSET_BYTES) -> str:
    if path.is_symlink() or not path.is_file() or not 0 < path.stat().st_size <= limit:
        raise CompatibilityError("File is missing, unsafe, empty, or exceeds the animation evidence limit.")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def digest(value: object) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def package_files(project: Path, path: str) -> dict:
    """Recheck the exact probed packages on the host as well as in Unreal."""
    if not PACKAGE_PATH.fullmatch(path):
        raise CompatibilityError("Unsafe or external Unreal package path.")
    content = project.parent / "Content"
    base = content / path.removeprefix("/Game/")
    if not base.resolve().is_relative_to(content):
        raise CompatibilityError("Unreal package resolves outside project Content.")
    files = {".uasset": file_digest(base.with_suffix(".uasset"))}
    for suffix in (".uexp", ".ubulk"):
        sidecar = base.with_suffix(suffix)
        if sidecar.exists() or sidecar.is_symlink():
            files[suffix] = file_digest(sidecar)
    return files


def approved_profiles(project: Path, source_fingerprint: str) -> tuple[str | None, dict]:
    path = project.parent / PROFILE_FILE
    if not path.exists() and not path.is_symlink():
        return None, {}
    if not path.resolve().is_relative_to(project.parent.resolve()):
        raise CompatibilityError("The approved profile catalog escapes the selected Unreal project.")
    data = read_json(path, 64 * 1024)
    if (data.get("kind") != PROFILE_CATALOG or data.get("schema_version") != "1"
            or not isinstance(data.get("profiles"), list) or len(data["profiles"]) > 16):
        raise CompatibilityError("Invalid locally approved animation profile catalog.")
    fields = {"unity_project_fingerprint", "source_entity_id", "source_fbx_sha256", *PATH_FIELDS}
    seen = set()
    profiles = {}
    for profile in data["profiles"]:
        if (not isinstance(profile, dict) or set(profile) != fields
                or not all(isinstance(x, str) and 0 < len(x) <= 512 for x in profile.values())
                or not SHA256.fullmatch(profile["source_fbx_sha256"])
                or not all(PACKAGE_PATH.fullmatch(profile[key]) for key in PATH_FIELDS)
                or len({profile[key].casefold() for key in PATH_FIELDS}) != 3):
            raise CompatibilityError("Invalid approved source FBX or Unreal rig asset reference.")
        identity = profile["unity_project_fingerprint"], profile["source_entity_id"]
        if identity in seen:
            raise CompatibilityError("Ambiguous approved animation profiles for one Unity character.")
        seen.add(identity)
        if identity[0] == source_fingerprint:
            profiles[identity[1]] = {key: profile[key] for key in ("source_fbx_sha256", *PATH_FIELDS)}
    return file_digest(path, 64 * 1024), profiles


def input_context(config: dict, csir: dict) -> tuple[dict, dict]:
    project = Path(config["target_project"]).resolve()
    unity_root = Path(config["unity_project"]).resolve()
    scope = str(config["source_scope"]).replace("\\", "/")
    scope_parts = scope.split("/")
    if (scope_parts[0] != "Assets" or any(part in ("", ".", "..") for part in scope_parts)
            or not (unity_root / scope).resolve().is_relative_to(unity_root / "Assets")
            or not (unity_root / scope).is_dir()):
        raise CompatibilityError("Animation source scope must be inside the selected Unity Assets tree.")
    fingerprint = str(csir.get("source", {}).get("project_fingerprint") or "")
    profile_sha, profiles = approved_profiles(project, fingerprint) if fingerprint else (None, {})
    context = {
        "unity_project_fingerprint": fingerprint, "unity_project": str(unity_root), "source_scope": scope,
        "unreal_project": str(project), "uproject_sha256": file_digest(project, 4 * 1024 * 1024),
        "destination_level": config["level_path"], "create_level": bool(config.get("auto_create_level")),
        "profile_catalog_sha256": profile_sha,
    }
    return context, profiles


def _asset(context: dict, record: dict, suffix: str) -> dict:
    path, guid = record.get("asset_path"), record.get("guid")
    if not isinstance(path, str) or not isinstance(guid, str) or not GUID.fullmatch(guid):
        return {"status": "MISSING_UNITY_PATH_OR_GUID"}
    parts = path.replace("\\", "/").split("/")
    if parts[0] != "Assets" or any(part in ("", ".", "..") for part in parts):
        return {"status": "OUTSIDE_SELECTED_SOURCE_SCOPE"}
    if Path(parts[-1]).suffix.lower() != suffix:
        return {"status": "UNSUPPORTED_UNITY_ASSET_FORMAT", "asset_path": path, "guid": guid.lower()}
    root = Path(context["unity_project"])
    original = root.joinpath(*parts)
    source = original.resolve()
    meta = original.with_name(original.name + ".meta")
    if (original != source or meta.is_symlink()
            or not source.is_relative_to((root / context["source_scope"]).resolve())):
        return {"status": "OUTSIDE_SELECTED_SOURCE_SCOPE"}
    if not source.is_file() or not meta.is_file():
        return {"status": "UNITY_ASSET_OR_META_MISSING", "asset_path": path, "guid": guid.lower()}
    if meta.stat().st_size > MAX_METADATA_BYTES:
        return {"status": "UNITY_META_EVIDENCE_OVERSIZE"}
    evidence = resolve([source], "", {suffix}, project_root=root, records=[record])
    if evidence["selected"] != source:
        return {"status": "UNITY_GUID_MISMATCH", "asset_path": path, "guid": guid.lower()}
    try:
        return {"status": "EXACT", "asset_path": path, "guid": guid.lower(),
                "sha256": file_digest(source), "meta_sha256": file_digest(meta, MAX_METADATA_BYTES)}
    except CompatibilityError:
        return {"status": "UNAVAILABLE_ASSET_CONTENT_HASH", "asset_path": path, "guid": guid.lower()}


def _ref_pose(rig: dict) -> tuple[str, list[list[str]]]:
    bones = rig.get("bones", [])
    ids = {b["bone_id"]: b for b in bones}
    names = {key: str(row.get("native_bone_name") or row.get("hierarchy_path", "").rsplit("/", 1)[-1])
             for key, row in ids.items()}
    roots = [key for key, row in ids.items() if not row.get("parent_bone_id")]
    if (not bones or len(bones) > 4096 or len(ids) != len(bones) or len(roots) != 1
            or not all(names.values()) or len({name.casefold() for name in names.values()}) != len(names)):
        raise CompatibilityError("Ambiguous or incomplete Unity rig hierarchy.")
    for bone_id in ids:
        visited = set()
        current = bone_id
        while current and current not in visited and current in ids:
            visited.add(current)
            current = ids[current].get("parent_bone_id")
        if current or roots[0] not in visited:
            raise CompatibilityError("Unity source rig has an unresolved parent or cycle.")
    layout = sorted([names[key], names.get(row.get("parent_bone_id"), "")] for key, row in ids.items())
    return roots[0], layout


def angle_degrees(a: list, b: list) -> float:
    if (len(a) != 4 or len(b) != 4 or not math.isclose(math.hypot(*a), 1, abs_tol=0.01)
            or not math.isclose(math.hypot(*b), 1, abs_tol=0.01)):
        raise CompatibilityError("Invalid observed unit quaternion.")
    dot = abs(sum(x * y for x, y in zip(a, b))) / (math.hypot(*a) * math.hypot(*b))
    return math.degrees(2 * math.acos(min(1.0, dot)))


def _one(rows: list, field: str, value: str) -> dict:
    matches = [row for row in rows if row.get(field) == value]
    if len(matches) != 1:
        raise CompatibilityError("Expected one exact source identity in every measured frame.")
    return matches[0]


def _motion(capture: dict, entity: dict, usable: bool) -> dict:
    if not usable:
        return {"owner": "INSUFFICIENT_EVIDENCE", "reason": "SOURCE_CAPTURE_INCOMPLETE_OR_UNMATCHED"}
    identifier = entity["entity_id"]
    try:
        root_id, rig = _ref_pose(_one(capture["rigs"], "entity_id", identifier))
        samples = []
        for sample in capture["samples"]:
            actor = _one(sample["entities"], "entity_id", identifier)["world_transform"]
            pose = _one(sample["skeletal_poses"], "entity_id", identifier)
            root = _one(pose["bones"], "bone_id", root_id)["world_transform"]
            samples.append((actor, root))
        first_actor, first_root = samples[0]
        first_offset = [a - b for a, b in zip(first_root["position_m"], first_actor["position_m"])]
        actor_cm = 100 * max(math.dist(first_actor["position_m"], a["position_m"]) for a, _ in samples)
        root_cm = 100 * max(math.dist(first_root["position_m"], b["position_m"]) for _, b in samples)
        offset_cm = 100 * max(math.dist(first_offset, [r - p for r, p in zip(b["position_m"], a["position_m"])])
                              for a, b in samples)
        actor_deg = max(angle_degrees(first_actor["rotation_xyzw"], a["rotation_xyzw"]) for a, _ in samples)
        root_deg = max(angle_degrees(first_root["rotation_xyzw"], b["rotation_xyzw"]) for _, b in samples)
        relative = [character_motion.relative_root(a, b) for a, b in samples]
        local_cm = 100 * max(math.dist(relative[0][0], p) for p, _ in relative)
        local_deg = max(angle_degrees(relative[0][1], q) for _, q in relative)
        unit_scale = all(math.dist(a["scale_xyz"], [1, 1, 1]) <= 1e-5 for a, _ in samples)
        root_unit_scale = all(math.dist(b["scale_xyz"], [1, 1, 1]) <= 1e-5 for _, b in samples)
        finite = all(math.isfinite(value) for value in (actor_cm, root_cm, offset_cm, actor_deg, root_deg, local_cm, local_deg))
        if not finite:
            raise CompatibilityError("Nonfinite actor or root motion sample.")
    except (CompatibilityError, KeyError, TypeError, ValueError, IndexError):
        return {"owner": "INSUFFICIENT_EVIDENCE", "reason": "SOURCE_RIG_ROOT_OR_FRAME_AMBIGUOUS"}
    moving_actor = actor_cm > STILL_CM or actor_deg > STILL_DEGREES
    moving_root = root_cm > STILL_CM or root_deg > STILL_DEGREES
    if moving_actor:
        owner = character_motion.LOCAL_OWNER if local_cm <= STILL_CM and local_deg <= STILL_DEGREES else "COMPOUND_OR_UNRESOLVED"
    else:
        owner = "SKELETAL_ROOT" if moving_root else "IN_PLACE"
    return {"owner": owner, "sample_count": len(samples), "root_bone_id": root_id, "rig_sha256": digest(rig),
            "bones": rig, "actor_translation_cm": actor_cm, "root_translation_cm": root_cm,
            "actor_rotation_degrees": actor_deg, "root_rotation_degrees": root_deg,
            "relative_world_offset_drift_cm": offset_cm, "actor_has_unit_scale": unit_scale,
            "relative_actor_space_drift_cm": local_cm, "relative_actor_space_rotation_degrees": local_deg,
            "root_has_unit_scale": root_unit_scale,
            "basis": "UNITY_PLAY_MODE_CAPTURE_CANONICAL_WORLD"}


def _clip(context: dict, section: dict, asset: dict, mapping: dict) -> dict:
    meta = asset.get("metadata") or {}
    clip = meta.get("animation_clip") or {}
    format_choice = animation_format_policy.classify(asset, skeletal=True)
    source_format = format_choice["format"]
    origin = _asset(
        context, meta, source_format if source_format in {".fbx", ".anim"} else ".fbx"
    )
    asset_id = asset.get("asset_id")
    target = (mapping.get("assets") or {}).get(asset.get("name"))
    result = {"section_id": section.get("section_id"), "asset_id": asset_id, "source": origin,
              "unity_local_file_id": meta.get("local_file_id"), "planned_target_clip": target,
              "source_format": source_format, "format_policy": format_choice["policy"]}
    if source_format != ".fbx":
        # Keep the existing provenance verification but NEVER convert a
        # Unity .anim rig track by pretending the input is an FBX take.
        if origin.get("status") != "EXACT":
            return {**result, "status": origin["status"]}
        if (meta.get("source_sha256") != origin["sha256"]
                or meta.get("source_meta_sha256") != origin["meta_sha256"]):
            return {**result, "status": "UNITY_CLIP_EXPORT_HASH_MISSING_OR_STALE"}
        return {**result, "status": format_choice["policy"],
                "next_step": format_choice.get("next_step")}
    if origin["status"] != "EXACT":
        return {**result, "status": origin["status"]}
    if meta.get("source_sha256") != origin["sha256"] or meta.get("source_meta_sha256") != origin["meta_sha256"]:
        return {**result, "status": "UNITY_CLIP_EXPORT_HASH_MISSING_OR_STALE"}
    if (asset.get("ced_type") != "animation.clip" or meta.get("asset_type") != "UnityEngine.AnimationClip"
            or type(meta.get("local_file_id")) is not int or meta["local_file_id"] == 0
            or asset_id != f"unity-asset:{origin['guid']}:{meta['local_file_id']}"):
        return {**result, "status": "UNITY_CLIP_SUBASSET_ID_UNVERIFIED"}
    try:
        start, end, offset = [csir_plan.rational_seconds(section[k]) for k in ("start", "end", "source_offset")]
        speed = float(section.get("time_scale", 1))
        duration, fps = float(clip["duration_seconds"]), float(clip["frame_rate"])
        values = [start, end, offset, speed, duration, fps]
        if not all(math.isfinite(x) for x in values) or start < 0 or end <= start or offset < 0:
            raise ValueError
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        return {**result, "status": "CLIP_TIMING_EVIDENCE_UNAVAILABLE"}
    timing = {"start_seconds": start, "end_seconds": end, "offset_seconds": offset,
              "time_scale": speed, "duration_seconds": duration, "source_fps": fps}
    eligible = (0 < fps <= 240 and duration > 0 and speed > 0 and (end - start) * speed + offset <= duration + 1e-5
                and clip.get("default_single_fbx_take") is True and clip.get("is_looping") is False
                and clip.get("is_humanoid") is False and section.get("loop") is not True
                and isinstance(target, str) and PACKAGE_PATH.fullmatch(target))
    return {**result, "timing": timing, "status": "EXACT" if eligible else "UNSUPPORTED_CLIP_TAKE_OR_MAPPING"}


def inspect(config: dict, csir: dict, capture: dict, mapping: dict, fingerprints: dict,
            target_probe: dict | None) -> dict:
    context, profiles = input_context(config, csir)
    context["input_sha256"] = fingerprints
    context["original_sequence_path"] = mapping.get("sequence_asset_path")
    probe = target_probe or {}
    probe = probe if probe.get("context_sha256") == probe_identity(context) else {}
    native = probe.get("profiles", {})
    observed_clips = probe.get("clips", {})
    tracks = [t for t in csir.get("tracks", []) if t.get("ced_type") == "animation.track"
              and t.get("muted") is not True and t.get("sections")]
    by_entity = Counter(t.get("binding_entity_id") for t in tracks)
    all_entities = csir.get("entities", [])
    characters = [e for e in all_entities if e.get("ced_type") == "entity.character"
                  and e.get("entity_id") in by_entity]
    asset_by_id = {a["asset_id"]: a for a in csir.get("assets", [])}
    asset_name_counts = Counter(a.get("name") for a in csir.get("assets", []))
    asset_id_counts = Counter(a.get("asset_id") for a in csir.get("assets", []))
    name_counts = Counter(e.get("name") for e in all_entities)
    usable = False
    if characters and len(capture.get("samples") or []) <= 4000:
        try:
            plan = sampling_plan.build_plan(csir, csir_sha256=fingerprints["csir"])
            usable = (bool(plan["samples"]) and not sampling_plan.validate_capture(plan, capture)["failures"]
                      and bool(context["unity_project_fingerprint"])
                      and capture.get("source", {}).get("project_fingerprint") == context["unity_project_fingerprint"])
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            pass
    rows = []
    for entity in sorted(characters, key=lambda row: str(row["entity_id"]))[:MAX_CHARACTERS]:
        identifier, name = entity["entity_id"], entity["name"]
        row_id = f"character-{len(rows) + 1:02d}"
        meta = entity.get("metadata") or {}
        refs = {(r.get("asset_path"), r.get("guid")) for r in (meta.get("source_model_assets") or [])}
        model = (_asset(context, dict(zip(("asset_path", "guid"), next(iter(refs)))), ".fbx")
                 if len(refs) == 1 else {"status": "AMBIGUOUS_OR_MISSING_RENDERER_FBX"})
        motion = _motion(capture, entity, usable)
        if motion["owner"] == character_motion.LOCAL_OWNER:
            try:
                path = character_motion.trajectory(csir, capture, identifier)
                motion.update(trajectory=path, trajectory_sha256=digest(path))
            except (ValueError, TypeError, KeyError, ZeroDivisionError) as exc:
                motion.update(owner="INSUFFICIENT_EVIDENCE", reason=str(exc))
        sections = [s for track in tracks if track.get("binding_entity_id") == identifier for s in track["sections"]]
        clips = []
        for section in sections[:MAX_SECTIONS]:
            aid = (section.get("payload") or {}).get("asset_id")
            asset = asset_by_id.get(aid, {})
            if asset_id_counts[aid] != 1 or asset_name_counts[asset.get("name")] != 1:
                clips.append({"status": "AMBIGUOUS_OR_MISSING_CLIP_IDENTITY", "section_id": section.get("section_id")})
            else:
                clips.append(_clip(context, section, asset, mapping))
        for clip in clips:
            clip["target"] = observed_clips.get(clip.get("planned_target_clip"), {"status": "UNOBSERVED"})
        materials = [_asset(context, record, ".mat") for record in (meta.get("source_material_assets") or [])[:32]]
        profile = profiles.get(identifier)
        target = native.get(identifier, {})
        if target.get("status") == "OBSERVED":
            try:
                packages = target["packages"]
                if not packages or any(package_files(Path(context["unreal_project"]), p["path"]) != p["files_sha256"]
                                       for p in packages.values()):
                    raise CompatibilityError("Changed native packages.")
            except (OSError, ValueError, KeyError, TypeError):
                target = {"status": "TARGET_PACKAGE_EVIDENCE_STALE"}
        binding = (mapping.get("entities") or {}).get(name, {})
        sections_known = {c.get("section_id") for c in clips}
        takes = {(c.get("source", {}).get("guid"), c.get("unity_local_file_id")) for c in clips}
        failures = []
        if model["status"] != "EXACT":
            failures.append(model["status"])
        if (not clips or len(sections) > MAX_SECTIONS or None in sections_known or len(sections_known) != len(clips)
                or any(c["status"] != "EXACT" for c in clips)
                or len({guid for guid, _ in takes}) != len(takes)):
            failures.append("CLIP_IDENTITY_OR_TIMING_UNVERIFIED")
        if name_counts[name] != 1 or not binding.get("actor_label"):
            failures.append("AMBIGUOUS_OR_MISSING_ACTOR_BINDING")
        if motion["owner"] == "INSUFFICIENT_EVIDENCE":
            failures.append(motion["reason"])
        if profile:
            if model.get("sha256") != profile["source_fbx_sha256"]:
                failures.append("APPROVED_FBX_HASH_MISMATCH")
            if entity.get("parent_entity_id") or config.get("skeletal_root_world_lock") or mapping.get("enable_cinetwin_skeletal_world_lock"):
                failures.append("PARENTED_OR_COMPETING_ROOT_MOTION_POLICY")
            if (motion["owner"] not in ("IN_PLACE", character_motion.LOCAL_OWNER)
                    or not motion.get("actor_has_unit_scale") or not motion.get("root_has_unit_scale")):
                failures.append("UNPROVEN_MOTION_COMPOSITION")
            if motion["owner"] == character_motion.LOCAL_OWNER:
                if any(r.get("source_sha256") != model.get("sha256") or r.get("source_meta_sha256") != model.get("meta_sha256")
                       for r in (meta.get("source_model_assets") or [])):
                    failures.append("UNITY_MODEL_EXPORT_HASH_MISSING_OR_STALE")
                if probe.get("observed_identity", {}).get("native_actor_motion") is not True:
                    failures.append("TARGET_ACTOR_MOTION_API_UNAVAILABLE")
                # This version deliberately excludes layered/crossfaded root ownership.
                ordered = sorted(clips, key=lambda c: c.get("timing", {}).get("start_seconds", -1))
                if (len(clips) != 1 or by_entity[identifier] != 1
                        or any(csir_plan.timeline_clip_easing_seconds(s.get("native_payload", {}), direction) > 0
                               for s in sections for direction in ("in", "out"))):
                    failures.append("MOVING_ACTOR_REQUIRES_ONE_UNBLENDED_CLIP")
                if any(c.get("timing", {}).get("source_fps", 1) * c.get("timing", {}).get("duration_seconds", 0)
                       >= character_motion.MAX_FRAMES - 1 for c in clips):
                    failures.append("MOVING_ACTOR_NATIVE_ROOT_SAMPLE_BUDGET_EXCEEDED")
                try:
                    native_plan = csir_plan.build_plan({**csir, "tracks": [t for t in tracks if t.get("binding_entity_id") == identifier]}, mapping)
                    if any("expected_root_delta_cm" in a for a in native_plan["actions"] if a.get("entity_name") == name):
                        failures.append("MOVING_ACTOR_REFUSES_LEGACY_ROOT_CURVE_CORRECTION")
                except (ValueError, KeyError, TypeError, ZeroDivisionError):
                    failures.append("MOVING_ACTOR_NATIVE_CLIP_PLAN_UNVERIFIED")
                if ordered and "timing" in ordered[0] and "trajectory" in motion:
                    timing = ordered[0]["timing"]
                    path = motion["trajectory"]
                    rate = path["display_rate"]
                    end = path["source_start_seconds"] + path["duration_frames"] * rate["denominator"] / rate["numerator"]
                    if (not math.isclose(timing["start_seconds"], path["source_start_seconds"], abs_tol=1e-8)
                            or not math.isclose(timing["end_seconds"], end, abs_tol=1e-8)):
                        failures.append("MOVING_ACTOR_CLIP_MUST_COVER_PLAYBACK")
            if target.get("status") != "OBSERVED":
                failures.append(target.get("status", "TARGET_NATIVE_PROBE_UNAVAILABLE"))
            elif (target.get("source_rig_sha256") != motion.get("rig_sha256")
                  or os.path.normcase(target.get("source_import_path") or "") != os.path.normcase(
                      str((Path(context["unity_project"]) / model.get("asset_path", "")).resolve()))):
                failures.append("PREVIEW_SOURCE_HIERARCHY_OR_IMPORT_MISMATCH")
            if any(clip["target"]["status"] != "AVAILABLE_FOR_NEW_ASSET" for clip in clips):
                failures.append("TARGET_CLIP_PATH_UNAVAILABLE_OR_OCCUPIED")
            if (probe.get("observed_identity", {}).get("native_skeletal_track") is not True
                    or not str(probe.get("observed_identity", {}).get("engine_version", "")).startswith("5.8.")):
                failures.append("TARGET_SKELETAL_API_OR_VERSION_UNVERIFIED")
            if identifier in mapping.get("skeletal_retarget_profiles", {}):
                failures.append("EXISTING_MANUAL_RETARGET_PROFILE")
        elif not failures:
            failures.append("NO_APPROVED_TARGET_RIG_MAPPING")
        material_status = "TARGET_MESH_MATERIALS_RETAINED" if profile else "TARGET_MATERIAL_UNVERIFIED"
        same_skeleton = (target.get("packages", {}).get("source_skeleton", {}).get("path")
                         == target.get("packages", {}).get("target_skeleton", {}).get("path"))
        status = ("COMPATIBLE" if profile and not failures and same_skeleton else
                  "COMPATIBLE_AFTER_APPROVED_RETARGET" if profile and not failures else
                  "INCOMPATIBLE" if any(reason in failures for reason in (
                      "APPROVED_FBX_HASH_MISMATCH", "PREVIEW_SOURCE_HIERARCHY_OR_IMPORT_MISMATCH",
                      "TARGET_ASSET_CLASS_OR_BINDING_MISMATCH", "UNITY_GUID_MISMATCH")) else "INSUFFICIENT_EVIDENCE")
        entries = {"model": model, "clips": clips, "motion": motion, "target": target, "materials": materials}
        rows.append({"id": row_id, "source_entity_id": identifier, "source_entity_name": name,
                     "source_parent_entity_id": entity.get("parent_entity_id"), "target_actor_label": binding.get("actor_label"),
                     **entries, "approved_profile": profile, "status": status, "reasons": failures,
                     "source_reference_pose_status": "UNAVAILABLE_FROM_SOURCE_CAPTURE",
                     "source_local_reference_validation": "CHECKED_AFTER_FRESH_IMPORT_BEFORE_RETARGETING",
                     "material_status": material_status, "evidence_ids": {
                         key: digest([identifier, key, value]) for key, value in entries.items()}})
    return {"kind": REPORT, "schema_version": "1", "context": context, "characters": rows,
            "target_probe": probe.get("observed_identity"), "probe_request_sha256": probe.get("request_sha256"),
            "character_count": len(characters),
            "truncated": len(characters) > MAX_CHARACTERS, "fidelity_verified": False}


def probe_identity(context: dict) -> str:
    return digest({key: value for key, value in context.items() if key not in ("input_sha256", "original_sequence_path")})
