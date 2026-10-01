using System;
using System.IO;
using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.Timeline;

namespace CutsceneAI.UnityExtractor
{
    internal static class UnityTimelineOffsetAugmenter
    {
        internal const string FinalExtractorVersion = "0.1.4";

        internal static void Augment(string outputPath, PlayableDirector director)
        {
            if (string.IsNullOrWhiteSpace(outputPath) || !File.Exists(outputPath))
                throw new FileNotFoundException("CSIR export was not found.", outputPath);
            if (director == null || director.playableAsset is not TimelineAsset timeline)
                throw new InvalidOperationException("PlayableDirector must reference a TimelineAsset.");

            var document = JsonUtility.FromJson<CsirDocument>(File.ReadAllText(outputPath));
            if (document == null)
                throw new InvalidOperationException("Unable to deserialize the generated CSIR document.");

            foreach (var rootTrack in timeline.GetRootTracks())
                AugmentTrackRecursive(rootTrack, document);

            if (document.source != null)
                document.source.adapter_version = FinalExtractorVersion;
            if (document.provenance != null)
            {
                document.provenance.extractor_version = FinalExtractorVersion;
                document.provenance.notes.Add(
                    "AnimationTrack track/infinite offsets are preserved as synthetic canonical curves so infinite-track keys can be reconstructed as authored rather than treated as absolute values.");
                document.provenance.notes.Add(
                    "Unity 6000.3 uses AnimationTrack.trackOffset as the authoritative offset-mode API; deprecated applyOffsets is intentionally not read.");
            }

            File.WriteAllText(outputPath, JsonUtility.ToJson(document, true));
        }

        private static void AugmentTrackRecursive(TrackAsset track, CsirDocument document)
        {
            if (track is AnimationTrack animationTrack && animationTrack.infiniteClip != null)
                AugmentInfiniteAnimationTrack(animationTrack, document);

            foreach (var child in track.GetChildTracks())
                AugmentTrackRecursive(child, document);
        }

        private static void AugmentInfiniteAnimationTrack(AnimationTrack track, CsirDocument document)
        {
            var trackId = ExtractorUtilities.StableAssetId(track);
            TrackRecord record = null;
            foreach (var candidate in document.tracks)
            {
                if (candidate.track_id == trackId)
                {
                    record = candidate;
                    break;
                }
            }

            if (record == null)
                return;

            SectionRecord section = null;
            foreach (var candidate in record.sections)
            {
                if (candidate.section_id == trackId + ":infinite")
                {
                    section = candidate;
                    break;
                }
            }

            if (section?.payload?.animation == null)
                return;

            AddScalar(section, "CutSceneAI.AnimationTrack.trackOffset",
                "timeline.animation_track.track_offset_mode", (double)(int)track.trackOffset,
                "unity_track_metadata");

            AddCanonicalPosition(section, "CutSceneAI.AnimationTrack.position",
                "transform.track_offset.position", track.position);
            AddCanonicalQuaternion(section, "CutSceneAI.AnimationTrack.rotation",
                "transform.track_offset.rotation", track.rotation);
            AddCanonicalPosition(section, "CutSceneAI.AnimationTrack.infiniteClipOffsetPosition",
                "transform.infinite_offset.position", track.infiniteClipOffsetPosition);
            AddCanonicalQuaternion(section, "CutSceneAI.AnimationTrack.infiniteClipOffsetRotation",
                "transform.infinite_offset.rotation", track.infiniteClipOffsetRotation);
        }

        private static void AddCanonicalPosition(
            SectionRecord section,
            string propertyPrefix,
            string semanticPrefix,
            Vector3 nativeValue)
        {
            var canonical = ExtractorUtilities.CanonicalPosition(nativeValue);
            AddScalar(section, propertyPrefix + ".x", semanticPrefix + ".x", canonical.x,
                "unity_to_cutsceneai_canonical");
            AddScalar(section, propertyPrefix + ".y", semanticPrefix + ".y", canonical.y,
                "unity_to_cutsceneai_canonical");
            AddScalar(section, propertyPrefix + ".z", semanticPrefix + ".z", canonical.z,
                "unity_to_cutsceneai_canonical");
        }

        private static void AddCanonicalQuaternion(
            SectionRecord section,
            string propertyPrefix,
            string semanticPrefix,
            Quaternion nativeValue)
        {
            var canonical = ExtractorUtilities.CanonicalRotation(nativeValue);
            AddScalar(section, propertyPrefix + ".x", semanticPrefix + ".x", canonical.x,
                "unity_to_cutsceneai_canonical");
            AddScalar(section, propertyPrefix + ".y", semanticPrefix + ".y", canonical.y,
                "unity_to_cutsceneai_canonical");
            AddScalar(section, propertyPrefix + ".z", semanticPrefix + ".z", canonical.z,
                "unity_to_cutsceneai_canonical");
            AddScalar(section, propertyPrefix + ".w", semanticPrefix + ".w", canonical.w,
                "unity_to_cutsceneai_canonical");
        }

        private static void AddScalar(
            SectionRecord section,
            string propertyName,
            string semantic,
            double value,
            string conversion)
        {
            var key = new KeyframeRecord
            {
                time_seconds = 0.0,
                value = value,
                in_tangent = 0.0,
                out_tangent = 0.0,
                in_weight = 0.0,
                out_weight = 0.0,
                weighted_mode = 0,
            };

            section.payload.animation.curves.Add(new CurveRecord
            {
                path = string.Empty,
                component_type = "CutSceneAI.UnityTimelineOffsetMetadata",
                property_name = propertyName,
                canonical_semantic = semantic,
                conversion = conversion,
                keys = { key },
                native_keys = { key },
            });
        }
    }
}
