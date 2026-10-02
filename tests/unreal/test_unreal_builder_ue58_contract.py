def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_skeletal_play_rate_uses_runtime_compatibility_shim() -> None:
    builder = _read("integrations/unreal/build_level_sequence.py")
    compat = _read("integrations/unreal/unreal_compat.py")
    assert "unreal_compat.make_fixed_play_rate" in builder
    assert "MovieSceneTimeWarpVariant" in compat
    assert "set_fixed_play_rate" in compat
    assert 'params.set_editor_property("play_rate", float(' not in builder


def test_section_channels_use_runtime_compatibility_shim() -> None:
    builder = _read("integrations/unreal/build_level_sequence.py")
    compat = _read("integrations/unreal/unreal_compat.py")
    assert "unreal_compat.get_section_channels(section)" in builder
    assert "get_all_channels" in compat
    assert ".get_channels()" not in builder


def test_camera_component_resolution_is_feature_driven() -> None:
    builder = _read("integrations/unreal/build_level_sequence.py")
    compat = _read("integrations/unreal/unreal_compat.py")
    assert "unreal_compat.resolve_camera_component(actor)" in builder
    assert "get_cine_camera_component" in compat
    assert "get_camera_component" in compat
    assert '"camera_component"' in compat
    assert "get_components_by_class" in compat
    assert "actor.get_camera_component()" not in builder


def test_unity_vertical_fov_is_adapted_to_target_camera_model() -> None:
    builder = _read("integrations/unreal/build_level_sequence.py")
    compat = _read("integrations/unreal/unreal_compat.py")
    plan = _read("integrations/unreal/csir_plan.py")
    assert '"source_fov_axis": "vertical"' in plan
    assert "prepare_camera_fov_track" in builder
    assert "CurrentFocalLength" in compat
    assert "sensor_height" in compat
    assert "aspect_ratio" in compat


def test_runtime_preflight_occurs_before_target_mutation() -> None:
    builder = _read("integrations/unreal/build_level_sequence.py")
    preflight_call = builder.index("_preflight(plan)")
    prep_call = builder.index("_apply_scene_prep(csir, mapping)", preflight_call)
    assert preflight_call < prep_call
    assert "runtime_profile()" in builder
    assert "Runtime preflight PASS" in builder


def test_failed_unreal_build_rolls_back_partial_sequence() -> None:
    builder = _read("integrations/unreal/build_level_sequence.py")
    assert "Rolled back incomplete generated sequence after build failure" in builder
    assert "unreal.EditorAssetLibrary.delete_asset(asset_path)" in builder
