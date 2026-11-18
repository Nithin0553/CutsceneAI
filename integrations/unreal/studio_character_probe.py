"""Read-only targeted Unreal probe for the pre-transfer character policy."""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for directory in (ROOT / "tools", ROOT / "packages/studio", ROOT / "packages/cinetwin"):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import character_compatibility as compatibility
import studio_ik_retarget


def _asset_path(asset) -> str:
    return str(asset.get_path_name()).split(".", 1)[0] if asset is not None else ""


def _asset_class(asset) -> str:
    return str(asset.get_class().get_name()) if asset is not None else ""


def package_files(project: Path, path: str) -> dict:
    if not compatibility.PACKAGE_PATH.fullmatch(path):
        raise compatibility.CompatibilityError("Unsafe or external Unreal package path.")
    content = project.parent / "Content"
    base = content / path.removeprefix("/Game/")
    if not base.resolve().is_relative_to(content):
        raise compatibility.CompatibilityError("Unreal package resolves outside project Content.")
    files = {".uasset": compatibility.file_digest(base.with_suffix(".uasset"))}
    for suffix in (".uexp", ".ubulk"):
        sidecar = base.with_suffix(suffix)
        if sidecar.exists() or sidecar.is_symlink():
            files[suffix] = compatibility.file_digest(sidecar)
    return files


def _bones(api, mesh, skeleton) -> list[list[str]]:
    extension = api.AnimPoseExtensions
    pose = extension.get_reference_pose(skeleton)
    names = [str(bone) for bone in extension.get_bone_names(pose)]
    if not names or len(names) > 4096 or len(set(names)) != len(names):
        raise compatibility.CompatibilityError("Missing or ambiguous Unreal reference skeleton.")
    rows = []
    for bone in names:
        parent = str(mesh.get_bone_parent(bone))
        rows.append([bone, "" if parent.lower() == "none" else parent])
    return sorted(rows)


def _reference_pose(api, skeleton) -> str:
    extension = api.AnimPoseExtensions
    pose = extension.get_reference_pose(skeleton)
    rows = []
    for bone in extension.get_bone_names(pose):
        transform = extension.get_bone_pose(pose, bone)
        position, rotation, scale = transform.translation, transform.rotation, transform.scale3d
        values = [position.x, position.y, position.z, rotation.x, rotation.y, rotation.z, rotation.w,
                  scale.x, scale.y, scale.z]
        if not all(math.isfinite(float(value)) for value in values):
            raise compatibility.CompatibilityError("Nonfinite native reference-pose transform.")
        rows.append([str(bone), *map(float, values)])
    return compatibility.digest(sorted(rows))


def _profile(api, project: Path, identifier: str, spec: dict, dirty: set[str]) -> dict:
    parts = studio_ik_retarget.prepare(api, {"skeletal_retarget_profiles": {identifier: spec}, "imports": []})[identifier]
    source, target = parts["source"], parts["target"]
    source_skeleton = source.get_editor_property("skeleton")
    target_skeleton = target.get_editor_property("skeleton")
    assets = {**parts, "source_skeleton": source_skeleton, "target_skeleton": target_skeleton}
    classes = {"source": "SkeletalMesh", "target": "SkeletalMesh", "retargeter": "IKRetargeter",
               "source_rig": "IKRigDefinition", "target_rig": "IKRigDefinition",
               "source_skeleton": "Skeleton", "target_skeleton": "Skeleton"}
    if any(_asset_class(asset) != classes[key] for key, asset in assets.items()):
        return {"status": "TARGET_ASSET_CLASS_OR_BINDING_MISMATCH"}
    if any(_asset_path(asset) in dirty for asset in assets.values()):
        return {"status": "TARGET_RIG_PACKAGES_UNSAVED"}
    packages = {key: {"path": _asset_path(asset), "class": classes[key],
                      "files_sha256": package_files(project, _asset_path(asset))}
                for key, asset in assets.items()}
    data = source.get_editor_property("asset_import_data")
    sources = list(data.extract_filenames()) if data is not None else []
    origin = Path(str(sources[0])) if len(sources) == 1 else None
    source_path = str(origin.resolve()) if origin is not None and origin.is_absolute() else None
    return {"status": "OBSERVED", "packages": packages, "source_import_path": source_path,
            "source_rig_sha256": compatibility.digest(_bones(api, source, source_skeleton)),
            "target_rig_sha256": compatibility.digest(_bones(api, target, target_skeleton)),
            "source_reference_pose_sha256": _reference_pose(api, source_skeleton),
            "target_reference_pose_sha256": _reference_pose(api, target_skeleton),
            "target_material_slot_count": len(target.get_editor_property("materials"))}


def inspect(api, request: dict, *, project: str, level: str) -> dict:
    """Read only named assets and record the actual editor project/map identity."""
    context = request["context"]
    selected = Path(project).resolve()
    if (os.path.normcase(str(selected)) != os.path.normcase(context["unreal_project"])
            or (level != context["destination_level"] and not context["create_level"])):
        raise compatibility.CompatibilityError("Wrong Unreal project or map for the animation compatibility probe.")
    catalog_sha, approved = compatibility.approved_profiles(selected, context["unity_project_fingerprint"])
    if (request.get("kind") != "cutsceneai.studio.character_probe_request"
            or request.get("context_sha256") != compatibility.probe_identity(context)
            or catalog_sha != context["profile_catalog_sha256"]
            or compatibility.file_digest(selected, 4 * 1024 * 1024) != context["uproject_sha256"]
            or any(identifier not in approved for identifier in request["profile_ids"])):
        raise compatibility.CompatibilityError("The approved project or rig catalog changed before native inspection.")
    dirty_query = getattr(getattr(api, "EditorLoadingAndSavingUtils", None), "get_dirty_content_packages", None)
    dirty = {_asset_path(p) for p in dirty_query()} if callable(dirty_query) and request["profile_ids"] else set()
    profiles = {}
    for identifier in request["profile_ids"]:
        try:
            profiles[identifier] = (_profile(api, selected, identifier, approved[identifier], dirty)
                                    if callable(dirty_query) else {"status": "TARGET_PACKAGE_DIRTY_PROBE_UNAVAILABLE"})
        except studio_ik_retarget.RetargetError as exc:
            reason = ("TARGET_IK_API_UNAVAILABLE" if "API" in str(exc) or "roles" in str(exc)
                      else "TARGET_ASSET_CLASS_OR_BINDING_MISMATCH")
            profiles[identifier] = {"status": reason}
        except (OSError, TypeError, AttributeError, ValueError, RuntimeError):
            profiles[identifier] = {"status": "TARGET_NATIVE_EVIDENCE_UNAVAILABLE"}
    clips = {}
    for path in request["clip_paths"]:
        if not compatibility.PACKAGE_PATH.fullmatch(path):
            raise compatibility.CompatibilityError("Invalid target animation package in read-only request.")
        asset = api.load_asset(path) if api.EditorAssetLibrary.does_asset_exist(path) else None
        asset_class = _asset_class(asset)
        clips[path] = {"status": "OCCUPIED" if asset else "AVAILABLE_FOR_NEW_ASSET",
                       "class": asset_class or None,
                       "skeleton": _asset_path(asset.get_editor_property("skeleton")) if asset_class == "AnimSequence" else None}
    return {"kind": "cutsceneai.studio.character_target_probe", "context_sha256": request["context_sha256"],
            "request_sha256": compatibility.digest(request), "profiles": profiles, "clips": clips,
            "observed_identity": {"project": str(selected), "level": level,
                                  "engine_version": str(api.SystemLibrary.get_engine_version()), "editor_pid": os.getpid(),
                                  "native_skeletal_track": hasattr(api, "MovieSceneSkeletalAnimationTrack")}}


def service(workspace: Path, api, *, project: str, level: str, save) -> None:
    """Answer a single bounded request on the existing Unreal editor tick thread."""
    path = workspace / "character-probe-request.json"
    if not path.is_file():
        return
    request = compatibility.read_json(path, 256 * 1024)
    if (not isinstance(request.get("profile_ids"), list) or len(request["profile_ids"]) > 16
            or not isinstance(request.get("clip_paths"), list) or len(request["clip_paths"]) > 64):
        raise compatibility.CompatibilityError("Out-of-bounds native character asset request.")
    answer = workspace / "character-probe-result.json"
    token = compatibility.digest(request)
    if answer.is_file():
        previous = compatibility.read_json(answer)
        if (previous.get("request_sha256") == token
                and previous.get("observed_identity", {}).get("editor_pid") == os.getpid()
                and previous.get("observed_identity", {}).get("level") == level):
            return
    try:
        result = inspect(api, request, project=project, level=level)
    except (AttributeError, KeyError, OSError, TypeError, RuntimeError, ValueError) as exc:
        result = {"request_sha256": token, "error": str(exc)[:300],
                  "observed_identity": {"editor_pid": os.getpid(), "level": level}}
    save(answer, result)
