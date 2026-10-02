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


def test_camera_setup_uses_stable_output_gate_and_preflights_without_mutation() -> None:
    builder = _read("integrations/unreal/build_level_sequence.py")
    compat = _read("integrations/unreal/unreal_compat.py")
    plan = _read("integrations/unreal/csir_plan.py")
    assert '"kind": "camera_setup"' in plan
    assert '"target_output_aspect"' in plan
    assert '"observed_source_aspect"' in plan
    assert '"output_resolution"' in plan
    assert "unreal_compat.validate_camera_setup" in builder
    assert "unreal_compat.apply_camera_setup" in builder
    assert "cine_filmback_and_focal_length" in compat
    assert '"sensor_width"' in compat
    assert '"current_focal_length"' in compat


def test_skeletal_root_motion_is_calibrated_in_actor_world_space() -> None:
    builder = _read("integrations/unreal/build_level_sequence.py")
    compat = _read("integrations/unreal/unreal_compat.py")
    plan = _read("integrations/unreal/csir_plan.py")
    assert '"expected_root_delta_cm"' in plan
    assert "root_motion_yaw_alignment_degrees" in plan
    assert "extract_animation_root_delta_cm" in builder
    assert "extract_root_track_transform" in compat
    assert "apply_actor_world_yaw_alignment" in builder
    assert "space=actor_world" in builder
    assert "apply_skeletal_root_yaw(section, yaw)" not in builder


def test_skeletal_completion_holds_last_frame_instead_of_restoring_pose() -> None:
    builder = _read("integrations/unreal/build_level_sequence.py")
    compat = _read("integrations/unreal/unreal_compat.py")
    plan = _read("integrations/unreal/csir_plan.py")
    assert '"completion_mode": "keep_state"' in plan
    assert '"hold_strategy": "post_roll_last_frame"' in plan
    assert "set_section_post_roll_frames" in builder
    assert "set_post_roll_frames" in compat
    assert "set_section_completion_mode" in builder
    assert "MovieSceneCompletionMode" in compat
    assert "KEEP_STATE" in compat


def test_unreal_rotators_are_constructed_by_semantic_field_name() -> None:
    builder = _read("integrations/unreal/build_level_sequence.py")
    compat = _read("integrations/unreal/unreal_compat.py")
    assert "unreal_compat.make_rotator_semantic" in builder
    assert "make_rotator_semantic(roll=0.0, pitch=0.0, yaw=float(yaw_degrees))" in compat
    assert "rotator_type(roll=float(roll), pitch=float(pitch), yaw=float(yaw))" in compat
    assert "unreal.Rotator(float(pitch), float(yaw), float(roll))" not in builder
    assert "unreal.Rotator(0.0, float(yaw_degrees), 0.0)" not in compat
