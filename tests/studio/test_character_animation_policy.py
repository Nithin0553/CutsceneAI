"""Friday assignment tests use synthetic captures and a read-only Unreal API mock."""
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from types import SimpleNamespace as NS

import jsonschema
import pytest

ROOT = Path(__file__).resolve().parents[2]
for folder in ("tools", "packages/cinetwin", "packages/studio", "packages/learning", "integrations/unreal"):
    sys.path.insert(0, str(ROOT / folder))

import animation_conversion_policy as policy
import character_compatibility as compat
import prepared_transfer
import sampling_plan
import studio_auto_assets
import studio_candidate
import studio_character_execution as executor
import studio_character_probe as native
import studio_transfer_ai as ai


def _json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _time(seconds):
    return {"value": round(seconds * 24), "rate": {"numerator": 24, "denominator": 1}}


def _pose(x):
    return {"position_m": [x, 0, 0], "rotation_xyzw": [0, 0, 0, 1], "scale_xyz": [1, 1, 1]}


class Asset:
    def __init__(self, path, kind, **props):
        self.path, self.kind, self.props = path, kind, props

    def get_path_name(self):
        return self.path + "." + self.path.rsplit("/", 1)[-1]

    def get_class(self):
        return NS(get_name=lambda: self.kind)

    def get_editor_property(self, name):
        return self.props[name]

    def get_bone_parent(self, name):
        return "None" if name == "Root" else "Root"

    def get_play_length(self):
        return self.props["duration"]


@pytest.fixture
def case(tmp_path):
    unity = tmp_path / "PrivateUnity"
    model, clip = [unity / "Assets" / name for name in ("SourceModel.fbx", "PrivateClip.fbx")]
    model.parent.mkdir(parents=True)
    for path, guid in zip((model, clip), ("1" * 32, "2" * 32)):
        path.write_bytes(("fixture-only " + path.name).encode())
        path.with_name(path.name + ".meta").write_text("guid: " + guid + "\n", encoding="utf-8")
    source_project = {"engine": "unity", "engine_version": "6000.3.10f1", "project_fingerprint": "unity-fixture",
                      "sequence_ref": "Assets/PrivateTimeline.playable"}
    clip_id = "unity-asset:" + "2" * 32 + ":111"
    clip_path = "/Game/Staging/Animations/AS_Fresh"
    csir = {"schema_version": "0.1.0", "cutscene_id": "synthetic-cutscene", "source": source_project,
            "timing": {"display_rate": {"numerator": 24, "denominator": 1},
                       "source_rate": {"numerator": 24, "denominator": 1}, "playback_start": _time(0),
                       "playback_end": _time(1), "duration_seconds": 1.0},
            "entities": [{"entity_id": "source-char", "name": "PrivatePerformer", "ced_type": "entity.character",
                          "native_ref": "source-character-global-id",
                          "metadata": {"scene_path": "Assets/PrivateScene.unity", "hierarchy_path": "PrivatePerformer",
                                       "source_model_assets": [{"asset_path": "Assets/SourceModel.fbx", "guid": "1" * 32}]}}],
            "assets": [{"asset_id": clip_id, "name": "PrivateClip", "ced_type": "animation.clip",
                        "metadata": {"asset_path": "Assets/PrivateClip.fbx", "guid": "2" * 32, "local_file_id": 111,
                                     "source_sha256": compat.file_digest(clip),
                                     "source_meta_sha256": compat.file_digest(clip.with_name(clip.name + ".meta")),
                                     "asset_type": "UnityEngine.AnimationClip", "animation_clip": {
                                         "duration_seconds": 1.0, "frame_rate": 24.0, "is_looping": False,
                                         "is_humanoid": False, "default_single_fbx_take": True}}}],
            "tracks": [{"track_id": "skeletal", "name": "Body", "ced_type": "animation.track",
                        "binding_entity_id": "source-char", "sections": [{"section_id": "section",
                            "ced_type": "animation.section", "start": _time(0), "end": _time(1),
                            "source_offset": _time(0), "time_scale": 1.0, "payload": {"asset_id": clip_id}}]}]}
    csir_path = _json(tmp_path / "source.json", csir)
    plan = sampling_plan.build_plan(csir, csir_sha256=compat.file_digest(csir_path))
    capture = {"kind": "cinetwin.behavior_capture", "cutscene_id": plan["cutscene_id"], "source": plan["source"],
               "capture_layers": [{"layer": x["layer"], "status": "CAPTURED" if x["status"] == "PLANNED" else "NOT_IMPLEMENTED"}
                                  for x in plan["capabilities"]],
               "rigs": [{"entity_id": "source-char", "bones": [
                   {"bone_id": "root-id", "native_bone_name": "Root", "parent_bone_id": ""},
                   {"bone_id": "arm-id", "native_bone_name": "Arm", "parent_bone_id": "root-id"}]}],
               "samples": [{"time_seconds": frame["time_seconds"],
                            "entities": [{"entity_id": "source-char", "world_transform": _pose(0)}],
                            "skeletal_poses": [{"entity_id": "source-char", "bones": [
                                {"bone_id": bid, "local_transform": _pose(value), "world_transform": _pose(value)}
                                for bid, value in (("root-id", 0), ("arm-id", frame["time_seconds"]))]}]}
                           for frame in plan["samples"]]}
    capture_file = _json(tmp_path / "capture.json", capture)
    mapping = {"sequence_asset_path": "/Game/Staging/LS_Base", "overwrite_sequence": False,
               "entities": {"PrivatePerformer": {"actor_label": "NewPerformer"}}, "assets": {"PrivateClip": clip_path}}
    mapping_path = _json(tmp_path / "mapping.json", mapping)
    census = _json(unity / "CutSceneAI/Exports/feature-surface-unity-fixture.json",
                   {"kind": "cutsceneai.engine.feature_surface", "schema_version": "0.2.0",
                   **{key: source_project[key] for key in ("engine", "engine_version", "project_fingerprint")},
                   "loaded_scene_components": [{"scene_path": "Assets/PrivateScene.unity", "object_path": "PrivatePerformer",
                        "global_object_id": "source-character-global-id", "component_global_id": "source-transform-global-id",
                        "component_type": "UnityEngine.Transform", "component_assembly": "UnityEngine.CoreModule"}]})
    project = _json(tmp_path / "Unreal" / "Staging.uproject", {"EngineAssociation": "5.8"})
    level = "/Game/Staging/L_Draft"
    config = {"unity_project": str(unity), "source_scope": "Assets", "csir": str(csir_path),
              "capture": str(capture_file), "mapping": str(mapping_path), "target_project": str(project), "level_path": level}
    profile = {"source_mesh_path": "/Game/Approved/Source", "target_mesh_path": "/Game/Approved/Target",
               "retargeter_path": "/Game/Approved/Retarget", "source_fbx_sha256": compat.file_digest(model)}
    catalog = _json(project.parent / compat.PROFILE_FILE, {"kind": compat.PROFILE_CATALOG, "schema_version": "1",
                    "profiles": [{**profile, "unity_project_fingerprint": "unity-fixture", "source_entity_id": "source-char"}]})
    source_skeleton = Asset("/Game/Approved/SourceSkeleton", "Skeleton")
    target_skeleton = Asset("/Game/Approved/TargetSkeleton", "Skeleton")
    source_rig = Asset("/Game/Approved/SourceRig", "IKRigDefinition")
    target_rig = Asset("/Game/Approved/TargetRig", "IKRigDefinition")
    source = Asset(profile["source_mesh_path"], "SkeletalMesh", skeleton=source_skeleton,
                   asset_import_data=NS(extract_filenames=lambda: [str(model)]))
    target = Asset(profile["target_mesh_path"], "SkeletalMesh", skeleton=target_skeleton, materials=[object()])
    retarget = Asset(profile["retargeter_path"], "IKRetargeter")
    assets = {a.path: a for a in (source, target, retarget, source_skeleton, target_skeleton, source_rig, target_rig)}
    for path, asset in assets.items():
        package = project.parent / "Content" / (path.removeprefix("/Game/") + ".uasset")
        package.parent.mkdir(parents=True, exist_ok=True)
        package.write_bytes(asset.kind.encode())
    controller = NS(get_ik_rig=lambda role: {"source": source_rig, "target": target_rig}[role],
                    get_preview_mesh=lambda role: {"source": source, "target": target}[role])
    api = NS(
        EditorLoadingAndSavingUtils=NS(get_dirty_content_packages=list),
        EditorAssetLibrary=NS(does_asset_exist=lambda path: path in assets, does_directory_exist=lambda _: False,
                              find_asset_data=lambda _: None, save_loaded_asset=lambda _: True),
        IKRetargeterController=NS(get_controller=lambda _: controller),
        IKRetargetBatchOperation=NS(duplicate_and_retarget=lambda *_: []),
        RetargetSourceOrTarget=NS(SOURCE="source", TARGET="target"),
        AnimPoseExtensions=NS(get_reference_pose=lambda _: object(), get_bone_names=lambda _: ["Root", "Arm"],
                              get_bone_pose=lambda *_: NS(translation=NS(x=0, y=0, z=0),
                                  rotation=NS(x=0, y=0, z=0, w=1), scale3d=NS(x=1, y=1, z=1))),
        SystemLibrary=NS(get_engine_version=lambda: "5.8.3"),
        MovieSceneSkeletalAnimationTrack=type("SkeletalTrack", (), {}),
        EditorActorSubsystem=object(), get_editor_subsystem=lambda _: NS(get_all_level_actors=list),
        load_asset=assets.get,
    )
    worker = {"connected": True, "project": str(project), "level": level, "editor_pid": os.getpid(),
              "scene_inventory": {"available": True, "actor_count": 0, "class_counts": {}, "character_compatibility_probe": True,
                                  "native_capabilities": {key: True for key in (
                                      "fbx_asset_import", "sequencer_visibility_track", "sequencer_skeletal_animation_track",
                                      "cine_camera_actor")}}}
    return NS(config=config, unity=unity, csir=csir, capture=capture, mapping=mapping, level=level, api=api, worker=worker,
              project=project, model=model, clip=clip, catalog=catalog, census=str(census), profile=profile, assets=assets,
              clip_path=clip_path, source_skeleton=source_skeleton, target_skeleton=target_skeleton)


def _probe(case):
    request = policy.make_probe_request(case.config, case.csir, case.mapping, run_id="fixture-run")
    return native.inspect(case.api, request, project=str(case.project), level=case.level)


def _choice(case, monkeypatch):
    captured = {}
    def response(**kwargs):
        captured.update(kwargs)
        return NS(output_text=json.dumps({"strategy": "native_source", "reason": "Approved in-place retarget.",
                                         "animation_choice_id": "character-01"}))
    monkeypatch.setenv("OPENAI_API_KEY", "mock-transport")
    monkeypatch.setitem(sys.modules, "openai", NS(OpenAI=lambda **_: NS(responses=NS(create=response))))
    decision = ai.decide(case.config, case.census, case.worker, native_character_probe=_probe(case))
    decision["character_probe_run_id"] = "fixture-run"
    report = decision.pop("character_compatibility")
    assert decision["animation_conversion"]["action_id"] == policy.ACTION
    assert "character-01" in captured["input"]
    for private in (str(case.unity), "Private", "/Game/Approved", "unity-fixture", "source-char", "mock-transport"):
        assert private not in captured["input"]
    return report, decision


def test_model_choice_changes_native_manifest_and_survives_editor_preflight(case, tmp_path, monkeypatch):
    report, decision = _choice(case, monkeypatch)
    schema = _read(ROOT / "packages/contracts/studio/ai-animation-conversion-decision-v1.schema.json")
    jsonschema.Draft202012Validator(schema).validate(decision["animation_conversion"])
    root = tmp_path / "candidate"
    copied, _ = studio_candidate.prepare_candidate(
        Path(case.config["csir"]), Path(case.config["mapping"]), Path(case.config["capture"]),
        "/Game/Staging/LS_New", root, character_selection=(report, decision["animation_conversion"]),
        transfer_options={"source_feature_surface_path": case.census, "require_complete_source_features": False},
    )
    prepared_transfer.verify(root)
    plan = _read(root / "transfer-plan.json")
    manifest = studio_auto_assets.inspect(case.config["csir"], copied, root / "transfer-plan.json", case.unity,
                                         "Assets", "/Game/Staging/NewCandidate")
    assert manifest["ready"], manifest["blockers"]
    clips = [row for row in manifest["imports"] if row["kind"] == "AnimSequence"]
    clip, = clips
    assert clip["target_asset_path"] == case.clip_path
    assert clip["source_animation_path"].startswith("/Game/Staging/NewCandidate/RetargetSource/")
    assert "skeletal_retarget_profiles" not in _read(case.config["mapping"])
    report_file = _json(root / policy.REPORT_FILE, report)
    job = {"candidate_dir": str(root), "expected_project": str(case.project), "expected_level": case.level,
           "csir": case.config["csir"], "capture": case.config["capture"], "sequence_path": plan["sequence_asset_path"],
           "character_original_mapping": case.config["mapping"], "automatic_setup": True,
           "character_compatibility_sha256": compat.file_digest(report_file)}
    verified = executor.preflight(case.api, job, decision, _read(copied), plan, manifest, worker=case.worker)
    assert verified["status"] == "COMPATIBLE_AFTER_APPROVED_RETARGET"
    existing = case.assets.copy()
    case.assets[plan["sequence_asset_path"]] = Asset(plan["sequence_asset_path"], "LevelSequence")
    with pytest.raises(RuntimeError, match="occupied"):
        executor.preflight(case.api, job, decision, _read(copied), plan, manifest, worker=case.worker)
    del case.assets[plan["sequence_asset_path"]]
    package = case.project.parent / "Content/Approved/TargetRig.uasset"
    package.write_bytes(b"edited native package")
    with pytest.raises(ai.TransferAIError, match="stale"):
        executor.preflight(case.api, job, decision, _read(copied), plan, manifest, worker=case.worker)
    assert case.assets == existing


@pytest.mark.parametrize("mutation", ["source_bytes", "importer_settings", "clip_guid", "profile_hash", "native_package", "choice_code"])
def test_selected_action_rejects_changed_evidence_without_mutation(case, monkeypatch, mutation):
    _report, decision = _choice(case, monkeypatch)
    if mutation == "source_bytes":
        case.clip.write_bytes(b"source changed after Unity capture")
    elif mutation == "importer_settings":
        case.clip.with_name(case.clip.name + ".meta").write_text("guid: " + "2" * 32 + "\nchanged: true\n")
    elif mutation == "clip_guid":
        case.clip.with_name(case.clip.name + ".meta").write_text("guid: " + "3" * 32 + "\n")
    elif mutation == "profile_hash":
        configured = _read(case.catalog)
        configured["profiles"][0]["source_fbx_sha256"] = "f" * 64
        _json(case.catalog, configured)
    elif mutation == "native_package":
        (case.project.parent / "Content/Approved/SourceSkeleton.uasset").write_bytes(b"changed skeleton")
    else:
        decision["animation_conversion"]["python"] = "arbitrary_command()"
    before = set(case.assets)
    with pytest.raises((ai.TransferAIError, compat.CompatibilityError), match="stale|unregistered|eligible"):
        ai.verify(decision, case.config, case.census, case.worker, native_character_probe=_probe(case))
    assert set(case.assets) == before


def test_studio_queue_binds_model_choice_report_and_prepared_mapping(case, tmp_path, monkeypatch):
    import studio_local_bridge as bridge

    report, decision = _choice(case, monkeypatch)
    workspace = tmp_path / "runs"
    config = bridge.config_check({**case.config, "source_rights_confirmed": True, "skeletal_root_world_lock": False})
    _json(workspace / "connection.json", config)
    probe = _probe(case)
    _json(workspace / policy.PROBE_RESULT, probe)
    options = {"source_feature_surface_path": case.census, "require_complete_source_features": False}
    current = bridge.prepare(workspace, options, character_selection=(report, decision["animation_conversion"]))
    candidate = Path(current["candidate_dir"])
    _json(candidate / policy.REPORT_FILE, report)
    _json(candidate / "ai-conversion-decision.json", decision)
    bridge.approve_one_click(current["candidate_id"], workspace, enable_ai_agents=True)
    worker = {**case.worker, "worker_version": bridge.REQUIRED_WORKER_PROTOCOL, "checkout_root": str(ROOT),
              "worker_source_sha256": compat.file_digest(ROOT / "integrations/unreal/studio_local_editor_worker.py")}
    monkeypatch.setattr(bridge, "worker_connected", lambda _: worker)
    monkeypatch.setattr(bridge, "destination_readiness", lambda _: {"ready": False, "status": "SCENE_SETUP_REQUIRED"})
    queued = bridge.queue_trial(current["candidate_id"], workspace)
    job = _read(workspace / "jobs" / (queued["job_id"] + ".json"))
    assert job["ai_conversion_decision_sha256"] == compat.file_digest(candidate / "ai-conversion-decision.json")
    assert job["character_compatibility_sha256"] == compat.file_digest(candidate / policy.REPORT_FILE)
    assert job["character_original_mapping"] == case.config["mapping"]
    assert job["automatic_setup"] is True
    mapping = _read(job["mapping"])
    assert mapping["ai_character_animation"] == decision["animation_conversion"]
    with pytest.raises(ValueError, match="already submitted"):
        bridge.queue_trial(current["candidate_id"], workspace)


def test_one_click_waits_for_native_probe_then_uses_model_choice(case, tmp_path, monkeypatch):
    import studio_autopilot as autopilot
    import studio_local_bridge as bridge

    work = tmp_path / "runs"
    config = bridge.config_check({**case.config, "source_rights_confirmed": True, "skeletal_root_world_lock": False})
    _json(work / "connection.json", config)
    _json(work / autopilot.ACTIVE, {"status": "ANALYZING_PROJECTS", "run_id": "one-click-run", "census_path": case.census})
    requests = []
    def response(**kwargs):
        requests.append(kwargs)
        return NS(id="resp_fixture_transport", output_text=json.dumps({
            "strategy": "native_source", "reason": "Use approved in-place retarget.", "animation_choice_id": "character-01"}))
    monkeypatch.setenv("OPENAI_API_KEY", "mock-transport")
    monkeypatch.setitem(sys.modules, "openai", NS(OpenAI=lambda **_: NS(responses=NS(create=response))))
    service = NS(lock=threading.RLock(), worker_connected=lambda _: case.worker, load_json=bridge.load_json,
                 prepare=bridge.prepare, approve_one_click=bridge.approve_one_click)
    pending = autopilot.advance(work, service=service)
    assert pending["status"] == "ANALYZING_PROJECTS"
    assert not requests and not (work / "candidates").exists()
    native.service(work, case.api, project=str(case.project), level=case.level, save=bridge.atomic_json)
    chosen = autopilot.advance(work, service=service)
    assert chosen["status"] == "PREPARING"
    assert len(requests) == 1
    planned = autopilot.advance(work, service=service)
    assert planned["status"] == "WAITING_FOR_UNREAL", planned
    directory = work / "candidates" / planned["candidate_id"]
    decision = _read(directory / "ai-conversion-decision.json")
    assert decision["model_response_id"] == "resp_fixture_transport"
    assert _read(directory / "transfer-plan.json")["ai_character_animation"] == decision["animation_conversion"]
    assert compat.digest(_read(directory / policy.REPORT_FILE)) == decision["character_compatibility_sha256"]


def test_probe_request_is_run_bound_and_pending_does_not_fall_back(case, tmp_path):
    work = tmp_path / "runs"
    work.mkdir()
    save = lambda path, value: _json(path, value)
    needed, observation = ai.target_probe(case.config, case.worker, work, "run-1", write=save)
    assert needed and observation is None
    native.service(work, case.api, project=str(case.project), level=case.level, save=save)
    needed, observation = ai.target_probe(case.config, case.worker, work, "run-1")
    assert needed and observation["kind"] == "cutsceneai.studio.character_target_probe"
    needed, observation = ai.target_probe(case.config, case.worker, work, "run-2", write=save)
    assert needed and observation is None
    native.service(work, case.api, project=str(case.project), level=case.level, save=save)
    other_worker = {**case.worker, "editor_pid": os.getpid() + 1}
    assert ai.target_probe(case.config, other_worker, work, "run-2")[1] is None


@pytest.mark.parametrize("fault", ["split_take", "external_scope", "ambiguous_profile", "source_symlink"])
def test_clip_scope_and_profile_ambiguities_refuse_ai_selection(case, tmp_path, fault):
    if fault == "split_take":
        case.csir["assets"][0]["metadata"]["animation_clip"]["default_single_fbx_take"] = False
        source = _json(Path(case.config["csir"]), case.csir)
        case.capture["source"]["csir_sha256"] = compat.file_digest(source)
        _json(Path(case.config["capture"]), case.capture)
    elif fault == "external_scope":
        (case.unity / "Assets/Allowed").mkdir()
        case.config["source_scope"] = "Assets/Allowed"
    elif fault == "ambiguous_profile":
        configured = _read(case.catalog)
        configured["profiles"].append(dict(configured["profiles"][0]))
        _json(case.catalog, configured)
        with pytest.raises(compat.CompatibilityError, match="Ambiguous"):
            _probe(case)
        return
    else:
        external = tmp_path / "external.fbx"
        external.write_bytes(case.clip.read_bytes())
        case.clip.unlink()
        case.clip.symlink_to(external)
    evidence = ai.inspect(case.config, case.census, case.worker, native_character_probe=_probe(case))
    assert evidence["animation_choices"] == []


@pytest.mark.parametrize("duration", [1.0, 1.5])
def test_native_asset_timing_readback_halts_on_incompatible_output(case, tmp_path, duration):
    probe = _probe(case)
    report = ai.inspect(case.config, case.census, case.worker, native_character_probe=probe)["character_compatibility"]
    selected = report["characters"][0]
    clip = Asset(case.clip_path, "AnimSequence", skeleton=case.target_skeleton, duration=duration)
    case.assets[case.clip_path] = clip
    actor = Asset("/Game/Staging/Actor", "SkeletalMeshActor",
                  skeletal_mesh_component=NS(get_skeletal_mesh_asset=lambda: case.assets[case.profile["target_mesh_path"]]))
    actor.get_actor_label = lambda: "NewPerformer"
    params = NS(get_editor_property=lambda key: {"animation": clip, "start_frame_offset": NS(value=0),
                                                "play_rate": NS(to_fixed_play_rate=lambda: 1.0)}[key])
    section = NS(get_editor_property=lambda _: params)
    track = case.api.MovieSceneSkeletalAnimationTrack()
    track.get_sections = lambda: [section]
    binding = NS(get_tracks=lambda: [track])
    case.api.MovieSceneSequenceExtensions = NS(get_bindings=lambda _: [binding], locate_bound_objects=lambda *_: [actor],
                                               get_tick_resolution=lambda _: NS(numerator=24000, denominator=1))
    case.api.MovieSceneSectionExtensions = NS(get_start_frame=lambda _: 0, get_end_frame=lambda _: 24)
    case.api.UnrealEditorSubsystem = object()
    case.api.get_editor_subsystem = lambda _: NS(get_all_level_actors=lambda: [actor], get_editor_world=object)
    job = {"job_id": "a" * 32, "candidate_dir": str(tmp_path), "sequence_path": "/Game/Staging/LS_New",
           "ai_conversion_decision_sha256": "b" * 64, "character_compatibility_sha256": "c" * 64}
    plan = {"actions": [{"kind": "skeletal_animation", "entity_name": "PrivatePerformer", "unreal_asset_path": case.clip_path,
                          "start_frame": 0, "end_frame": 24, "time_scale": 1.0, "source_offset_seconds": 0.0}]}
    proof = executor.record(case.api, job, plan, selected, Asset(job["sequence_path"], "LevelSequence"))
    assert proof["status"] == ("PASS" if duration == 1.0 else "FAIL")
    assert proof["reopened"] is False
    assert proof["target_playback_sample_status"] == "AWAITING_INDEPENDENT_CINETWIN"


@pytest.mark.parametrize(("case_type", "expected"), [
    ("wrong_guid", "UNITY_GUID_MISMATCH"), ("ambiguous_mesh", "AMBIGUOUS_OR_MISSING_RENDERER_FBX"),
    ("missing_frame", "SOURCE_CAPTURE_INCOMPLETE_OR_UNMATCHED"), ("parented", "PARENTED_OR_COMPETING_ROOT_MOTION_POLICY"),
    ("both_move", "UNPROVEN_MOTION_COMPOSITION"), ("plugin_missing", "TARGET_IK_API_UNAVAILABLE"),
    ("retarget_missing", "TARGET_ASSET_CLASS_OR_BINDING_MISMATCH"), ("dirty_rig", "TARGET_RIG_PACKAGES_UNSAVED"),
    ("existing_clip", "TARGET_CLIP_PATH_UNAVAILABLE_OR_OCCUPIED"),
    ("different_reference_rig", "PREVIEW_SOURCE_HIERARCHY_OR_IMPORT_MISMATCH"),
])
def test_ineligible_character_actions_are_never_offered(case, case_type, expected):
    if case_type == "wrong_guid":
        case.model.with_name(case.model.name + ".meta").write_text("guid: " + "3" * 32 + "\n")
    elif case_type == "ambiguous_mesh":
        case.csir["entities"][0]["metadata"]["source_model_assets"].append({"asset_path": "Assets/Unrelated.fbx", "guid": "3" * 32})
    elif case_type == "missing_frame":
        case.capture["samples"].pop()
    elif case_type == "parented":
        case.csir["entities"][0]["parent_entity_id"] = "parent"
    elif case_type == "both_move":
        case.capture["samples"][3]["entities"][0]["world_transform"] = _pose(2.955)
        case.capture["samples"][3]["skeletal_poses"][0]["bones"][0]["world_transform"] = _pose(3.797)
    elif case_type == "plugin_missing":
        del case.api.IKRetargetBatchOperation
    elif case_type == "retarget_missing":
        del case.assets[case.profile["retargeter_path"]]
    elif case_type == "dirty_rig":
        case.api.EditorLoadingAndSavingUtils.get_dirty_content_packages = lambda: [case.assets[case.profile["retargeter_path"]]]
    elif case_type == "existing_clip":
        case.assets[case.clip_path] = Asset(case.clip_path, "AnimSequence", skeleton=case.target_skeleton)
    elif case_type == "different_reference_rig":
        case.api.AnimPoseExtensions.get_bone_names = lambda _: ["Unrelated"]
    csir_path = _json(Path(case.config["csir"]), case.csir)
    case.capture["source"]["csir_sha256"] = compat.file_digest(csir_path)
    _json(Path(case.config["capture"]), case.capture)
    probe = _probe(case)
    evidence = ai.inspect(case.config, case.census, case.worker, native_character_probe=probe)
    row, = evidence["character_compatibility"]["characters"]
    assert expected in row["reasons"]
    if case_type == "both_move":
        assert row["motion"]["owner"] == "COMPOUND_OR_UNRESOLVED"
        assert row["motion"]["relative_world_offset_drift_cm"] == pytest.approx(84.2)
    assert not evidence["animation_choices"]
    with pytest.raises(ai.TransferAIError, match="without eligible"):
        ai.decide(case.config, case.census, case.worker, native_character_probe=probe,
                  reasoner=lambda _: {"strategy": "native_source", "animation_choice_id": "character-01"})


def test_probe_refuses_wrong_unreal_project_and_map_before_loading_assets(case):
    request = policy.make_probe_request(case.config, case.csir, case.mapping)
    case.api.load_asset = lambda _: pytest.fail("The native probe loaded an asset in the wrong project or map.")
    for project, level in ((case.project.with_name("Other.uproject"), case.level), (case.project, "/Game/Other/Map")):
        with pytest.raises(compat.CompatibilityError, match="Wrong Unreal project or map"):
            native.inspect(case.api, request, project=str(project), level=level)


def test_compatible_same_skeleton_has_a_distinct_report_and_keeps_native_policy(case):
    target = case.assets[case.profile["target_mesh_path"]]
    target.props["skeleton"] = case.source_skeleton
    probe = _probe(case)
    evidence = ai.inspect(case.config, case.census, case.worker, native_character_probe=probe)
    row, = evidence["character_compatibility"]["characters"]
    assert row["status"] == "COMPATIBLE"
    assert row["source_reference_pose_status"] == "UNAVAILABLE_FROM_SOURCE_CAPTURE"
    assert evidence["animation_choices"] == []


@pytest.mark.parametrize("moving_root", [True, False])
def test_actor_and_root_rotation_ownership_is_measured_separately(case, moving_root):
    sample = case.capture["samples"][5]
    rotated = [0, 0, 1, 0]
    if moving_root:
        sample["skeletal_poses"][0]["bones"][0]["world_transform"]["rotation_xyzw"] = rotated
    else:
        sample["entities"][0]["world_transform"]["rotation_xyzw"] = rotated
    _json(Path(case.config["capture"]), case.capture)
    evidence = ai.inspect(case.config, case.census, case.worker, native_character_probe=_probe(case))
    row, = evidence["character_compatibility"]["characters"]
    assert row["motion"]["owner"] == ("SKELETAL_ROOT" if moving_root else "ACTOR_WITH_STABLE_WORLD_OFFSET")
    assert row["motion"]["root_rotation_degrees" if moving_root else "actor_rotation_degrees"] == 180
    assert not evidence["animation_choices"]


def test_anonymized_schema_example_is_marked_synthetic_and_matches_its_report():
    example = _read(ROOT / "docs/studio/examples/friday-animation-conversion.synthetic.json")
    assert example["evidence_origin"] == "SYNTHETIC_TEST_FIXTURE"
    assert example["real_editor_invoked"] is False and example["real_model_invoked"] is False
    report = example["character_compatibility_report"]
    decision = example["ai_animation_conversion_decision"]
    assert policy.selected(report, decision)["id"] == "character-01"
    schema = _read(ROOT / "packages/contracts/studio/ai-animation-conversion-decision-v1.schema.json")
    jsonschema.Draft202012Validator(schema).validate(decision)
