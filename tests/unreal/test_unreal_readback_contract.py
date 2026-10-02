from pathlib import Path

READBACK = Path("integrations/unreal/readback_level_sequence.py")
RUNNER = Path("integrations/unreal/validate_transfer.py")
BENCHMARK001_WRAPPER = Path("integrations/unreal/validate_benchmark001.py")


def test_readback_inspects_saved_sequence_instead_of_reusing_generation_plan() -> None:
    source = READBACK.read_text(encoding="utf-8")
    assert "sequence.get_bindings" in source or "_bindings(sequence)" in source
    assert "_root_tracks(sequence)" in source
    assert "get_camera_binding_id" in source
    assert "get_marked_frames_from_sequence" in source
    assert "csir_plan.build_plan" not in source


def test_readback_canonicalizes_transforms_and_camera_lens_semantics() -> None:
    source = READBACK.read_text(encoding="utf-8")
    assert "target_transform_to_canonical" in source
    assert "vertical_fov_from_focal_length" in source
    assert "vertical_fov_from_horizontal" in source
    assert "extract_animation_root_delta_cm" in source


def test_generic_validation_runner_uses_benchmark_name_for_outputs() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert 'f"{benchmark_name}.expected.json"' in source
    assert 'f"{benchmark_name}.unreal.readback.json"' in source
    assert 'f"{benchmark_name}.validation.json"' in source
    assert "validation_core.compare" in source


def test_benchmark001_wrapper_has_no_special_validation_semantics() -> None:
    source = BENCHMARK001_WRAPPER.read_text(encoding="utf-8")
    assert 'validate_transfer.run(' in source
    assert '"Benchmark001"' in source
    assert "validation_core.compare" not in source
