using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.Timeline;

namespace CutsceneAI.UnityExtractor
{
    internal static class UnityTimelineSourceSnapshot
    {
        internal const string SnapshotVersion = "0.1.0";
        private const string MenuPath = "Tools/CutsceneAI/Export Selected Timeline Source Snapshot";

        [MenuItem(MenuPath, priority = 101)]
        private static void ExportSelectedTimelineSourceSnapshot()
        {
            var director = GetSelectedDirector();
            if (director == null)
            {
                EditorUtility.DisplayDialog(
                    "CutsceneAI",
                    "Select a GameObject containing a PlayableDirector with a saved TimelineAsset.",
                    "OK");
                return;
            }

            try
            {
                var outputPath = Export(director);
                Debug.Log($"[CutsceneAI] Unity source snapshot exported to: {outputPath}");
                EditorUtility.RevealInFinder(outputPath);
            }
            catch (Exception exception)
            {
                Debug.LogException(exception);
                EditorUtility.DisplayDialog("CutsceneAI Source Snapshot Export Failed", exception.Message, "OK");
            }
        }

        [MenuItem(MenuPath, validate = true)]
        private static bool ValidateExportSelectedTimelineSourceSnapshot()
        {
            return GetSelectedDirector() != null;
        }

        internal static string Export(PlayableDirector director)
        {
            if (director == null)
                throw new ArgumentNullException(nameof(director));
            if (director.playableAsset is not TimelineAsset timeline)
                throw new InvalidOperationException("Selected PlayableDirector does not reference a TimelineAsset.");

            if (!ExtractorUtilities.TryGetAssetIdentity(timeline, out var timelineGuid, out var timelineLocalId, out var timelinePath))
                throw new InvalidOperationException("TimelineAsset must be saved in the Unity project before extraction.");

            var snapshot = new UnitySourceSnapshotDocument
            {
                cutscene_id = $"unity:{timelineGuid}:{timelineLocalId}",
                timeline_name = timeline.name,
                timeline_asset_guid = timelineGuid,
                timeline_asset_local_file_id = timelineLocalId,
                timeline_asset_path = timelinePath,
                director_global_object_id = GlobalObjectId.GetGlobalObjectIdSlow(director).ToString(),
                director_scene_path = director.gameObject.scene.path ?? string.Empty,
                engine_version = Application.unityVersion,
                exporter_version = SnapshotVersion,
                exported_at_utc = DateTime.UtcNow.ToString("O"),
            };

            foreach (var rootTrack in timeline.GetRootTracks())
                ExtractAnimationTracksRecursive(rootTrack, director, snapshot.animation_tracks);

            var projectRoot = Directory.GetParent(Application.dataPath)?.FullName ?? Application.dataPath;
            var exportDirectory = Path.Combine(projectRoot, "CutsceneAI", "Exports");
            Directory.CreateDirectory(exportDirectory);

            var shortId = timelineGuid.Length >= 8 ? timelineGuid[..8] : timelineGuid;
            var fileName = $"{ExtractorUtilities.SafeFileName(timeline.name)}-{shortId}.unity-source.json";
            var outputPath = Path.Combine(exportDirectory, fileName);
            File.WriteAllText(outputPath, JsonUtility.ToJson(snapshot, true));
            return outputPath;
        }

        private static void ExtractAnimationTracksRecursive(
            TrackAsset track,
            PlayableDirector director,
            List<AnimationTrackSourceRecord> output)
        {
            if (track is AnimationTrack animationTrack)
                output.Add(CreateAnimationTrackRecord(animationTrack, director));

            foreach (var child in track.GetChildTracks())
                ExtractAnimationTracksRecursive(child, director, output);
        }

        private static AnimationTrackSourceRecord CreateAnimationTrackRecord(
            AnimationTrack track,
            PlayableDirector director)
        {
            var binding = director.GetGenericBinding(track);
            var bindingObject = ResolveGameObject(binding);
            var record = new AnimationTrackSourceRecord
            {
                track_id = ExtractorUtilities.StableAssetId(track),
                name = track.name,
                binding_global_object_id = bindingObject != null
                    ? GlobalObjectId.GetGlobalObjectIdSlow(bindingObject).ToString()
                    : string.Empty,
                binding_name = bindingObject != null ? bindingObject.name : string.Empty,
                in_clip_mode = track.inClipMode,
                track_offset_mode = track.trackOffset.ToString(),
                track_position = ExtractorUtilities.CanonicalPosition(track.position),
                track_rotation = ExtractorUtilities.CanonicalRotation(track.rotation),
                track_euler_degrees_native = NativeVector(track.eulerAngles),
                infinite_clip_offset_position = ExtractorUtilities.CanonicalPosition(track.infiniteClipOffsetPosition),
                infinite_clip_offset_rotation = ExtractorUtilities.CanonicalRotation(track.infiniteClipOffsetRotation),
                infinite_clip_offset_euler_degrees_native = NativeVector(track.infiniteClipOffsetEulerAngles),
            };

            var index = 0;
            foreach (var timelineClip in track.GetClips())
            {
                if (timelineClip.asset is AnimationPlayableAsset animationPlayable)
                    record.clips.Add(CreateClipRecord(timelineClip, animationPlayable, index));
                index++;
            }

            if (track.infiniteClip != null)
            {
                record.infinite_clip_asset_ref = ExtractorUtilities.AssetReference(track.infiniteClip);
                record.infinite_clip_asset_id = ExtractorUtilities.StableAssetId(track.infiniteClip);
            }

            return record;
        }

        private static AnimationClipSourceRecord CreateClipRecord(
            TimelineClip timelineClip,
            AnimationPlayableAsset animationPlayable,
            int index)
        {
            var animationClip = animationPlayable.clip;
            return new AnimationClipSourceRecord
            {
                index = index,
                display_name = timelineClip.displayName ?? string.Empty,
                start_seconds = timelineClip.start,
                end_seconds = timelineClip.end,
                clip_in_seconds = timelineClip.clipIn,
                time_scale = timelineClip.timeScale,
                playable_asset_id = ExtractorUtilities.StableAssetId(animationPlayable),
                animation_clip_asset_id = animationClip != null
                    ? ExtractorUtilities.StableAssetId(animationClip)
                    : string.Empty,
                animation_clip_asset_ref = animationClip != null
                    ? ExtractorUtilities.AssetReference(animationClip)
                    : string.Empty,
                clip_offset_position = ExtractorUtilities.CanonicalPosition(animationPlayable.position),
                clip_offset_rotation = ExtractorUtilities.CanonicalRotation(animationPlayable.rotation),
                clip_offset_euler_degrees_native = NativeVector(animationPlayable.eulerAngles),
                remove_start_offset = animationPlayable.removeStartOffset,
                use_track_match_fields = animationPlayable.useTrackMatchFields,
                apply_foot_ik = animationPlayable.applyFootIK,
                loop_mode = animationPlayable.loop.ToString(),
            };
        }

        private static Vector3Record NativeVector(Vector3 value)
        {
            return new Vector3Record { x = value.x, y = value.y, z = value.z };
        }

        private static GameObject ResolveGameObject(UnityEngine.Object binding)
        {
            return binding switch
            {
                GameObject gameObject => gameObject,
                Component component => component.gameObject,
                _ => null,
            };
        }

        private static PlayableDirector GetSelectedDirector()
        {
            var gameObject = Selection.activeGameObject;
            if (gameObject == null)
                return null;

            var director = gameObject.GetComponent<PlayableDirector>();
            if (director == null)
                return null;

            return director.playableAsset is TimelineAsset ? director : null;
        }

        [Serializable]
        internal sealed class UnitySourceSnapshotDocument
        {
            public string schema_version = "0.1.0";
            public string cutscene_id;
            public string timeline_name;
            public string timeline_asset_guid;
            public long timeline_asset_local_file_id;
            public string timeline_asset_path;
            public string director_global_object_id;
            public string director_scene_path;
            public string engine = "unity";
            public string engine_version;
            public string exporter = "CutsceneAI.UnityTimelineSourceSnapshot";
            public string exporter_version;
            public string exported_at_utc;
            public List<AnimationTrackSourceRecord> animation_tracks = new();
        }

        [Serializable]
        internal sealed class AnimationTrackSourceRecord
        {
            public string track_id;
            public string name;
            public string binding_global_object_id;
            public string binding_name;
            public bool in_clip_mode;
            public string track_offset_mode;
            public Vector3Record track_position;
            public QuaternionRecord track_rotation;
            public Vector3Record track_euler_degrees_native;
            public Vector3Record infinite_clip_offset_position;
            public QuaternionRecord infinite_clip_offset_rotation;
            public Vector3Record infinite_clip_offset_euler_degrees_native;
            public string infinite_clip_asset_id = string.Empty;
            public string infinite_clip_asset_ref = string.Empty;
            public List<AnimationClipSourceRecord> clips = new();
        }

        [Serializable]
        internal sealed class AnimationClipSourceRecord
        {
            public int index;
            public string display_name;
            public double start_seconds;
            public double end_seconds;
            public double clip_in_seconds;
            public double time_scale;
            public string playable_asset_id;
            public string animation_clip_asset_id;
            public string animation_clip_asset_ref;
            public Vector3Record clip_offset_position;
            public QuaternionRecord clip_offset_rotation;
            public Vector3Record clip_offset_euler_degrees_native;
            public bool remove_start_offset;
            public bool use_track_match_fields;
            public bool apply_foot_ik;
            public string loop_mode;
        }
    }
}
