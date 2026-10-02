from pathlib import Path

READBACK = Path("integrations/unreal/readback_level_sequence.py")
RUNNER = Path("integrations/unreal/validate_benchmark001.py")


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


def test_validation_runner_writes_expectation_readback_and_report() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    assert "Benchmark001.expected.json" in source
    assert "Benchmark001.unreal.readback.json" in source
    assert "Benchmark001.validation.json" in source
    assert "validation_core.compare" in source
