def test_unreal_58_skeletal_play_rate_uses_timewarp_variant() -> None:
    with open("integrations/unreal/build_level_sequence.py", encoding="utf-8") as handle:
        source = handle.read()
    assert "unreal.MovieSceneTimeWarpVariant()" in source
    assert "play_rate.set_fixed_play_rate" in source
    assert 'params.set_editor_property("play_rate", play_rate)' in source
    assert 'params.set_editor_property("play_rate", float(' not in source
