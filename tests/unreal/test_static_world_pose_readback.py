"""Verify that keyed static poses never become invented full world transforms."""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

import pytest


@pytest.fixture
def static_pose_helper(monkeypatch: pytest.MonkeyPatch):
    # The file imports Unreal only for runtime-only helpers, while this static
    # key classifier is independently testable without launching the editor.
    monkeypatch.setitem(sys.modules, "unreal", types.ModuleType("unreal"))
    monkeypatch.setitem(
        sys.modules, "unreal_compat", types.ModuleType("unreal_compat")
    )
    file = (
        Path(__file__).resolve().parents[2]
        / "integrations" / "unreal" / "readback_level_sequence.py"
    )
    spec = importlib.util.spec_from_file_location(
        "_test_cutsceneai_static_pose_reader", file
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._static_world_pose_from_keyed_track


class FakeActor:
    def __init__(self, parent=None):
        self.parent = parent

    def get_attach_parent_actor(self):
        return self.parent


def _track(*, name="CutSceneAI Static Scene Pose", frame=0):
    return {
        "kind": "transform",
        "track_name": name,
        "keys": [
            {
                "frame": frame,
                "position_m": [1.0, 2.0, -3.0],
                "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
            },
        ],
    }


def test_saved_static_world_pose_recovers_only_keyed_6dof(static_pose_helper):
    actual = static_pose_helper([_track()], FakeActor())
    assert actual == {
        "position_m": [1.0, 2.0, -3.0],
        "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
    }
    assert "scale_xyz" not in actual


@pytest.mark.parametrize("tracks", [
    [_track(name="Other Transform")],
    [_track(frame=1)],
    [_track(), _track()],
    [_track(), {"kind": "skeletal_animation"}],
    [{**_track(), "keys": []}],
])
def test_unsupported_or_ambiguous_keys_do_not_prove_static_world_pose(
    static_pose_helper, tracks
):
    assert static_pose_helper(tracks, FakeActor()) is None


def test_attached_actor_cannot_mislabel_local_key_as_world(static_pose_helper):
    assert static_pose_helper([_track()], FakeActor(parent=object())) is None
    assert static_pose_helper([_track()], object()) is None
