"""Engine-independent regressions and editor-mock checks for staged root lock."""
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
for folder in ("packages/studio", "integrations/unreal"):
    sys.path.insert(0, str(ROOT / folder))

import root_world_lock
import cinetwin_root_world_lock


def fixture():
    csir = {
        "cutscene_id": "source",
        "timing": {
            "source_rate": {"numerator": 2, "denominator": 1},
            "playback_start": {"value": 0, "rate": {"numerator": 1, "denominator": 1}},
            "playback_end": {"value": 3, "rate": {"numerator": 2, "denominator": 1}},
        },
    }
    entity = {"name": "Animated", "entity_id": "rigA"}
    root = "Actor[0]/mixamorig9:Hips[7]"
    capture = {
        "rigs": [{"entity_id": "rigA", "bones": [{
            "bone_id": root, "parent_bone_id": "", "hierarchy_path": root,
        }]}],
        "samples": [{
            "time_seconds": frame / 2.0,
            "skeletal_poses": [{
                "entity_id": "rigA", "bones": [{
                    "bone_id": root,
                    "world_transform": {
                        "position_m": [0.0, 1.0, -frame],
                    },
                }],
            }],
        } for frame in range(4)],
    }
    return csir, entity, capture


def test_root_observations_use_unique_top_bone_and_exclude_end_boundary():
    csir, entity, capture = fixture()
    result = root_world_lock.source_root_world_keys(csir, capture, entity)
    assert result["root_bone_alias"] == "hips"
    assert [x["frame"] for x in result["keys"]] == [0, 1, 2]
    assert [x["source_root_world_cm"] for x in result["keys"]] == [
        [0, 0, 100], [100, 0, 100], [200, 0, 100]
    ]
    assert result["source_root_excursion_cm"] == 200.0


def test_duplicate_rig_bones_fail_closed():
    csir, entity, capture = fixture()
    capture["rigs"][0]["bones"].append({
        "bone_id": "Other:Root", "parent_bone_id": ""
    })
    with pytest.raises(root_world_lock.RootWorldLockError, match="Ambiguous"):
        root_world_lock.source_root_world_keys(csir, capture, entity)


def test_missing_source_frame_blocks_instead_of_inventing_pose():
    csir, entity, capture = fixture()
    capture["samples"].pop(1)
    with pytest.raises(root_world_lock.RootWorldLockError, match="Missing authenticated"):
        root_world_lock.source_root_world_keys(csir, capture, entity)


def test_root_calibration_math_compensates_initial_offset_and_transition_snap():
    actor = (1090.0, 150.0, 0.0)
    pre = root_world_lock.corrected_actor_location_cm(
        (950.0, 150.0, 95.0), (870.0, 153.0, 95.0), actor
    )
    after_snap = root_world_lock.corrected_actor_location_cm(
        (800.0, 150.0, 95.0), (1092.0, 153.0, 95.0), actor
    )
    assert pre == (1170.0, 147.0, 0.0)
    assert after_snap == (798.0, 147.0, 0.0)
    assert tuple(870 + pre[0] - actor[0] for _ in range(1)) == (950.0,)
    assert tuple(1092 + after_snap[0] - actor[0] for _ in range(1)) == (800.0,)


def test_nan_or_malformed_root_correction_is_rejected():
    with pytest.raises(root_world_lock.RootWorldLockError):
        root_world_lock.corrected_actor_location_cm([float("nan"), 0, 0], (0, 0, 0), (0, 0, 0))
    with pytest.raises(root_world_lock.RootWorldLockError):
        root_world_lock.corrected_actor_location_cm([1, 2], (0, 0, 0), (0, 0, 0))


class FakeMesh:
    def get_bone_name(self, _index):
        return "Hips"

    def get_socket_location(self, bone):
        assert bone == "Hips"
        return SimpleNamespace(x=100 + FakeEditor.time, y=0, z=95)


class FakeTrack:
    pass


class FakeActor:
    def get_attach_parent_actor(self):
        return None

    def get_components_by_class(self, kind):
        assert kind == FakeMesh
        return [FakeMesh()]

    def get_actor_location(self):
        return SimpleNamespace(x=1000, y=0, z=0)

    def get_actor_rotation(self):
        return SimpleNamespace(roll=0, pitch=0, yaw=90)


class FakeBinding:
    def get_tracks(self):
        return []


class FakeSequence:
    def get_playback_start(self):
        return 0

    def get_playback_end(self):
        return 3


class FakeEditor:
    time = 15
    current = "old-sequence"

    @classmethod
    def get_current_level_sequence(cls):
        return cls.current

    @classmethod
    def get_current_time(cls):
        return cls.time

    @classmethod
    def open_level_sequence(cls, seq):
        cls.current = seq

    @classmethod
    def set_current_time(cls, frame):
        cls.time = frame

    @classmethod
    def force_update(cls):
        pass


class FakeAPI:
    LevelSequenceEditorBlueprintLibrary = FakeEditor
    MovieScene3DTransformTrack = FakeTrack
    SkeletalMeshComponent = FakeMesh


def test_runtime_samples_actual_root_then_restores_editor_state():
    target = FakeSequence()
    actor = FakeActor()
    bindings = {"A": {"actor": actor, "binding": FakeBinding()}}
    action = {
        "kind": "skeletal_world_root_lock",
        "entity_name": "A", "actor_label": "ActorA",
        "root_source_bone_id": "Actor/mixamorig:Hips[7]",
        "root_bone_alias": "hips",
        "keys": [{"frame": f, "source_root_world_cm": [200 + f, 0, 95]}
                 for f in range(3)],
    }
    old_time, old_seq = FakeEditor.time, FakeEditor.current
    result = cinetwin_root_world_lock.prepare_corrections(
        target, [action], bindings, FakeAPI
    )
    assert FakeEditor.time == old_time
    assert FakeEditor.current == old_seq
    assert len(result) == 1
    assert [key["location_cm"] for key in result[0]["keys"]] == [
        [1100.0, 0.0, 0.0],
        [1100.0, 0.0, 0.0],
        [1100.0, 0.0, 0.0],
    ]
    assert result[0]["baked_source_curves"] is True


def test_runtime_preflight_blocks_existing_transform_or_wrong_bone():
    target = FakeSequence()
    actor = FakeActor()
    action = {
        "entity_name": "A", "actor_label": "ActorA",
        "root_source_bone_id": "Rig/Other[0]",
        "root_bone_alias": "other",
        "keys": [{"frame": f, "source_root_world_cm": [200, 0, 0]}
                 for f in range(3)],
    }
    binding = FakeBinding()
    with pytest.raises(cinetwin_root_world_lock.UnrealRootWorldLockError, match="same skeletal root"):
        cinetwin_root_world_lock.preflight(target, [action], {
            "A": {"actor": actor, "binding": binding}
        }, FakeAPI)
