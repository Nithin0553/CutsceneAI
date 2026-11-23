"""Read-only Unreal character-facing ownership preflight (software mocks).

These synthetic editor doubles intentionally do not claim that a native
character can be safely rotated. The answer from the adapter is always
'no mutation authorized', even for a clean isolated static candidate.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "integrations/unreal"))
import studio_character_facing_ownership as ownership


def ns(**kwargs):
    return SimpleNamespace(**kwargs)


class FakeTrack:
    def __init__(self, name):
        self.name = name

    def get_class(self):
        return ns(get_name=lambda: self.name)


class FakeBinding:
    def __init__(self, tracks=()):
        self.tracks = tracks

    def get_tracks(self):
        return [FakeTrack(t) for t in self.tracks]


class FakeComponent:
    def __init__(self):
        self.mesh = "/Game/Characters/Guard"
        self.relative = ns(
            translation=ns(x=0, y=0, z=0),
            rotation=ns(x=0, y=0, z=0, w=1),
            scale3d=ns(x=1, y=1, z=1),
        )
        self.mode = "AnimationMode.ANIMATION_CUSTOM_MODE"
        self.physics = False

    def get_skeletal_mesh_asset(self):
        return ns(get_path_name=lambda: self.mesh + "." + self.mesh.split("/")[-1])

    def get_relative_transform(self):
        return self.relative

    def get_editor_property(self, key):
        if key == "animation_mode":
            return self.mode
        raise ValueError(key)

    def is_simulating_physics(self):
        return self.physics


class FakeActor:
    def __init__(self, label="GuardTarget"):
        self.label = label
        self.parent = None
        self.roll = self.pitch = 0.
        self.yaw = 45.
        self.scale = ns(x=1, y=1, z=1)
        self.cls = "SkeletalMeshActor"
        self.components = [FakeComponent()]

    def get_actor_label(self):
        return self.label

    def get_class(self):
        return ns(get_name=lambda: self.cls)

    def get_attach_parent_actor(self):
        return self.parent

    def get_actor_scale3d(self):
        return self.scale

    def get_actor_rotation(self):
        return ns(roll=self.roll, pitch=self.pitch, yaw=self.yaw)

    def get_components_by_class(self, _):
        return self.components


def editor(*, bindings=None, root=None):
    if bindings is None:
        bindings = [FakeBinding()]
    if root is None:
        root = [FakeTrack("MovieSceneCameraCutTrack")]
    return ns(
        SkeletalMeshComponent=object(),
        MovieSceneSequenceExtensions=ns(
            get_bindings=lambda _: bindings,
            get_tracks=lambda _: root,
        ),
    )


def check(actor=None, *, api=None, others=None, expected_mesh="/Game/Characters/Guard"):
    actor = actor if actor is not None else FakeActor()
    return ownership.inspect(
        api if api is not None else editor(), object(), actor,
        expected_actor_label="GuardTarget",
        expected_mesh_asset_path=expected_mesh,
        all_level_actors=others if others is not None else [actor],
    )


def assert_blocked(result, reason):
    assert result["status"] == "BLOCKED_UNVERIFIED_OWNER"
    assert reason in result["blocking_reasons"]
    assert result["native_edit_authorized"] is False
    assert result["actor_yaw_repair_authorized"] is False
    assert result["source_to_target_facing_verified"] is False


def test_statically_isolated_native_character_is_still_not_authorized():
    result = check()
    assert result["status"] == "STATIC_NATIVE_OWNER_CANDIDATE_REQUIRES_SOURCE_PROOF"
    assert result["owner_hypothesis"] == "STATIC_ACTOR_BASE_POSSIBLE_UNPROVEN"
    assert result["read_only"] is True
    assert result["blocking_reasons"] == []
    assert result["native_edit_authorized"] is False
    assert result["actor_yaw_repair_authorized"] is False
    assert result["full_cutscene_fidelity_verified"] is False
    assert result["native_track_types"] == ["MovieSceneCameraCutTrack"]


@pytest.mark.parametrize("kind", [
    "MovieScene3DTransformTrack",
    "MovieSceneSkeletalAnimationTrack",
    "MovieSceneControlRigParameterTrack",
    "MovieSceneCinematicShotTrack",
    "MovieSceneSubTrack",
    "MovieSceneFloatTrack",
    "MovieScene3DAttachTrack",
    "MovieSceneUnknownPluginTrack",
])
def test_owned_or_unknown_sequencer_tracks_refuse_any_facing_edit(kind):
    for api in (
        editor(bindings=[FakeBinding([kind])]),
        editor(root=[FakeTrack(kind)]),
    ):
        assert_blocked(check(api=api), "NATIVE_TRACK_OR_ANIMATION_OWNER_NOT_ISOLATED")


def test_unknown_track_api_or_raised_python_introspection_refuses():
    api = editor()
    api.MovieSceneSequenceExtensions.get_bindings = None
    assert_blocked(check(api=api),
                   "Complete native Sequencer master and bound track APIs are unavailable.")
    api = editor()
    def broken(_):
        raise RuntimeError("new Unreal interface")
    api.MovieSceneSequenceExtensions.get_tracks = broken
    assert_blocked(check(api=api),
                   "Native Sequencer binding/track inspection failed.")


@pytest.mark.parametrize("change,reason", [
    (lambda a: setattr(a, "cls", "Character"), "UNSUPPORTED_CHARACTER_ACTOR_CLASS"),
    (lambda a: setattr(a, "parent", object()), "ACTOR_PARENT_ATTACHMENT_OWNS_ORIENTATION"),
    (lambda a: setattr(a, "pitch", 7), "ACTOR_NON_UPRIGHT_ROLL_OR_PITCH"),
    (lambda a: setattr(a, "roll", float("nan")), "Native actor rotator is invalid."),
    (lambda a: setattr(a, "scale", ns(x=-1, y=1, z=1)), "NON_UNIT_ACTOR_SCALE"),
    (lambda a: setattr(a, "components", []), "MISSING_OR_MULTIPLE_SKELETAL_MESH_COMPONENTS"),
    (lambda a: setattr(a.components[0], "mesh", "/Game/Unrelated"),
     "UNAPPROVED_NATIVE_SKELETAL_MESH_IDENTITY"),
    (lambda a: setattr(a.components[0], "physics", True),
     "SKELETAL_COMPONENT_PHYSICS_OWNS_POSE"),
])
def test_native_identity_hierarchy_scale_and_physics_block(change, reason):
    actor = FakeActor()
    change(actor)
    assert_blocked(check(actor), reason)


def test_relative_skeletal_mesh_rotation_translation_and_scale_block():
    actor = FakeActor()
    relative = actor.components[0].relative
    relative.rotation = ns(x=0, y=0, z=math.sqrt(0.5), w=math.sqrt(0.5))
    assert_blocked(check(actor), "COMPONENT_RELATIVE_ROTATION_OWNS_MESH_FACING")
    relative.rotation = ns(x=0, y=0, z=0, w=1)
    relative.translation.x = 20
    assert_blocked(check(actor), "COMPONENT_RELATIVE_TRANSLATION_OR_SCALE")
    relative.translation.x = 0
    relative.scale3d.y = -1
    assert_blocked(check(actor), "COMPONENT_RELATIVE_TRANSLATION_OR_SCALE")


def test_attachment_descendant_and_duplicate_label_block():
    actor = FakeActor()
    child = FakeActor("Other")
    child.parent = actor
    assert_blocked(check(actor, others=[actor, child]), "ATTACHED_CHILDREN_CAN_BE_ROTATED")
    duplicate = FakeActor("GuardTarget")
    assert_blocked(check(actor, others=[actor, duplicate]),
                   "Target actor is not the one unique mapped character.")


def test_animation_or_physics_readback_unavailable_refuses():
    actor = FakeActor()
    actor.components[0].get_editor_property = lambda _: (_ for _ in ()).throw(
        AttributeError("missing")
    )
    assert_blocked(check(actor), "SKELETAL_ANIMATION_MODE_UNOBSERVABLE")
    actor = FakeActor()
    actor.components[0].is_simulating_physics = None
    assert_blocked(check(actor), "SKELETAL_PHYSICS_MODE_UNOBSERVABLE")


def test_untrusted_mesh_identity_and_unbounded_inventory_refuse():
    assert_blocked(check(expected_mesh="../../Editor"),
                   "Character identity, expected mesh or actor inventory is untrusted.")
    actor = FakeActor()
    assert_blocked(check(actor, others=[actor] * (ownership.MAX_ACTORS+1)),
                   "Character identity, expected mesh or actor inventory is untrusted.")
