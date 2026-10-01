using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.Timeline;

namespace CutsceneAI.UnityExtractor
{
    internal static class UnityTimelineOffsetAugmenter
    {
        internal const string FinalExtractorVersion = "0.1.5";

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

            AugmentStaticSceneContext(director, document);

            if (document.source_snapshot != null)
            {
                document.source_snapshot.extracted_entity_count = document.entities.Count;
                document.source_snapshot.extracted_asset_count = document.assets.Count;
            }

            if (document.source != null)
                document.source.adapter_version = FinalExtractorVersion;
            if (document.provenance != null)
            {
                document.provenance.extractor_version = FinalExtractorVersion;
                document.provenance.notes.Add(
                    "AnimationTrack track/infinite offsets are preserved as synthetic canonical curves so infinite-track keys can be reconstructed as authored rather than treated as absolute values.");
                document.provenance.notes.Add(
                    "Unity 6000.3 uses AnimationTrack.trackOffset as the authoritative offset-mode API; deprecated applyOffsets is intentionally not read.");
                document.provenance.notes.Add(
                    "AnimationPlayableAsset clip position/rotation offsets are preserved as canonical metadata curves for deterministic root-motion placement in the target engine.");
                document.provenance.notes.Add(
                    "Static rendered scene objects in the PlayableDirector scene are included as entity context so environment placement can be mapped and validated.");
            }

            File.WriteAllText(outputPath, JsonUtility.ToJson(document, true));
        }

        private static void AugmentTrackRecursive(TrackAsset track, CsirDocument document)
        {
            if (track is AnimationTrack animationTrack)
            {
                AugmentAnimationClipOffsets(animationTrack, document);
                if (animationTrack.infiniteClip != null)
                    AugmentInfiniteAnimationTrack(animationTrack, document);
            }

            foreach (var child in track.GetChildTracks())
                AugmentTrackRecursive(child, document);
        }

        private static void AugmentAnimationClipOffsets(AnimationTrack track, CsirDocument document)
        {
            var trackId = ExtractorUtilities.StableAssetId(track);
            var record = FindTrack(document, trackId);
            if (record == null)
                return;

            var clipIndex = 0;
            foreach (var clip in track.GetClips())
            {
                if (clip.asset is AnimationPlayableAsset animationPlayable)
                {
                    var sectionId = $"{trackId}:clip:{clipIndex}:{ToMicroseconds(clip.start)}";
                    var section = FindSection(record, sectionId);
                    if (section?.payload?.animation != null)
                    {
                        AddScalar(section, "CutSceneAI.AnimationTrack.trackOffset",
                            "timeline.animation_track.track_offset_mode", (double)(int)track.trackOffset,
                            "unity_track_metadata");
                        AddCanonicalPosition(section, "CutSceneAI.AnimationTrack.position",
                            "transform.track_offset.position", track.position);
                        AddCanonicalQuaternion(section, "CutSceneAI.AnimationTrack.rotation",
                            "transform.track_offset.rotation", track.rotation);
                        AddCanonicalPosition(section, "CutSceneAI.AnimationPlayableAsset.position",
                            "transform.clip_offset.position", animationPlayable.position);
                        AddCanonicalQuaternion(section, "CutSceneAI.AnimationPlayableAsset.rotation",
                            "transform.clip_offset.rotation", animationPlayable.rotation);
                    }
                }
                clipIndex++;
            }
        }

        private static void AugmentInfiniteAnimationTrack(AnimationTrack track, CsirDocument document)
        {
            var trackId = ExtractorUtilities.StableAssetId(track);
            var record = FindTrack(document, trackId);
            if (record == null)
                return;

            var section = FindSection(record, trackId + ":infinite");
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

        private static TrackRecord FindTrack(CsirDocument document, string trackId)
        {
            foreach (var candidate in document.tracks)
            {
                if (candidate.track_id == trackId)
                    return candidate;
            }
            return null;
        }

        private static SectionRecord FindSection(TrackRecord record, string sectionId)
        {
            foreach (var candidate in record.sections)
            {
                if (candidate.section_id == sectionId)
                    return candidate;
            }
            return null;
        }

        private static void AugmentStaticSceneContext(PlayableDirector director, CsirDocument document)
        {
            var existing = new HashSet<string>();
            foreach (var entity in document.entities)
                existing.Add(entity.entity_id);

            foreach (var root in director.gameObject.scene.GetRootGameObjects())
                AddRenderedObjectsRecursive(root.transform, document, existing);
        }

        private static void AddRenderedObjectsRecursive(
            Transform transform,
            CsirDocument document,
            HashSet<string> existing)
        {
            var gameObject = transform.gameObject;
            var hasRenderer = gameObject.GetComponent<MeshRenderer>() != null ||
                              gameObject.GetComponent<SkinnedMeshRenderer>() != null;
            if (hasRenderer)
                AddSceneEntity(gameObject, document, existing);

            for (var i = 0; i < transform.childCount; i++)
                AddRenderedObjectsRecursive(transform.GetChild(i), document, existing);
        }

        private static void AddSceneEntity(
            GameObject gameObject,
            CsirDocument document,
            HashSet<string> existing)
        {
            var id = ExtractorUtilities.StableSceneObjectId(gameObject);
            if (!existing.Add(id))
                return;

            var camera = gameObject.GetComponent<Camera>();
            var audioSource = gameObject.GetComponent<AudioSource>();
            var animator = gameObject.GetComponent<Animator>();
            var hasCharacterRig = gameObject.GetComponent<SkinnedMeshRenderer>() != null ||
                                  (animator != null && animator.avatar != null);

            document.entities.Add(new EntityRecord
            {
                entity_id = id,
                ced_type = camera != null
                    ? "entity.camera"
                    : audioSource != null
                        ? "entity.audio_source"
                        : hasCharacterRig
                            ? "entity.character"
                            : "entity.prop",
                name = gameObject.name,
                native_ref = GlobalObjectId.GetGlobalObjectIdSlow(gameObject).ToString(),
                parent_entity_id = string.Empty,
                metadata = new EntityMetadata
                {
                    scene_path = gameObject.scene.path ?? string.Empty,
                    hierarchy_path = ExtractorUtilities.HierarchyPath(gameObject.transform),
                    active_self = gameObject.activeSelf,
                    local_transform = ExtractorUtilities.CaptureLocalTransform(gameObject.transform),
                    world_transform = ExtractorUtilities.CaptureWorldTransform(gameObject.transform),
                    camera = CreateCameraMetadata(camera),
                    animator = CreateAnimatorMetadata(animator),
                },
            });
        }

        private static CameraMetadata CreateCameraMetadata(Camera camera)
        {
            if (camera == null)
                return new CameraMetadata { sensor_size_mm = new Vector2Record(), lens_shift = new Vector2Record() };

            return new CameraMetadata
            {
                orthographic = camera.orthographic,
                orthographic_size = camera.orthographicSize,
                field_of_view_degrees = camera.fieldOfView,
                use_physical_properties = camera.usePhysicalProperties,
                focal_length_mm = camera.focalLength,
                sensor_size_mm = new Vector2Record { x = camera.sensorSize.x, y = camera.sensorSize.y },
                lens_shift = new Vector2Record { x = camera.lensShift.x, y = camera.lensShift.y },
                near_clip = camera.nearClipPlane,
                far_clip = camera.farClipPlane,
                aspect = camera.aspect,
            };
        }

        private static AnimatorMetadata CreateAnimatorMetadata(Animator animator)
        {
            if (animator == null)
                return new AnimatorMetadata { avatar_ref = string.Empty, controller_ref = string.Empty };

            return new AnimatorMetadata
            {
                apply_root_motion = animator.applyRootMotion,
                has_avatar = animator.avatar != null,
                avatar_is_human = animator.avatar != null && animator.avatar.isHuman,
                avatar_ref = animator.avatar != null ? ExtractorUtilities.AssetReference(animator.avatar) : string.Empty,
                controller_ref = animator.runtimeAnimatorController != null
                    ? ExtractorUtilities.AssetReference(animator.runtimeAnimatorController)
                    : string.Empty,
            };
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

        private static long ToMicroseconds(double seconds) => (long)Math.Round(seconds * 1_000_000.0);
    }
}
