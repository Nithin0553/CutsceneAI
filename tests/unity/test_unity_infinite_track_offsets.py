from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUGMENTER = (
    ROOT
    / "integrations"
    / "unity"
    / "com.cutsceneai.extractor"
    / "Editor"
    / "UnityTimelineOffsetAugmenter.cs"
)
MENU = (
    ROOT
    / "integrations"
    / "unity"
    / "com.cutsceneai.extractor"
    / "Editor"
    / "CutsceneAIExportMenu.cs"
)


def test_export_menu_runs_offset_augmentation() -> None:
    source = MENU.read_text(encoding="utf-8")
    assert "UnityTimelineOffsetAugmenter.Augment(outputPath, director)" in source


def test_infinite_track_offsets_are_preserved() -> None:
    source = AUGMENTER.read_text(encoding="utf-8")
    assert "infiniteClipOffsetPosition" in source
    assert "infiniteClipOffsetRotation" in source
    assert "transform.infinite_offset.position" in source
    assert "transform.infinite_offset.rotation" in source
    assert "transform.track_offset.position" in source
    assert "transform.track_offset.rotation" in source
    assert "track.trackOffset" in source
    assert "track.applyOffsets" not in source
    assert 'FinalExtractorVersion = "0.1.4"' in source
