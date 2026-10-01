def _read(path: str) -> str:
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def test_unreal_58_skeletal_play_rate_uses_compatibility_shim() -> None:
    builder = _read("integrations/unreal/build_level_sequence.py")
    compat = _read("integrations/unreal/unreal_compat.py")
    assert "unreal_compat.make_fixed_play_rate" in builder
    assert "MovieSceneTimeWarpVariant" in compat
    assert "set_fixed_play_rate" in compat
    assert 'params.set_editor_property("play_rate", float(' not in builder


def test_unreal_58_section_channels_use_get_all_channels_compatibility() -> None:
    builder = _read("integrations/unreal/build_level_sequence.py")
    compat = _read("integrations/unreal/unreal_compat.py")
    assert "unreal_compat.get_section_channels(section)" in builder
    assert "get_all_channels" in compat
    assert ".get_channels()" not in builder


def test_failed_unreal_build_rolls_back_partial_sequence() -> None:
    builder = _read("integrations/unreal/build_level_sequence.py")
    assert "Rolled back incomplete generated sequence after build failure" in builder
    assert "unreal.EditorAssetLibrary.delete_asset(asset_path)" in builder
