from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXTRACTOR = (
    ROOT
    / "integrations"
    / "unity"
    / "com.cutsceneai.extractor"
    / "Editor"
    / "UnityTimelineExtractor.cs"
)


def test_infinite_animation_tracks_are_exported() -> None:
    source = EXTRACTOR.read_text(encoding="utf-8")
    assert "animationTrack.infiniteClip" in source
    assert "ExtractInfiniteAnimationTrack" in source
    assert 'ced_type = isCamera ? "camera.transform" : "animation.section"' in source


def test_scene_entities_are_not_classified_by_animator_presence_alone() -> None:
    source = EXTRACTOR.read_text(encoding="utf-8")
    assert "SkinnedMeshRenderer" in source
    assert "animator.avatar != null" in source
    assert '"entity.audio_source"' in source
    assert '"entity.prop"' in source


def test_exported_adapter_version_tracks_extractor_version() -> None:
    source = EXTRACTOR.read_text(encoding="utf-8")
    assert "adapter_version = ExtractorVersion" in source
    assert 'ExtractorVersion = "0.1.2"' in source
