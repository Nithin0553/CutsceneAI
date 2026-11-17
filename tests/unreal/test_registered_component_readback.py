from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def read_registered(monkeypatch):
    for name in ("unreal", "unreal_compat"):
        monkeypatch.setitem(sys.modules, name, ModuleType(name))
    file = Path(__file__).resolve().parents[2] / "integrations/unreal/readback_level_sequence.py"
    monkeypatch.syspath_prepend(str(file.parent))
    spec = importlib.util.spec_from_file_location("_registered_component_test", file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.read_registered_scalar_components


class LightComponent:
    def __init__(self, label):
        self.label = label

    def get_owner(self):
        return SimpleNamespace(get_actor_label=lambda: self.label)


class BoolTrack:
    def __init__(self, frame, value):
        self.key = SimpleNamespace(get_time=lambda _: frame, get_value=lambda: value)

    def get_sections(self):
        return [SimpleNamespace(get_keys=lambda: [self.key])]


@pytest.mark.parametrize(("label", "frame", "value", "status"), [
    ("StageLight", 0, True, "PASS"),
    ("WrongActor", 0, True, "FAIL"),
    ("StageLight", 1, True, "FAIL"),
    ("StageLight", 0, False, "FAIL"),
    ("StageLight", 0, 1, "FAIL"),
])
def test_saved_binding_and_exact_boolean_key_are_required(
    read_registered, label, frame, value, status,
):
    api = SimpleNamespace(
        MovieSceneSequenceExtensions=SimpleNamespace(
            get_bindings=lambda sequence: sequence,
            locate_bound_objects=lambda *_: [LightComponent(label)],
        ),
        MovieScenePropertyTrackExtensions=SimpleNamespace(
            get_property_path=lambda _: "cast_shadows",
        ),
        MovieSceneSectionExtensions=SimpleNamespace(get_all_channels=lambda section: [section]),
        MovieSceneTimeUnit=SimpleNamespace(DISPLAY_RATE="display"),
        MovieSceneBoolTrack=BoolTrack, LightComponent=LightComponent,
        UnrealEditorSubsystem=object(),
        get_editor_subsystem=lambda _: SimpleNamespace(get_editor_world=object),
    )
    sequence = [SimpleNamespace(get_tracks=lambda: [BoolTrack(frame, value)])]
    row, = read_registered(sequence, [{
        "kind": "property_bool", "target_class": "LightComponent",
        "source_component_id": "source-light", "adapter_name": "unity_light_shadow",
        "actor_label": "StageLight", "target_scope": "component",
        "target_property_path": "cast_shadows", "keys": [{"frame": 0, "value": True}],
    }], api=api)
    assert row["status"] == status
    assert not row["behavior_verified"]
