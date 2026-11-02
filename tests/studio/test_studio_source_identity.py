"""Regressions for source path, Unity GUID and content identity matching."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import studio_source_identity as identity


def _file(root, name, payload, guid=None):
    file = root / "Assets" / "Models" / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(payload)
    if guid:
        (file.parent / (file.name + ".meta")).write_text(
            "fileFormatVersion: 2\nguid: " + guid + "\n"
        )
    return file


def test_unity_asset_id_guid_with_negative_local_id_finds_renamed_fbx(tmp_path):
    guid = "aabbccddeeff00112233445566778899"
    model = _file(tmp_path, "RenamedHero.fbx", b"hero-fbx", guid)
    result = identity.resolve([model], "LogicalCharacter", {".fbx"},
                              project_root=tmp_path,
                              records=[{"asset_id": f"unity-asset:{guid}:-2573467617735102660"}])
    assert result["selected"] == model
    assert result["strategy"] == "UNITY_META_GUID"


def test_explicit_path_conflicting_with_ondisk_guid_blocks(tmp_path):
    expected = "aabbccddeeff00112233445566778899"
    other = "bbbbccddeeff00112233445566778899"
    model = _file(tmp_path, "Hero.fbx", b"hero-fbx", other)
    result = identity.resolve(
        [model], "Hero", {".fbx"}, project_root=tmp_path,
        records=[{"metadata": {"asset_path": "Assets/Models/Hero.fbx", "guid": expected}}],
    )
    assert result["selected"] is None
    assert result["strategy"] == "IDENTITY_CONFLICT"


def test_different_guid_and_path_sources_cannot_silently_disagree(tmp_path):
    guid = "aabbccddeeff00112233445566778899"
    mismatched = "bbbbccddeeff00112233445566778899"
    left = _file(tmp_path, "PathHero.fbx", b"left", mismatched)
    right = _file(tmp_path, "GuidHero.fbx", b"right", guid)
    result = identity.resolve(
        [left, right], "Hero", {".fbx"}, project_root=tmp_path,
        records=[{"metadata": {"asset_path": "Assets/Models/PathHero.fbx", "guid": guid}}],
    )
    assert result["selected"] is None
    assert result["strategy"] == "IDENTITY_CONFLICT"
    assert len(result["candidates"]) == 2


def test_explicit_path_still_works_without_optional_meta_file(tmp_path):
    model = _file(tmp_path, "Hero.fbx", b"hero")
    result = identity.resolve(
        [model], "Elsewhere", {".fbx"}, project_root=tmp_path,
        records=[{"metadata": {"asset_path": "Assets/Models/Hero.fbx"}}],
    )
    assert result["selected"] == model
    assert result["strategy"] == "UNITY_ASSET_PATH"


def test_renderer_guid_from_windows_crlf_meta_is_verified(tmp_path):
    guid = "aabbccddeeff00112233445566778899"
    model = _file(tmp_path, "Guard.fbx", b"model")
    model.with_name(model.name + ".meta").write_bytes(
        b"fileFormatVersion: 2\r\nguid: " + guid.encode() + b"\r\n"
    )
    result = identity.resolve(
        [model], "DifferentRigName", {".fbx"}, project_root=tmp_path,
        records=[{"asset_path": "Assets/Models/Guard.fbx", "guid": guid}],
    )
    assert result["selected"] == model


def test_exported_guid_cannot_use_path_without_matching_meta(tmp_path):
    model = _file(tmp_path, "Guard.fbx", b"model")
    result = identity.resolve(
        [model], "Guard", {".fbx"}, project_root=tmp_path,
        records=[{"asset_path": "Assets/Models/Guard.fbx",
                  "guid": "aabbccddeeff00112233445566778899"}],
    )
    assert result["selected"] is None
    assert result["strategy"] == "UNITY_META_GUID_NOT_VERIFIABLE"


def test_identical_copies_resolve_but_different_bytes_block(tmp_path):
    one = _file(tmp_path, "A/Hero.fbx", b"same")
    two = _file(tmp_path, "B/Hero.fbx", b"same")
    result = identity.resolve([two, one], "Hero", {".fbx"}, project_root=tmp_path)
    assert result["selected"] == one
    assert result["strategy"] == "EXACT_FILENAME_CONTENT_IDENTICAL"
    two.write_bytes(b"different")
    blocked = identity.resolve([one, two], "Hero", {".fbx"}, project_root=tmp_path)
    assert blocked["selected"] is None
    assert blocked["strategy"] == "AMBIGUOUS_DISTINCT_CONTENT"
