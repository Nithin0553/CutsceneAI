"""Real Unreal source-independent visual audit: native material/env evidence, not guesswork."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "integrations" / "unreal"))
import studio_visual_audit as visual


class Klass:
    def __init__(self, name):
        self.name = name

    def get_name(self):
        return self.name


class Native:
    def __init__(self, klass, **attrs):
        self.klass = klass
        self.attrs = attrs

    def get_class(self):
        return Klass(self.klass)

    def get_path_name(self):
        return self.attrs.get("path", "")


class Renderer(Native):
    def __init__(self, kind, slots):
        super().__init__(kind)
        self.slots = slots

    def get_num_materials(self):
        return len(self.slots)

    def get_material(self, index):
        value = self.slots[index]
        return Native("Material", path=value) if value else None


class Actor(Native):
    def __init__(self, label, kind, renderers=None):
        super().__init__(kind)
        self.label = label
        self.renderers = renderers or []

    def get_actor_label(self):
        return self.label

    def get_components_by_class(self, klass):
        return [c for c in self.renderers if c.klass == klass]


class Sequence(Native):
    def __init__(self, tracks):
        super().__init__("LevelSequence")
        self.tracks = tracks

    def get_tracks(self):
        return self.tracks

    def get_bindings(self):
        return []


class World:
    def get_path_name(self):
        return "/Game/Testing/L_Benchmark002.L_Benchmark002"


class Editor:
    def __init__(self, actors):
        self.actors = actors

    def get_all_level_actors(self):
        return self.actors


def fake_unreal(actors, sequence):
    class Unreal:
        EditorActorSubsystem = "actor-system"
        UnrealEditorSubsystem = "editor-system"
        SkeletalMeshComponent = "SkeletalMeshComponent"
        StaticMeshComponent = "StaticMeshComponent"
        Paths = SimpleNamespace(
            get_project_file_path=lambda: "C:/Unreal/MyProject.uproject",
            convert_relative_path_to_full=lambda p: p,
        )

        @staticmethod
        def load_asset(path):
            assert path == "/Game/Testing/LS_Benchmark002"
            return sequence

        @staticmethod
        def get_editor_subsystem(which):
            if which == "actor-system":
                return Editor(actors)
            if which == "editor-system":
                return SimpleNamespace(get_editor_world=lambda: World())
            raise AssertionError("Unexpected editor subsystem")
    return Unreal


def test_missing_materials_and_sky_are_reported_not_called_fidelity_pass():
    seq = Sequence([Native("MovieSceneCameraCutTrack"), Native("MovieSceneAudioTrack")])
    actors = [
        Actor("CSAI_A", "SkeletalMeshActor", [
            Renderer("SkeletalMeshComponent", [
                "/Engine/EngineMaterials/DefaultMaterial.DefaultMaterial", ""
            ])
        ]),
        Actor("CSAI_B", "SkeletalMeshActor", [
            Renderer("SkeletalMeshComponent", ["/Game/Materials/M_Character"])
        ]),
        Actor("LIGHT", "PointLight"),
    ]
    report = visual.inspect_scene(fake_unreal(actors, seq), seq, {"CSAI_A", "CSAI_B"})
    assert report["material_slots"] == 3
    assert report["material_slots_engine_default"] == 1
    assert report["material_slots_empty"] == 1
    assert report["material_slots_nondefault"] == 1
    assert report["environment_actor_counts"]["SkyLight"] == 0
    assert report["sequencer_track_counts"]["MovieSceneCameraCutTrack"] == 1
    assert "NO_SKYLIGHT_OR_SKY_ATMOSPHERE_FOUND" in report["visual_issues"]
    assert "RENDER_MATERIALS_MISSING_OR_ENGINE_DEFAULT" in report["visual_issues"]
    assert report["status"] == "VISUAL_COMPLETENESS_REVIEW_REQUIRED"
    assert report["audio_fidelity_verified"] is False


def test_complete_native_tracks_still_do_not_prove_source_render_parity():
    seq = Sequence([Native("MovieSceneCameraCutTrack")])
    seq.get_bindings = lambda: [
        SimpleNamespace(get_tracks=lambda: [Native("MovieSceneSkeletalAnimationTrack")])
    ]
    api = fake_unreal([
        Actor("CSAI_A", "SkeletalMeshActor", [
            Renderer("SkeletalMeshComponent", ["/Game/Materials/M_Correct"])
        ]),
        Actor("SKY", "SkyLight"), Actor("SUN", "DirectionalLight"),
    ], seq)
    report = visual.inspect_scene(api, seq, {"CSAI_A"})
    assert report["status"] == "NATIVE_VISUAL_PREREQUISITES_PRESENT_PARITY_UNVERIFIED"
    assert report["source_rendering_fidelity_verified"] is False
    assert report["skeletal_pose_fidelity_verified"] is False


def test_visual_audit_is_candidate_scoped_and_immutable(tmp_path):
    workspace = tmp_path / "runs"
    jobid = "a" * 32
    target = workspace / "candidates" / "fresh"
    target.mkdir(parents=True)
    (workspace / "jobs").mkdir()
    (workspace / "active-job.json").write_text(json.dumps({"job_id": jobid}))
    (workspace / "jobs" / f"{jobid}.json").write_text(json.dumps({
        "job_id": jobid, "candidate_id": "fresh",
        "candidate_dir": str(target),
        "expected_project": "C:/Unreal/MyProject.uproject",
        "expected_level": "/Game/Testing/L_Benchmark002",
        "sequence_path": "/Game/Testing/LS_Benchmark002",
    }))
    (target / "transfer-plan.json").write_text(json.dumps({
        "sequence_asset_path": "/Game/Testing/LS_Benchmark002",
        "bindings": {"A": "CSAI_A"},
    }))
    seq = Sequence([Native("MovieSceneCameraCutTrack")])
    api = fake_unreal([Actor("CSAI_A", "SkeletalMeshActor")], seq)
    report = visual.audit_latest(workspace, api)
    assert report["job_id"] == jobid
    saved = list(target.glob(f"visual-audit-{jobid}-*.json"))
    assert len(saved) == 1
    assert json.loads(saved[0].read_text())["status"] == report["status"]
    visual.audit_latest(workspace, api)
    assert len(list(target.glob(f"visual-audit-{jobid}-*.json"))) == 2
    assert not list(target.glob("post-reopen-audit*"))


def test_visual_audit_refuses_foreign_workspace_paths(tmp_path):
    workspace = tmp_path / "runs"
    (workspace / "jobs").mkdir(parents=True)
    jobid = "b" * 32
    (workspace / "active-job.json").write_text(json.dumps({"job_id": jobid}))
    (workspace / "jobs" / f"{jobid}.json").write_text(json.dumps({
        "job_id": jobid,
        "candidate_dir": str(tmp_path / "other" / "bad"),
    }))
    with pytest.raises(visual.VisualAuditError, match="outside"):
        visual.audit_latest(workspace, fake_unreal([], None))


def test_results_ui_exposes_visual_audit_command():
    app = (ROOT / "apps" / "studio-web" / "app.js").read_text(encoding="utf-8")
    assert "studio_visual_audit as visual" in app
    assert "visual.audit_latest()" in app
    assert "Default engine materials" in app
    assert "SkyLight / SkyAtmosphere" in app
