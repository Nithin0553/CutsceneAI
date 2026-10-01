from pathlib import Path


BUILDER = Path("integrations/unreal/build_level_sequence.py")


def test_unreal_58_skeletal_play_rate_uses_timewarp_variant() -> None:
    source = BUILDER.read_text(encoding="utf-8")
    assert "unreal.MovieSceneTimeWarpVariant()" in source
    assert "play_rate.set_fixed_play_rate" in source
    assert 'params.set_editor_property("play_rate", play_rate)' in source
    assert 'params.set_editor_property("play_rate", float(' not in source
