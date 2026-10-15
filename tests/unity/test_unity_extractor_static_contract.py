import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNITY_PACKAGE = ROOT / "integrations" / "unity" / "com.cutsceneai.extractor"
EDITOR = UNITY_PACKAGE / "Editor"


def test_unity_package_manifest_targets_benchmark_versions() -> None:
    manifest = json.loads((UNITY_PACKAGE / "package.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "com.cutsceneai.extractor"
    assert manifest["unity"] == "6000.0"
    assert manifest["dependencies"]["com.unity.timeline"] == "1.8.10"


def test_editor_assembly_is_editor_only_and_references_timeline() -> None:
    asmdef = json.loads(
        (EDITOR / "CutsceneAI.UnityExtractor.Editor.asmdef").read_text(encoding="utf-8")
    )
    assert asmdef["includePlatforms"] == ["Editor"]
    assert "Unity.Timeline" in asmdef["references"]


def test_structural_extractor_uses_expected_read_only_timeline_apis() -> None:
    source = (EDITOR / "UnityTimelineExtractor.cs").read_text(encoding="utf-8")
    for required in (
        "GetRootTracks()",
        "GetChildTracks()",
        "GetClips()",
        "GetMarkers()",
        "GetGenericBinding(track)",
        "AnimationUtility.GetCurveBindings",
        "AnimationUtility.GetObjectReferenceCurveBindings",
    ):
        assert required in source


def test_structural_extractor_does_not_mutate_source_project() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in EDITOR.glob("*.cs"))
    forbidden = (
        "SetGenericBinding(",
        "SetReferenceValue(",
        "CreateTrack(",
        "DeleteTrack(",
        "DeleteClip(",
        "CreateMarkerTrack(",
        "SaveAssets(",
        "SaveScene(",
        ".Evaluate(",
        ".RebuildGraph(",
    )
    for token in forbidden:
        assert token not in source, f"Read-only extractor contains forbidden operation: {token}"


def test_exporter_declares_canonical_and_native_animation_keys() -> None:
    models = (EDITOR / "CsirModels.cs").read_text(encoding="utf-8")
    extractor = (EDITOR / "UnityTimelineExtractor.cs").read_text(encoding="utf-8")
    assert "native_keys" in models
    assert "canonical_semantic" in models
    assert "ConvertCurveValueToCanonical" in extractor
    assert "record.native_keys.Add" in extractor


def test_menu_entry_exists() -> None:
    source = (EDITOR / "CutsceneAIExportMenu.cs").read_text(encoding="utf-8")
    assert '"Tools/CutsceneAI/Export Selected Timeline"' in source


def test_parent_hierarchy_is_exported_as_reusable_csir_relationships() -> None:
    source = (EDITOR / "UnityTimelineOffsetAugmenter.cs").read_text(encoding="utf-8")
    assert "AugmentParentRelationships" in source
    assert 'ced_type = "transform.parent"' in source
    assert "parent_entity_id = parentId" in source
    assert "Unity Transform.parent hierarchy" in source
    assert 'FinalExtractorVersion = "0.1.7"' in source


def test_camera_fov_curve_is_emitted_as_canonical_ced_evidence() -> None:
    models = (EDITOR / "CsirModels.cs").read_text(encoding="utf-8")
    utilities = (EDITOR / "ExtractorUtilities.cs").read_text(encoding="utf-8")
    extractor = (EDITOR / "UnityTimelineExtractor.cs").read_text(encoding="utf-8")
    augmenter = (EDITOR / "UnityTimelineOffsetAugmenter.cs").read_text(encoding="utf-8")

    assert "public string ced_type;" in models
    assert "CurveCedType" in utilities
    assert 'return "camera.fov";' in utilities
    assert '"camera.vertical_fov_degrees"' in utilities
    assert "binding.type" in extractor
    assert "ExtractorUtilities.CurveCedType" in extractor
    assert 'FinalExtractorVersion = "0.1.7"' in augmenter
