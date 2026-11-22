"""F-003 code-only native/AI contracts. No engine or provider is invoked."""
from __future__ import annotations

import copy
import importlib.util
import json
import math
import sys
import threading
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parents[2]
for folder in ("tools", "packages/cinetwin", "packages/studio", "packages/learning", "integrations/unreal"):
    sys.path.insert(0, str(ROOT / folder))

import animation_conversion_policy as policy
import character_compatibility as compatibility
import character_motion as motion
import csir_plan
import jsonschema
import prepared_transfer
import pytest
import sampling_plan
import studio_ai_transfer_audit as audit
import studio_auto_assets
import studio_candidate
import studio_character_execution as executor
import studio_character_motion as native_motion
import studio_character_probe as probe
import studio_local_bridge as bridge
import studio_release_gate as gate
import studio_transfer_ai as ai
from behavior_compare import BehavioralComparisonError, compare
from test_character_animation_policy import Asset, _json, _probe, _read, case

__all__ = ["case"]


class Key:
    def __init__(self, frame, value, interpolation="linear"):
        self.frame, self.value, self.interpolation = frame, value, interpolation

    def get_time(self):
        return NS(frame_number=NS(value=self.frame), sub_frame=0.0)

    def get_value(self):
        return self.value

    def get_interpolation_mode(self):
        return self.interpolation


class ChannelBase:
    def __init__(self, name=""):
        self.keys, self.default = [], None
        self.channel_name = name

    def add_key(self, frame, value, interpolation="auto"):
        key = Key(frame.value, value, interpolation)
        self.keys.append(key)
        return key

    def get_keys(self):
        return self.keys

    def get_default(self):
        return self.default

    def set_default(self, value):
        self.default = value


class Channel(ChannelBase):
    pass


class FloatChannel(ChannelBase):
    pass


class Params:
    def __init__(self):
        self.values = {"start_frame_offset": NS(value=0)}

    def get_editor_property(self, name):
        return self.values[name]

    def set_editor_property(self, name, value):
        self.values[name] = value


class Section:
    expose_weight = False

    def __init__(self):
        self.channels = [Channel(name) for name in native_motion.CHANNEL_NAMES]
        if self.expose_weight:
            self.channels.append(FloatChannel("Weight"))
        self.params = Params()
        self.post_roll = 0
        self.active = True
        self.blend = "absolute"

    def set_range(self, start, end):
        self.start, self.end = start, end

    def get_editor_property(self, name):
        return getattr(self, name)

    def set_editor_property(self, name, value):
        setattr(self, name, value)

    def set_post_roll_frames(self, count):
        self.post_roll = count

    def get_post_roll_frames(self):
        return self.post_roll

    def set_completion_mode(self, mode):
        self.completion = mode

    def is_active(self):
        return self.active

    def set_is_active(self, active):
        self.active = active

    def get_blend_type(self):
        return NS(blend_type=self.blend, is_valid=True)

    def set_blend_type(self, blend):
        self.blend = blend


class TrackBase:
    def __init__(self):
        self.sections = []

    def set_display_name(self, name):
        self.name = name

    def add_section(self):
        section = Section()
        self.sections.append(section)
        return section

    def get_sections(self):
        return self.sections


class TransformTrack(TrackBase):
    pass


def _transform(position, quaternion):
    return {"position_m": list(position), "rotation_xyzw": list(quaternion), "scale_xyz": [1, 1, 1]}


def _persist(case):
    _json(Path(case.config["csir"]), case.csir)
    case.capture["source"]["csir_sha256"] = compatibility.file_digest(Path(case.config["csir"]))
    _json(Path(case.config["capture"]), case.capture)


def _animate(case, *, rotation_only=False):
    for sample in case.capture["samples"]:
        t = sample["time_seconds"]
        angle = math.radians(120 * t)
        q = [0, math.sin(angle / 2), 0, math.cos(angle / 2)]
        p = [0, 0, 0] if rotation_only else [0.3 + 2*t, 0.2, -0.1 + t*t]
        sample["entities"][0]["world_transform"] = _transform(p, q)
        root_delta = [0.25 * math.cos(angle), 0.75, -0.25 * math.sin(angle)]
        root = [a + b for a, b in zip(p, root_delta)]
        for i, bone in enumerate(sample["skeletal_poses"][0]["bones"]):
            bone["world_transform"] = _transform([root[0], root[1] + i*t, root[2]], q)
            bone["local_transform"] = _transform([0.25, 0.75 + i*t, 0], [0, 0, 0, 1])
    _persist(case)


def _capabilities(api):
    api.Actor = NS(get_attach_parent_actor=lambda: None, get_actor_scale3d=lambda: NS(x=1, y=1, z=1))
    api.PrimitiveComponent = NS(is_simulating_physics=lambda: False)
    api.MovieSceneSection = Section
    api.MovieSceneSkeletalAnimationTrack = type("SkeletalTrack", (TrackBase,), {})
    api.MovieSceneCompletionMode = NS(KEEP_STATE="keep_state")
    api.MovieSceneBlendType = NS(ABSOLUTE="absolute")
    api.log = lambda _: None
    api.MovieScene3DTransformTrack = TransformTrack
    api.MovieSceneScriptingDoubleChannel = Channel
    api.MovieSceneScriptingFloatChannel = FloatChannel
    api.MovieSceneScriptingDoubleKey = Key
    api.FrameNumber = lambda value: NS(value=value)
    api.MovieSceneKeyInterpolation = NS(LINEAR="linear")
    api.RichCurveInterpMode = NS(RCIM_LINEAR="linear")
    api.MovieSceneSectionExtensions = NS(get_all_channels=lambda s: s.channels,
                                         get_start_frame=lambda s: s.start, get_end_frame=lambda s: s.end)
    api.MovieSceneSequenceExtensions = NS(get_bindings=lambda _: [], locate_bound_objects=lambda *_: [],
                                         get_display_rate=lambda _: NS(numerator=24, denominator=1),
                                         get_tick_resolution=lambda _: NS(numerator=24000, denominator=1))
    def root(clip, time):
        delta = float(clip.props.get("root_drift", 0)) * math.sin(math.pi * time)
        turn = float(clip.props.get("root_turn", 0)) * math.sin(math.pi * time)
        return NS(translation=NS(x=delta, y=0, z=0),
                  rotation=NS(x=0, y=0, z=math.sin(turn / 2), w=math.cos(turn / 2)),
                  scale3d=NS(x=1, y=1, z=1))
    api.AnimationLibrary = NS(extract_root_track_transform=root)


@pytest.fixture
def moving(case):
    _capabilities(case.api)
    ref, = case.csir["entities"][0]["metadata"]["source_model_assets"]
    ref["source_sha256"] = compatibility.file_digest(case.model)
    ref["source_meta_sha256"] = compatibility.file_digest(case.model.with_name(case.model.name + ".meta"))
    _animate(case)
    return case


def _choose(case, monkeypatch):
    requests = []
    def response(**kwargs):
        requests.append(kwargs)
        return NS(output_text=json.dumps({"strategy": "native_source", "reason": "Use the registered measured actor strategy.",
                                          "animation_choice_id": "character-01"}))
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-transport")
    monkeypatch.setitem(sys.modules, "openai", NS(OpenAI=lambda **_: NS(responses=NS(create=response))))
    decision = ai.decide(case.config, case.census, case.worker, native_character_probe=_probe(case))
    decision["character_probe_run_id"] = "fixture-run"
    report = decision.pop("character_compatibility")
    assert decision["animation_conversion"]["action_id"] == motion.ACTION
    request, = requests
    assert "bake_verified_actor_world_trajectory" in request["input"]
    for value in (str(case.unity), "PrivatePerformer", "source-char", "/Game/Approved", "synthetic-transport"):
        assert value not in request["input"]
    assert motion.ACTION in request["instructions"] or "actor-world trajectory action" in request["instructions"]
    return report, decision


def _prepare(case, tmp_path, monkeypatch, *, candidate_name="candidate"):
    report, decision = _choose(case, monkeypatch)
    root = tmp_path / candidate_name
    mapping, _ = studio_candidate.prepare_candidate(
        Path(case.config["csir"]), Path(case.config["mapping"]), Path(case.config["capture"]),
        "/Game/Staging/LS_Moving", root, character_selection=(report, decision["animation_conversion"]),
        transfer_options={"source_feature_surface_path": case.census, "require_complete_source_features": False})
    plan = _read(root / "transfer-plan.json")
    manifest = studio_auto_assets.inspect(case.config["csir"], mapping, root / "transfer-plan.json", case.unity,
                                         "Assets", "/Game/Staging/FreshMotion")
    assert manifest["ready"], manifest["blockers"]
    _json(root / policy.REPORT_FILE, report)
    _json(root / "ai-conversion-decision.json", decision)
    _json(root / "automatic-setup.json", manifest)
    job = {"job_id": "a" * 32, "candidate_dir": str(root), "expected_project": str(case.project),
           "expected_level": case.level, "csir": case.config["csir"], "capture": case.config["capture"],
           "sequence_path": plan["sequence_asset_path"], "character_original_mapping": case.config["mapping"],
           "automatic_setup": True, "character_compatibility_sha256": compatibility.file_digest(root / policy.REPORT_FILE),
           "mapping": str(mapping), "automatic_setup_manifest": str(root / "automatic-setup.json"),
           "ai_conversion_decision_sha256": compatibility.file_digest(root / "ai-conversion-decision.json")}
    return NS(report=report, decision=decision, root=root, mapping=_read(mapping), plan=plan, manifest=manifest, job=job)


def _native_scene(case, plan, monkeypatch):
    """Execute the production transform builder, then independently read it."""
    clip = Asset(case.clip_path, "AnimSequence", skeleton=case.target_skeleton,
                 duration=case.csir["assets"][0]["metadata"]["animation_clip"]["duration_seconds"])
    case.assets[case.clip_path] = clip
    actor = Asset("/Game/Staging/NewActor", "SkeletalMeshActor", skeletal_mesh_component=NS(
        get_skeletal_mesh_asset=lambda: case.assets[case.profile["target_mesh_path"]], is_simulating_physics=lambda: False))
    actor.get_actor_label = lambda: "NewPerformer"
    actor.get_attach_parent_actor = lambda: None
    actor.get_actor_scale3d = lambda: NS(x=1, y=1, z=1)
    sequence = Asset(plan["sequence_asset_path"], "LevelSequence")
    sequence.get_playback_end = lambda: plan["duration_frames"]
    sequence.get_display_rate = lambda: NS(**plan["display_rate"])
    tracks = []
    def add_track(kind):
        track = kind()
        tracks.append(track)
        return track
    binding = NS(add_track=add_track, get_tracks=lambda: tracks)
    clip_action, = [a for a in plan["actions"] if a["kind"] == "skeletal_animation"]
    case.api.UnrealEditorSubsystem = object()
    case.api.get_editor_subsystem = lambda _: NS(get_all_level_actors=lambda: [actor], get_editor_world=object)
    case.api.MovieSceneSequenceExtensions = NS(get_bindings=lambda _: [binding], locate_bound_objects=lambda *_: [actor],
        get_tick_resolution=lambda _: NS(numerator=24000, denominator=1),
        get_display_rate=lambda _: NS(**plan["display_rate"]))
    monkeypatch.setitem(sys.modules, "unreal", case.api)
    import unreal_compat
    monkeypatch.setattr(unreal_compat, "unreal", case.api)
    spec = importlib.util.spec_from_file_location("f003_builder_test", ROOT / "integrations/unreal/build_level_sequence.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder._add_skeletal_animation(sequence, binding, clip_action)
    builder._add_transform(sequence, binding, native_motion.action(plan))
    return NS(clip=clip, actor=actor, sequence=sequence, binding=binding, tracks=tracks, builder=builder)


def test_turning_actor_relative_root_and_exact_source_keys(moving, tmp_path, monkeypatch):
    prepared = _prepare(moving, tmp_path, monkeypatch)
    row, = prepared.report["characters"]
    measured = row["motion"]
    assert measured["owner"] == motion.LOCAL_OWNER
    assert measured["relative_world_offset_drift_cm"] > 40
    assert measured["relative_actor_space_drift_cm"] < 1e-10
    assert measured["relative_actor_space_rotation_degrees"] < 1e-5
    transform = native_motion.action(prepared.plan)
    assert len(transform["keys"]) == 25
    assert transform["keys"][-1]["frame"] == 24
    for key, sample in zip(transform["keys"], moving.capture["samples"]):
        world = sample["entities"][0]["world_transform"]
        assert key["location_cm"] == list(csir_plan.canonical_position_to_unreal_cm(world["position_m"]))
        assert key["rotation_rpy_degrees"] == pytest.approx(csir_plan.canonical_quat_to_unreal_rotator(world["rotation_xyzw"]))
    assert transform["keys"][0]["location_cm"] != transform["keys"][-1]["location_cm"]
    assert transform["keys"][0]["rotation_rpy_degrees"] != transform["keys"][-1]["rotation_rpy_degrees"]
    jsonschema.validate(prepared.decision["animation_conversion"], _read(ROOT / "packages/contracts/studio/ai-animation-conversion-decision-v1.schema.json"))
    prepared_transfer.verify(prepared.root)
    assert "ai_character_animation" not in _read(moving.config["mapping"])
    assert executor.preflight(moving.api, prepared.job, prepared.decision, prepared.mapping, prepared.plan,
                              prepared.manifest, worker=moving.worker) == row


def test_rotation_only_actor_is_executable(moving, tmp_path, monkeypatch):
    _animate(moving, rotation_only=True)
    prepared = _prepare(moving, tmp_path, monkeypatch)
    row, = prepared.report["characters"]
    assert row["motion"]["actor_translation_cm"] == 0
    assert row["motion"]["actor_rotation_degrees"] == pytest.approx(120)
    assert len(native_motion.action(prepared.plan)["keys"]) == 25


def test_moving_actor_with_approved_same_skeleton_profile(moving, tmp_path, monkeypatch):
    moving.assets[moving.profile["target_mesh_path"]].props["skeleton"] = moving.source_skeleton
    moving.target_skeleton = moving.source_skeleton
    p = _prepare(moving, tmp_path, monkeypatch)
    assert p.report["characters"][0]["status"] == "COMPATIBLE"
    scene = _native_scene(moving, p.plan, monkeypatch)
    assert executor.record(moving.api, p.job, p.plan, p.report["characters"][0], scene.sequence)["status"] == "PASS"


@pytest.mark.parametrize("fault", ["mixed_translation", "mixed_rotation", "missing_frame", "parent", "actor_scale", "root_scale",
                                  "fbx", "meta", "model_meta", "old_export", "split_take", "humanoid", "loop", "different_rig", "missing_api", "overlap"])
def test_unsupported_moving_cases_refuse_without_native_side_effects(moving, monkeypatch, fault):
    before = set(moving.assets)
    frame = moving.capture["samples"][7]
    if fault == "mixed_translation":
        frame["skeletal_poses"][0]["bones"][0]["world_transform"]["position_m"][0] += 0.1
    elif fault == "mixed_rotation":
        frame["skeletal_poses"][0]["bones"][0]["world_transform"]["rotation_xyzw"] = [0, 0, 0, 1]
    elif fault == "missing_frame":
        moving.capture["samples"].pop(5)
    elif fault == "parent":
        moving.csir["entities"][0]["parent_entity_id"] = "parent"
    elif fault in ("actor_scale", "root_scale"):
        transform = (frame["entities"][0] if fault == "actor_scale" else frame["skeletal_poses"][0]["bones"][0])["world_transform"]
        transform["scale_xyz"][0] = 1.5
    elif fault in ("fbx", "meta", "model_meta"):
        path = moving.model if fault == "fbx" else (moving.model if fault == "model_meta" else moving.clip).with_suffix(".fbx.meta")
        path.write_bytes(path.read_bytes() + b"changed")
    elif fault == "old_export":
        moving.csir["entities"][0]["metadata"]["source_model_assets"][0].pop("source_meta_sha256")
    elif fault in ("split_take", "humanoid", "loop"):
        field = {"split_take": "default_single_fbx_take", "humanoid": "is_humanoid", "loop": "is_looping"}[fault]
        moving.csir["assets"][0]["metadata"]["animation_clip"][field] = fault != "split_take"
    elif fault == "different_rig":
        moving.api.AnimPoseExtensions.get_bone_names = lambda _: ["Unknown"]
    elif fault == "missing_api":
        del moving.api.AnimationLibrary
    else:
        section = copy.deepcopy(moving.csir["tracks"][0]["sections"][0])
        section["section_id"] = "duplicate-owner"
        moving.csir["tracks"][0]["sections"].append(section)
    _persist(moving)
    evidence = ai.inspect(moving.config, moving.census, moving.worker, native_character_probe=_probe(moving))
    assert not evidence["animation_choices"]
    with pytest.raises(ai.TransferAIError, match="without eligible"):
        ai.decide(moving.config, moving.census, moving.worker, native_character_probe=_probe(moving),
                  reasoner=lambda _: {"strategy": "native_source", "animation_choice_id": "character-01"})
    assert set(moving.assets) == before
    assert not list(moving.project.parent.glob("**/LS_*.uasset"))


def test_model_cannot_drop_moving_actor_by_selecting_keep_native(moving):
    with pytest.raises(ai.TransferAIError, match="motion refused"):
        ai.decide(moving.config, moving.census, moving.worker, native_character_probe=_probe(moving),
                  reasoner=lambda _: {"strategy": "native_source", "animation_choice_id": "keep_native"})


def test_missing_root_cannot_bypass_motion_preflight_with_legacy_choice(moving):
    moving.capture["samples"][0]["skeletal_poses"][0]["bones"].pop(0)
    _persist(moving)
    with pytest.raises(ai.TransferAIError, match="motion refused"):
        ai.decide(moving.config, moving.census, moving.worker, native_character_probe=_probe(moving),
                  reasoner=lambda _: {"strategy": "native_source", "animation_choice_id": "keep_native"})


def test_anonymized_moving_example_is_explicitly_synthetic_and_typed():
    example = _read(ROOT / "docs/studio/examples/friday-moving-character.synthetic.json")
    assert example["evidence_origin"] == "SYNTHETIC_TEST_FIXTURE"
    assert example["real_unity_invoked"] is example["real_unreal_invoked"] is example["real_provider_invoked"] is False
    assert example["fidelity_verified"] is False
    assert policy.selected(example["compatibility"], example["decision"])["motion"]["owner"] == motion.LOCAL_OWNER
    jsonschema.validate(example["decision"], _read(ROOT / "packages/contracts/studio/ai-animation-conversion-decision-v1.schema.json"))
    proof = example["mock_native_readback"]
    assert proof["motion"]["frame_count"] == 25
    assert proof["motion"]["section_end_frame"] == 25
    assert proof["observed_sections"][0]["post_roll_ticks"] == 1000


def test_changed_native_package_is_detected_from_cached_probe_on_host(moving, monkeypatch):
    report, decision = _choose(moving, monkeypatch)
    cached = _probe(moving)
    (moving.project.parent / "Content/Approved/TargetRig.uasset").write_bytes(b"new saved rig")
    with pytest.raises(ai.TransferAIError, match="stale"):
        ai.verify(decision, moving.config, moving.census, moving.worker, native_character_probe=cached)
    assert report["characters"][0]["status"] == "COMPATIBLE_AFTER_APPROVED_RETARGET"


@pytest.mark.parametrize("rate", [24, 30, 60])
def test_supported_display_rates_produce_every_measured_frame(moving, tmp_path, monkeypatch, rate):
    frequency = {"numerator": rate, "denominator": 1}
    moving.csir["timing"].update(source_rate=frequency, display_rate=frequency)
    _json(Path(moving.config["csir"]), moving.csir)
    plan = sampling_plan.build_plan(moving.csir, csir_sha256=compatibility.file_digest(Path(moving.config["csir"])))
    template = copy.deepcopy(moving.capture["samples"][0])
    moving.capture["samples"] = [dict(copy.deepcopy(template), time_seconds=t["time_seconds"]) for t in plan["samples"]]
    _animate(moving)
    p = _prepare(moving, tmp_path, monkeypatch)
    assert p.plan["display_rate"] == frequency
    assert len(native_motion.action(p.plan)["keys"]) == rate + 1


def test_fractional_frame_rate_trim_and_speed_are_source_bound(moving, tmp_path, monkeypatch):
    frequency = {"numerator": 30000, "denominator": 1001}
    moving.csir["timing"].update(source_rate=frequency, display_rate=frequency, duration_seconds=1.001,
                               playback_end={"value": 30, "rate": frequency})
    section, = moving.csir["tracks"][0]["sections"]
    section.update(end={"value": 30, "rate": frequency}, source_offset={"value": 1, "rate": {"numerator": 4, "denominator": 1}}, time_scale=2.0)
    moving.csir["assets"][0]["metadata"]["animation_clip"].update(duration_seconds=2.5, frame_rate=30)
    _json(Path(moving.config["csir"]), moving.csir)
    plan = sampling_plan.build_plan(moving.csir, csir_sha256=compatibility.file_digest(Path(moving.config["csir"])))
    template = copy.deepcopy(moving.capture["samples"][0])
    moving.capture["samples"] = [dict(copy.deepcopy(template), time_seconds=t["time_seconds"]) for t in plan["samples"]]
    _animate(moving)
    p = _prepare(moving, tmp_path, monkeypatch)
    assert p.plan["duration_frames"] == 30
    assert len(native_motion.action(p.plan)["keys"]) == 31
    scene = _native_scene(moving, p.plan, monkeypatch)
    proof = executor.record(moving.api, p.job, p.plan, p.report["characters"][0], scene.sequence)
    assert proof["status"] == "PASS", proof
    assert proof["observed_sections"][0]["source_trim_ticks"] == 6000
    assert proof["observed_sections"][0]["time_scale"] == 2


def test_unproven_grid_and_duplicate_timestamps_are_refused(moving):
    changed = copy.deepcopy(moving.csir)
    changed["timing"]["playback_start"]["value"] = 1
    with pytest.raises(motion.MotionError):
        motion.trajectory(changed, moving.capture, "source-char")
    changed = copy.deepcopy(moving.csir)
    changed["timing"]["playback_end"]["subframe"] = {"numerator": 1, "denominator": 2}
    with pytest.raises(motion.MotionError):
        motion.trajectory(changed, moving.capture, "source-char")
    moving.capture["samples"].append(moving.capture["samples"][0])
    with pytest.raises(motion.MotionError, match="DUPLICATE"):
        motion.trajectory(moving.csir, moving.capture, "source-char")


@pytest.mark.parametrize("fault", ["fbx", "meta", "target_package", "worker", "disconnected", "map", "project", "occupied_sequence", "occupied_scratch"])
def test_native_preflight_revalidates_every_identity_before_mutation(moving, tmp_path, monkeypatch, fault):
    p = _prepare(moving, tmp_path, monkeypatch)
    if fault == "fbx":
        moving.model.write_bytes(b"new source")
    elif fault == "meta":
        moving.clip.with_name(moving.clip.name + ".meta").write_text("guid: " + "2" * 32 + "\nchanged importer\n")
    elif fault == "target_package":
        (moving.project.parent / "Content/Approved/TargetRig.uasset").write_bytes(b"changed native rig")
    elif fault in ("worker", "disconnected", "map", "project"):
        key, value = {"worker": ("editor_pid", -1), "disconnected": ("connected", False),
                      "map": ("level", "/Game/Other/Map"), "project": ("project", str(moving.project.with_name("Other.uproject")))}[fault]
        moving.worker[key] = value
    else:
        path = p.job["sequence_path"] if fault == "occupied_sequence" else next(
            r["source_animation_path"] for r in p.manifest["imports"] if r.get("source_animation_path"))
        moving.assets[path] = Asset(path, "LevelSequence" if fault == "occupied_sequence" else "AnimSequence")
    snapshot = copy.copy(moving.assets)
    with pytest.raises((ValueError, RuntimeError)):
        executor.preflight(moving.api, p.job, p.decision, p.mapping, p.plan, p.manifest, worker=moving.worker)
    assert moving.assets == snapshot
    assert not (p.root / "character-native-attempt.json").exists()


@pytest.mark.parametrize("fault", ["key", "frame", "rotation", "worker_binding", "sequence", "rate", "root_owner"])
def test_immutable_motion_plan_refuses_tampering(moving, tmp_path, monkeypatch, fault):
    p = _prepare(moving, tmp_path, monkeypatch)
    transform = native_motion.action(p.plan)
    if fault == "key":
        transform["keys"][3]["location_cm"][1] += 1
    elif fault == "frame":
        transform["keys"][3]["frame"] += 1
    elif fault == "rotation":
        transform["keys"][3]["rotation_rpy_degrees"][2] += 90
    elif fault == "worker_binding":
        p.plan["ai_character_motion_binding"]["worker"]["editor_pid"] += 1
    elif fault == "sequence":
        p.plan["sequence_asset_path"] += "_Other"
    elif fault == "rate":
        p.plan["display_rate"]["numerator"] = 30
    else:
        p.plan["actions"].append({"kind": "skeletal_world_root_lock", "entity_name": "PrivatePerformer"})
    with pytest.raises(ValueError):
        policy.verify_plan(p.report, p.decision["animation_conversion"], p.mapping, p.plan, p.manifest)


@pytest.mark.parametrize("fault", [None, "position", "rotation", "missing_key", "interpolation", "binding", "extra_track", "range", "scale", "root_translation", "root_rotation", "rate", "target_parent", "target_scale", "physics", "post_roll", "inactive", "additive"])
def test_production_builder_and_independent_native_readback(moving, tmp_path, monkeypatch, fault):
    p = _prepare(moving, tmp_path, monkeypatch)
    scene = _native_scene(moving, p.plan, monkeypatch)
    transform = scene.tracks[1]
    section, = transform.get_sections()
    if fault in ("position", "rotation"):
        section.channels[0 if fault == "position" else 5].keys[6].value += 1
    elif fault == "missing_key":
        section.channels[1].keys.pop()
    elif fault == "interpolation":
        section.channels[0].keys[2].interpolation = "cubic"
    elif fault == "binding":
        moving.api.MovieSceneSequenceExtensions.locate_bound_objects = lambda *_: []
    elif fault == "extra_track":
        scene.tracks.append(TransformTrack())
    elif fault == "range":
        section.end = 23
    elif fault == "scale":
        section.channels[6].default = 2
    elif fault in ("root_translation", "root_rotation"):
        scene.clip.props["root_drift" if fault == "root_translation" else "root_turn"] = 0.5
    elif fault == "rate":
        moving.api.MovieSceneSequenceExtensions.get_display_rate = lambda _: NS(numerator=30, denominator=1)
    elif fault == "target_parent":
        scene.actor.get_attach_parent_actor = object
    elif fault == "target_scale":
        scene.actor.get_actor_scale3d = lambda: NS(x=2, y=1, z=1)
    elif fault == "physics":
        scene.actor.props["skeletal_mesh_component"].is_simulating_physics = lambda: True
    elif fault == "post_roll":
        scene.tracks[0].get_sections()[0].set_post_roll_frames(0)
    elif fault == "inactive":
        section.set_is_active(False)
    elif fault == "additive":
        section.set_blend_type("additive")
    proof = executor.record(moving.api, p.job, p.plan, p.report["characters"][0], scene.sequence)
    assert proof["status"] == ("PASS" if fault is None else "FAIL"), proof
    assert proof["fidelity_verified"] is False
    assert motion.receipt_matches(proof, p.plan) is (fault is None)
    if fault is None:
        assert proof["motion"]["frame_count"] == 25
        assert proof["motion"]["native_roots"]["roots"][0]["sample_count"] == 25
    else:
        assert proof.get("reason")


def test_partial_native_attempt_never_replays_even_when_no_sequence_exists(moving, tmp_path, monkeypatch):
    p = _prepare(moving, tmp_path, monkeypatch)
    executor.preflight(moving.api, p.job, p.decision, p.mapping, p.plan, p.manifest, worker=moving.worker)
    executor.begin(p.job, p.plan)
    journal = p.root / "character-native-attempt.json"
    assert _read(journal)["status"] == "STARTED_NO_REPLAY"
    with pytest.raises(FileExistsError):
        executor.begin(p.job, p.plan)
    with pytest.raises(RuntimeError, match="already executed"):
        executor.preflight(moving.api, p.job, p.decision, p.mapping, p.plan, p.manifest, worker=moving.worker)
    scene = _native_scene(moving, p.plan, monkeypatch)
    scene.clip.props["root_drift"] = 3
    with pytest.raises(RuntimeError, match="preserve partial"):
        executor.validate_staged(moving.api, p.job, p.plan)
    assert _read(p.root / "character-staged-motion.json")["status"] == "FAIL"
    assert journal.is_file() and moving.assets[moving.clip_path] is scene.clip
    with pytest.raises(FileExistsError):
        executor.validate_staged(moving.api, p.job, p.plan)


def test_source_change_during_import_halts_before_sequence_execution(moving, tmp_path, monkeypatch):
    p = _prepare(moving, tmp_path, monkeypatch)
    executor.begin(p.job, p.plan)
    scene = _native_scene(moving, p.plan, monkeypatch)
    moving.clip.write_bytes(b"synthetic Unity import changed while native staging ran")
    with pytest.raises(RuntimeError, match="preserve partial"):
        executor.validate_staged(moving.api, p.job, p.plan)
    assert _read(p.root / "character-staged-motion.json")["status"] == "FAIL"
    assert _read(p.root / "character-native-attempt.json")["status"] == "STAGED_MOTION_FAILED_NO_REPLAY"
    assert moving.assets[moving.clip_path] is scene.clip


@pytest.mark.parametrize("fault", [None, "weight_keys", "weight_default", "constraint", "duplicate_channel"])
def test_native_mixed_channel_layout_has_typed_transform_and_safe_manual_weight(moving, tmp_path, monkeypatch, fault):
    monkeypatch.setattr(Section, "expose_weight", True)
    p = _prepare(moving, tmp_path, monkeypatch)
    scene = _native_scene(moving, p.plan, monkeypatch)
    section, = scene.tracks[1].get_sections()
    assert len(section.channels) == 10
    weight = section.channels[-1]
    assert weight.get_default() == 1
    if fault == "weight_keys":
        weight.keys.append(Key(0, 0.5))
    elif fault == "weight_default":
        weight.default = 0
    elif fault == "constraint":
        weight.channel_name = "Constraint"
    elif fault == "duplicate_channel":
        section.channels[0].channel_name = section.channels[1].channel_name
    # Native enumeration order is irrelevant to the semantic-name reader.
    section.channels.reverse()
    proof = executor.record(moving.api, p.job, p.plan, p.report["characters"][0], scene.sequence)
    assert proof["status"] == ("PASS" if fault is None else "FAIL"), proof


def test_builder_refuses_root_motion_before_sequence_allocation(moving, tmp_path, monkeypatch):
    p = _prepare(moving, tmp_path, monkeypatch)
    scene = _native_scene(moving, p.plan, monkeypatch)
    scene.clip.props["root_drift"] = 0.5
    with pytest.raises(RuntimeError, match="competing skeletal-root"):
        scene.builder._preflight(p.plan)


def test_reopened_character_readback_preserves_the_generation_attempt(moving, tmp_path, monkeypatch):
    p = _prepare(moving, tmp_path, monkeypatch)
    executor.begin(p.job, p.plan)
    scene = _native_scene(moving, p.plan, monkeypatch)
    receipt = executor.record(moving.api, p.job, p.plan, p.report["characters"][0], scene.sequence)
    before = (p.root / "character-native-attempt.json").read_bytes()
    reopened = executor.record(moving.api, p.job, p.plan, p.report["characters"][0], scene.sequence,
                               path=p.root / "reopened.mock.json", reopened=True)
    assert receipt["status"] == reopened["status"] == "PASS"
    assert reopened["reopened"] is True and reopened["fidelity_verified"] is False
    assert (p.root / "character-native-attempt.json").read_bytes() == before


def test_action_schema_cannot_mix_motion_and_in_place_capabilities(moving, monkeypatch):
    report, decision = _choose(moving, monkeypatch)
    choice = decision["animation_conversion"]
    choice["capability_id"] = policy.CATALOG[policy.ACTION]["capability_id"]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(choice, _read(ROOT / "packages/contracts/studio/ai-animation-conversion-decision-v1.schema.json"))
    with pytest.raises(ValueError, match="Stale or unregistered"):
        policy.selected(report, choice)


@pytest.mark.parametrize("fault", [None, "import", "root", "readback", "disconnect"])
def test_real_editor_worker_executes_guarded_motion_lifecycle(moving, tmp_path, monkeypatch, fault):
    """The real worker queue/execute methods retain every F-003 safety hook.

    Only engine IO and unrelated audit domains are mocked. Preparation, source
    verification, native preflight, root inspection, key writing and character
    readback use production code. Disconnect is a synthetic abrupt termination.
    """
    import importlib

    import studio_planner_sync

    class SyntheticDisconnect(BaseException):
        pass

    workspace = tmp_path / "work"
    p = _prepare(
        moving, workspace / "candidates", monkeypatch,
        candidate_name="20261121T183000Z_deadbeef",
    )
    manifest_file = _json(p.root / "automatic-setup.json", p.manifest)
    job = {
        **p.job, "kind": "cutsceneai.studio.local_unreal_job",
        "schema_version": "0.1.0", "status": "QUEUED",
        "candidate_id": p.root.name,
        "mapping": str(p.root.with_suffix(".mapping.json")),
        "automatic_setup_manifest": str(manifest_file),
        "ai_agents_enabled": True,
    }
    job_file = _json(workspace / "jobs" / (job["job_id"] + ".json"), job)
    # Match the production active-candidate/active-job ownership contracts.
    # The native worker must not run a request merely because a file named
    # QUEUED was dropped in the jobs directory by a different process.
    _json(workspace / "active-candidate.json", {
        "candidate_id": p.root.name, "mapping_copy": job["mapping"],
        "sequence_path": job["sequence_path"],
    })
    _json(workspace / "active-job.json", {"job_id": job["job_id"]})
    monkeypatch.setitem(sys.modules, "unreal", moving.api)
    for name in ("log", "log_warning", "log_error"):
        setattr(moving.api, name, lambda _: None)
    spec = importlib.util.spec_from_file_location("f003_worker_test", ROOT / "integrations/unreal/studio_local_editor_worker.py")
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    worker.WORKSPACE = workspace
    worker.LAST_TICK = 0
    monkeypatch.setattr(worker, "_loaded_project", lambda: str(moving.project))
    monkeypatch.setattr(worker, "_loaded_level", lambda: moving.level)
    monkeypatch.setattr(worker, "_native_level_inventory", lambda: moving.worker["scene_inventory"])
    monkeypatch.setattr(worker, "_update_destination_readiness", lambda: _json(workspace / "destination-readiness.json",
        {"candidate_id": job["candidate_id"], "ready": True}))
    effects, generated = [], []
    monkeypatch.setattr(worker, "_ensure_target_level", lambda _: effects.append("level"))
    # The real synchronizer is covered by its dedicated suite. Retain test IO
    # mocks while executing the actual worker method and preflight below.
    reload_module = importlib.reload
    monkeypatch.setattr(importlib, "reload", lambda mod: mod if mod is studio_planner_sync else reload_module(mod))
    monkeypatch.setattr(studio_planner_sync, "synchronize", dict)

    def setup(_manifest, receipt, **_kwargs):
        effects.append("import")
        staged = {"status": "SETUP_SAVED_UNVERIFIED", "assets_imported": [], "actors_created": []}
        scene = _native_scene(moving, p.plan, monkeypatch)
        generated.append(scene)
        if fault in ("import", "disconnect"):
            staged["status"] = "PARTIAL_SETUP_MUST_INSPECT"
            _json(Path(receipt), staged)
            if fault == "disconnect":
                raise SyntheticDisconnect("synthetic worker process loss during native import")
            raise RuntimeError("synthetic partial import")
        if fault == "root":
            scene.clip.props["root_drift"] = 5
        _json(Path(receipt), staged)
        return staged

    monkeypatch.setitem(sys.modules, "studio_auto_scene", NS(run=setup, _save_level=lambda *_: effects.append("save")))
    # Import the native builder against the synthetic API, then replace only
    # its whole-project IO entrypoint. _native_scene uses its real key writer.
    builder_spec = importlib.util.spec_from_file_location("build_level_sequence", ROOT / "integrations/unreal/build_level_sequence.py")
    builder = importlib.util.module_from_spec(builder_spec)
    builder_spec.loader.exec_module(builder)
    def build(*_args, **_kwargs):
        effects.append("build")
        scene, = generated
        if fault == "readback":
            scene.tracks[1].get_sections()[0].channels[0].keys[3].value += 5
        return scene.sequence
    monkeypatch.setattr(builder, "build_prepared_files", build)
    monkeypatch.setitem(sys.modules, "build_level_sequence", builder)
    monkeypatch.setitem(sys.modules, "studio_agent_executor", NS(service_one=lambda *_args, **_kwargs: None))
    monkeypatch.setitem(sys.modules, "diagnose_cinetwin_parity", NS(run=lambda **_: {}))
    monkeypatch.setitem(sys.modules, "studio_visual_audit", NS(audit_latest=lambda *_args, **_kwargs: {"status": "NOT_TESTED"}))
    monkeypatch.setitem(sys.modules, "studio_generation_readback", NS(capture=lambda *_args, **_kwargs: {"native_structure": "INCOMPLETE"}))
    if fault == "disconnect":
        with pytest.raises(SyntheticDisconnect):
            worker._tick(0)
    else:
        worker._tick(0)
    observed = _read(job_file)
    attempt = _read(p.root / "character-native-attempt.json")
    if fault is None:
        assert observed["character_native_readback_status"] == "PASS", observed.get("error")
        assert attempt["status"] == "READBACK_PASS_NO_REPLAY"
        assert effects == ["level", "import", "build", "save"]
    elif fault == "readback":
        assert observed["generation_status"] == "NATIVE_ANIMATION_READBACK_FAILED"
        assert observed["character_native_readback_status"] == "FAIL"
        assert attempt["status"] == "READBACK_FAIL_NO_REPLAY"
    elif fault == "disconnect":
        assert observed["status"] == "RUNNING"
        assert attempt["status"] == "STARTED_NO_REPLAY"
    else:
        assert "build" not in effects
        assert observed["failure_stage"] == ("IMPORTING_ASSETS_AND_CREATING_ACTORS" if fault == "import" else "VERIFYING_STAGED_CHARACTER_MOTION")
        assert attempt["status"] == "FAILED_NO_REPLAY"
    # Recovered RUNNING, terminal failure and completed candidates all stay
    # out of the execution queue, even if the process disappeared mid-import.
    count = list(effects)
    worker.LAST_TICK = 0
    worker._tick(0)
    assert effects == count
    assert moving.assets[moving.clip_path] is generated[0].clip


def test_independent_frame_matched_actor_and_root_measurement(moving):
    plan = sampling_plan.build_plan(moving.csir, csir_sha256=compatibility.file_digest(Path(moving.config["csir"])))
    target = {"kind": "cinetwin.target_behavior_observation", "cutscene_id": plan["cutscene_id"], "source": plan["source"],
              "coverage": {"full_temporal_coverage": True, "sample_count": len(plan["samples"]), "unmapped_source_entities": []},
              "native_rigs": [{"entity_id": "source-char", "native_target_bones": [
                  {"bone_name": "Root", "parent_bone_name": None}, {"bone_name": "Arm", "parent_bone_name": "Root"}]}],
              "samples": []}
    for sample in moving.capture["samples"]:
        entities = [dict(copy.deepcopy(e), actor_label="NewPerformer") for e in sample["entities"]]
        target["samples"].append({"time_seconds": sample["time_seconds"], "entities": entities,
            "skeletal_poses": [{"entity_id": "source-char", "bones": [
                {"bone_name": "Root" if b["bone_id"] == "root-id" else "Arm", "world_position_m": b["world_transform"]["position_m"],
                 "unreal_world_rotation_xyzw": b["world_transform"]["rotation_xyzw"]}
                for b in sample["skeletal_poses"][0]["bones"]]}]})
    baseline = compare(plan, moving.capture, target)
    assert baseline["entities"][0]["max_world_position_error_cm"] == 0
    assert baseline["entities"][0]["max_world_rotation_error_degrees"] < 1e-5
    assert baseline["rig_motion_diagnostics"][0]["skeletal_root_world"]["max_world_position_error_cm"] == 0
    target["samples"][4]["entities"][0]["world_transform"]["position_m"][0] += 0.05
    target["samples"][4]["entities"][0]["world_transform"]["rotation_xyzw"] = [0, 0, 0, 1]
    target["samples"][4]["skeletal_poses"][0]["bones"][0]["world_position_m"] = [9, 9, 9]
    result = compare(plan, moving.capture, target)
    assert result["evaluation"]["status"] == "DIFFERENCES_DETECTED"
    assert result["entities"][0]["max_world_position_error_cm"] == pytest.approx(5)
    assert result["entities"][0]["max_world_rotation_error_degrees"] > 1
    assert result["rig_motion_diagnostics"][0]["skeletal_root_world"]["max_world_position_error_cm"] > 5
    target["samples"].pop(3)
    with pytest.raises(BehavioralComparisonError):
        compare(plan, moving.capture, target)


def test_one_click_selects_motion_and_native_failure_is_not_release_success(moving, tmp_path, monkeypatch):
    import studio_autopilot as autopilot
    _choose(moving, monkeypatch)
    workspace = tmp_path / "runs"
    config = bridge.config_check({**moving.config, "source_rights_confirmed": True, "skeletal_root_world_lock": False})
    _json(workspace / "connection.json", config)
    _json(workspace / autopilot.ACTIVE, {"status": "ANALYZING_PROJECTS", "run_id": "moving-run", "census_path": moving.census})
    service = NS(lock=threading.RLock(), worker_connected=lambda _: moving.worker, load_json=bridge.load_json,
                 prepare=bridge.prepare, approve_one_click=bridge.approve_one_click)
    assert autopilot.advance(workspace, service=service)["status"] == "ANALYZING_PROJECTS"
    probe.service(workspace, moving.api, project=str(moving.project), level=moving.level, save=bridge.atomic_json)
    assert autopilot.advance(workspace, service=service)["status"] == "PREPARING"
    ready = autopilot.advance(workspace, service=service)
    assert ready["status"] == "WAITING_FOR_UNREAL", ready
    worker = {**moving.worker, "worker_version": bridge.REQUIRED_WORKER_PROTOCOL, "checkout_root": str(ROOT),
              "worker_source_sha256": compatibility.file_digest(ROOT / "integrations/unreal/studio_local_editor_worker.py")}
    monkeypatch.setattr(bridge, "worker_connected", lambda _: worker)
    monkeypatch.setattr(bridge, "destination_readiness", lambda _: {"ready": False, "status": "SCENE_SETUP_REQUIRED"})
    queued = bridge.queue_trial(ready["candidate_id"], workspace)
    job_path = workspace / "jobs" / (queued["job_id"] + ".json")
    job = _read(job_path)
    candidate = Path(job["candidate_dir"])
    plan = _read(candidate / "transfer-plan.json")
    decision = _read(candidate / "ai-conversion-decision.json")
    assert decision["animation_conversion"]["action_id"] == motion.ACTION
    assert audit.assess(workspace, job["job_id"])["character_conversion"]["native_readback_passed"] is False
    executor.begin(job, plan)
    scene = _native_scene(moving, plan, monkeypatch)
    executor.validate_staged(moving.api, job, plan)
    row = _read(candidate / policy.REPORT_FILE)["characters"][0]
    proof = executor.record(moving.api, job, plan, row, scene.sequence)
    assert proof["status"] == "PASS", proof
    receipt = candidate / ("unreal-runtime-receipt-" + job["job_id"] + ".json")
    _json(receipt, {"kind": "cutsceneai.unreal.best_effort_receipt", "status": "GENERATED_UNVERIFIED", "stage": "complete",
                    "verified_project": job["expected_project"], "verified_level": job["expected_level"],
                    "transfer_plan_sha256": compatibility.file_digest(candidate / "transfer-plan.json"),
                    "generated_sequence": scene.sequence.get_path_name()})
    job.update(status="GENERATED_AND_MEASURED_NOT_FIDELITY_VERIFIED", generation_status="GENERATED_UNVERIFIED",
               generated_sequence=scene.sequence.get_path_name(), receipt_file=str(receipt), character_native_readback_status="PASS")
    _json(job_path, job)
    assessed = audit.assess(workspace, job["job_id"])
    assert assessed["character_conversion"]["native_readback_passed"] is True
    assessed = gate.assess(workspace, job["job_id"])
    assert assessed["checks"]["ai_native_character_conversion"]["status"] == "PASS"
    assert assessed["release_ready"] is False
    # A skeleton/section-only receipt can never stand in for motion readback.
    proof.pop("motion")
    _json(candidate / policy.NATIVE_FILE, proof)
    assert audit.assess(workspace, job["job_id"])["character_conversion"]["native_readback_passed"] is False
    assert gate.assess(workspace, job["job_id"])["checks"]["ai_native_character_conversion"]["status"] == "FAIL"
    with pytest.raises(ValueError, match="already submitted"):
        bridge.queue_trial(ready["candidate_id"], workspace)
