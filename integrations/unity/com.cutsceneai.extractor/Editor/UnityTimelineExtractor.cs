using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.Timeline;

namespace CutsceneAI.UnityExtractor
{
    internal static class UnityTimelineExtractor
    {
        internal const string ExtractorName = "CutsceneAI.UnityTimelineExtractor";
        internal const string ExtractorVersion = "0.1.2";

        internal static string Export(PlayableDirector director)
        {
            if (director == null)
                throw new ArgumentNullException(nameof(director));
            if (director.playableAsset is not TimelineAsset timeline)
                throw new InvalidOperationException("Selected PlayableDirector does not reference a TimelineAsset.");

            var context = new ExtractionContext(director, timeline);
            var document = context.Extract();
            var json = JsonUtility.ToJson(document, true);

            var projectRoot = Directory.GetParent(Application.dataPath)?.FullName ?? Application.dataPath;
            var exportDirectory = Path.Combine(projectRoot, "CutsceneAI", "Exports");
            Directory.CreateDirectory(exportDirectory);

            var shortId = context.TimelineGuid.Length >= 8 ? context.TimelineGuid[..8] : context.TimelineGuid;
            var fileName = $"{ExtractorUtilities.SafeFileName(timeline.name)}-{shortId}.csir.json";
            var outputPath = Path.Combine(exportDirectory, fileName);
            File.WriteAllText(outputPath, json);
            return outputPath;
        }

        private sealed class ExtractionContext
        {
            private readonly PlayableDirector _director;
            private readonly TimelineAsset _timeline;
            private readonly Dictionary<string, AssetRecord> _assets = new();
            private readonly Dictionary<string, EntityRecord> _entities = new();
            private readonly HashSet<string> _visitedTracks = new();
            private readonly RationalRate _sourceRate;

            internal string TimelineGuid { get; }
            private long TimelineLocalId { get; }
            private string TimelinePath { get; }

            internal ExtractionContext(PlayableDirector director, TimelineAsset timeline)
            {
                _director = director;
                _timeline = timeline;
                _sourceRate = ExtractorUtilities.FrameRateToRational(timeline.editorSettings.frameRate);

                if (!ExtractorUtilities.TryGetAssetIdentity(timeline, out var guid, out var localId, out var path))
                    throw new InvalidOperationException("TimelineAsset must be saved in the Unity project before extraction.");

                TimelineGuid = guid;
                TimelineLocalId = localId;
                TimelinePath = path;
            }

            internal CsirDocument Extract()
            {
                var document = new CsirDocument
                {
                    cutscene_id = $"unity:{TimelineGuid}:{TimelineLocalId}",
                    name = _timeline.name,
                    source = new SourceInfo
                    {
                        adapter_version = ExtractorVersion,
                        engine_version = Application.unityVersion,
                        project_fingerprint = ExtractorUtilities.ProjectFingerprint(),
                        sequence_ref = $"{TimelinePath}|guid={TimelineGuid}|local={TimelineLocalId}",
                    },
                    coordinate_system = new CoordinateSystem(),
                    timing = new SequenceTiming
                    {
                        source_rate = _sourceRate,
                        display_rate = _sourceRate,
                        tick_resolution = ExtractorUtilities.MicrosecondRate,
                        playback_start = ExtractorUtilities.SecondsToRationalTime(0.0),
                        playback_end = ExtractorUtilities.SecondsToRationalTime(_timeline.duration),
                        duration_seconds = _timeline.duration,
                        preroll_seconds = 0.0,
                        postroll_seconds = 0.0,
                    },
                    provenance = new Provenance
                    {
                        extractor = ExtractorName,
                        extractor_version = ExtractorVersion,
                        extracted_at_utc = DateTime.UtcNow.ToString("O"),
                    },
                };

                AddAsset(_timeline, "sequence.root");

                foreach (var rootTrack in _timeline.GetRootTracks())
                    ExtractTrackRecursive(rootTrack, document);

                var markerTrack = _timeline.markerTrack;
                if (markerTrack != null)
                    ExtractTrackRecursive(markerTrack, document);

                foreach (var asset in _assets.Values)
                    document.assets.Add(asset);
                foreach (var entity in _entities.Values)
                    document.entities.Add(entity);

                var snapshot = new SourceSnapshot
                {
                    timeline_asset_guid = TimelineGuid,
                    timeline_asset_local_file_id = TimelineLocalId,
                    timeline_asset_path = TimelinePath,
                    director_global_object_id = GlobalObjectId.GetGlobalObjectIdSlow(_director).ToString(),
                    director_scene_path = _director.gameObject.scene.path ?? string.Empty,
                    director_name = _director.name,
                    root_track_count = _timeline.rootTrackCount,
                    output_track_count = _timeline.outputTrackCount,
                    extracted_track_count = document.tracks.Count,
                    extracted_entity_count = document.entities.Count,
                    extracted_asset_count = document.assets.Count,
                };
                document.source_snapshot = snapshot;
                document.provenance.source_snapshot_hash = "sha256:" + ExtractorUtilities.Sha256(JsonUtility.ToJson(snapshot, false));
                document.provenance.notes.Add("Structural extraction only; PlayableDirector.Evaluate was not called.");
                document.provenance.notes.Add("Raw Unity animation key values are retained beside canonicalized transform channels.");
                document.provenance.notes.Add("Activation clips are classified from ActivationTrack because Unity Timeline 1.8 does not expose the implementation playable publicly.");
                document.provenance.notes.Add("Infinite AnimationTrack clips are exported explicitly so recorded transform/property tracks are not lost.");
                return document;
            }

            private void ExtractTrackRecursive(TrackAsset track, CsirDocument document)
            {
                if (track == null)
                    return;

                var trackId = ExtractorUtilities.StableAssetId(track);
                if (!_visitedTracks.Add(trackId))
                    return;

                var binding = _director.GetGenericBinding(track);
                var bindingGameObject = ResolveGameObject(binding);
                var bindingEntityId = bindingGameObject != null ? EnsureEntity(bindingGameObject) : string.Empty;

                var record = new TrackRecord
                {
                    track_id = trackId,
                    ced_type = ClassifyTrack(track, bindingGameObject),
                    name = track.name,
                    binding_entity_id = bindingEntityId,
                    muted = track.muted,
                    metadata = new TrackMetadata
                    {
                        native_type = track.GetType().FullName ?? track.GetType().Name,
                        parent_track_id = track.parent is TrackAsset parent ? ExtractorUtilities.StableAssetId(parent) : string.Empty,
                        supports_notifications = track.supportsNotifications,
                        has_curves = track.hasCurves,
                        start_seconds = IsFinite(track.start) ? track.start : 0.0,
                        end_seconds = IsFinite(track.end) ? track.end : 0.0,
                        binding_native_type = binding != null ? binding.GetType().FullName ?? binding.GetType().Name : string.Empty,
                    },
                };

                var clipIndex = 0;
                foreach (var clip in track.GetClips())
                {
                    record.sections.Add(ExtractClip(track, clip, bindingGameObject, clipIndex));
                    clipIndex++;
                }

                if (track is AnimationTrack animationTrack && animationTrack.infiniteClip != null)
                    record.sections.Add(ExtractInfiniteAnimationTrack(animationTrack, bindingGameObject));

                var markerIndex = 0;
                foreach (var marker in track.GetMarkers())
                {
                    record.sections.Add(ExtractMarker(track, marker, markerIndex));
                    markerIndex++;
                }

                document.tracks.Add(record);

                foreach (var child in track.GetChildTracks())
                    ExtractTrackRecursive(child, document);
            }

            private SectionRecord ExtractInfiniteAnimationTrack(AnimationTrack track, GameObject bindingGameObject)
            {
                var clip = track.infiniteClip;
                var trackEnd = IsFinite(track.end) && track.end > 0.0 ? track.end : clip.length;
                var assetId = AddAsset(clip, "animation.clip");
                var isCamera = bindingGameObject != null && bindingGameObject.GetComponent<Camera>() != null;
                var section = new SectionRecord
                {
                    section_id = $"{ExtractorUtilities.StableAssetId(track)}:infinite",
                    ced_type = isCamera ? "camera.transform" : "animation.section",
                    start = ExtractorUtilities.SecondsToRationalTime(0.0),
                    end = ExtractorUtilities.SecondsToRationalTime(trackEnd),
                    source_offset = ExtractorUtilities.SecondsToRationalTime(0.0),
                    time_scale = 1.0,
                    loop = false,
                    payload = CreateEmptyPayload(clip.name, assetId),
                    native_payload = new NativeSectionPayload
                    {
                        native_asset_type = clip.GetType().FullName ?? clip.GetType().Name,
                        start_seconds = 0.0,
                        end_seconds = trackEnd,
                        duration_seconds = clip.length,
                        clip_in_seconds = 0.0,
                        time_scale = 1.0,
                        blend_in_seconds = 0.0,
                        blend_out_seconds = 0.0,
                        ease_in_seconds = 0.0,
                        ease_out_seconds = 0.0,
                    },
                };

                ExtractAnimationCurves(clip, section.payload.animation);
                return section;
            }

            private SectionRecord ExtractClip(TrackAsset track, TimelineClip clip, GameObject bindingGameObject, int index)
            {
                UnityEngine.Object asset = clip.asset;
                var assetId = asset != null ? AddAsset(asset, ClassifyClipAsset(track, asset)) : string.Empty;
                var sectionId = $"{ExtractorUtilities.StableAssetId(track)}:clip:{index}:{ToMicroseconds(clip.start)}";
                var section = new SectionRecord
                {
                    section_id = sectionId,
                    ced_type = ClassifySection(track, asset, bindingGameObject),
                    start = ExtractorUtilities.SecondsToRationalTime(clip.start),
                    end = ExtractorUtilities.SecondsToRationalTime(clip.end),
                    source_offset = ExtractorUtilities.SecondsToRationalTime(clip.clipIn),
                    time_scale = clip.timeScale > 0.0 ? clip.timeScale : 1.0,
                    loop = false,
                    payload = CreateEmptyPayload(clip.displayName, assetId),
                    native_payload = new NativeSectionPayload
                    {
                        native_asset_type = asset != null ? asset.GetType().FullName ?? asset.GetType().Name : string.Empty,
                        start_seconds = clip.start,
                        end_seconds = clip.end,
                        duration_seconds = clip.duration,
                        clip_in_seconds = clip.clipIn,
                        time_scale = clip.timeScale,
                        blend_in_seconds = clip.blendInDuration,
                        blend_out_seconds = clip.blendOutDuration,
                        ease_in_seconds = clip.easeInDuration,
                        ease_out_seconds = clip.easeOutDuration,
                    },
                };

                if (track is ActivationTrack activationTrack)
                {
                    section.payload.activation.active = true;
                    section.payload.activation.post_playback_state = activationTrack.postPlaybackState.ToString();
                }
                else if (asset is AnimationPlayableAsset animationPlayable)
                {
                    section.payload.animation.apply_foot_ik = animationPlayable.applyFootIK;
                    if (animationPlayable.clip != null)
                    {
                        section.payload.asset_id = AddAsset(animationPlayable.clip, "animation.clip");
                        ExtractAnimationCurves(animationPlayable.clip, section.payload.animation);
                    }
                }
                else if (asset is AudioPlayableAsset audioPlayable)
                {
                    section.loop = audioPlayable.loop;
                    section.payload.audio.loop = audioPlayable.loop;
                    if (audioPlayable.clip != null)
                    {
                        section.payload.asset_id = AddAsset(audioPlayable.clip, "audio.asset");
                        section.payload.audio.channels = audioPlayable.clip.channels;
                        section.payload.audio.frequency = audioPlayable.clip.frequency;
                        section.payload.audio.samples = audioPlayable.clip.samples;
                        section.payload.audio.clip_length_seconds = audioPlayable.clip.length;
                    }
                }
                else
                {
                    section.payload.generic.native_type = asset != null ? asset.GetType().FullName ?? asset.GetType().Name : string.Empty;
                    section.payload.generic.asset_ref = asset != null ? ExtractorUtilities.AssetReference(asset) : string.Empty;
                }

                return section;
            }

            private SectionRecord ExtractMarker(TrackAsset track, IMarker marker, int index)
            {
                var markerObject = marker as UnityEngine.Object;
                var markerType = markerObject != null ? markerObject.GetType().FullName ?? markerObject.GetType().Name : marker.GetType().FullName ?? marker.GetType().Name;
                var markerId = markerObject != null ? ExtractorUtilities.StableAssetId(markerObject) : $"{ExtractorUtilities.StableAssetId(track)}:marker:{index}:{ToMicroseconds(marker.time)}";
                var section = new SectionRecord
                {
                    section_id = markerId,
                    ced_type = marker is SignalEmitter ? "event.trigger" : "timeline.marker",
                    start = ExtractorUtilities.SecondsToRationalTime(marker.time),
                    end = ExtractorUtilities.SecondsToRationalTime(marker.time),
                    source_offset = ExtractorUtilities.SecondsToRationalTime(0.0),
                    time_scale = 1.0,
                    loop = false,
                    payload = CreateEmptyPayload(markerType, string.Empty),
                    native_payload = new NativeSectionPayload
                    {
                        native_asset_type = markerType,
                        start_seconds = marker.time,
                        end_seconds = marker.time,
                        duration_seconds = 0.0,
                        clip_in_seconds = 0.0,
                        time_scale = 1.0,
                        blend_in_seconds = 0.0,
                        blend_out_seconds = 0.0,
                        ease_in_seconds = 0.0,
                        ease_out_seconds = 0.0,
                    },
                };

                if (marker is SignalEmitter signal)
                {
                    section.payload.signal.emit_once = signal.emitOnce;
                    section.payload.signal.retroactive = signal.retroactive;
                    if (signal.asset != null)
                        section.payload.signal.signal_asset_id = AddAsset(signal.asset, "event.trigger");
                }
                else
                {
                    section.payload.generic.native_type = markerType;
                    section.payload.generic.asset_ref = markerObject != null ? ExtractorUtilities.AssetReference(markerObject) : string.Empty;
                }

                return section;
            }

            private void ExtractAnimationCurves(AnimationClip clip, AnimationPayload payload)
            {
                foreach (var binding in AnimationUtility.GetCurveBindings(clip))
                {
                    var curve = AnimationUtility.GetEditorCurve(clip, binding);
                    if (curve == null)
                        continue;

                    var record = new CurveRecord
                    {
                        path = binding.path ?? string.Empty,
                        component_type = binding.type != null ? binding.type.FullName ?? binding.type.Name : string.Empty,
                        property_name = binding.propertyName ?? string.Empty,
                    };

                    foreach (var key in curve.keys)
                    {
                        var nativeKey = CreateKeyRecord(key, key.value, key.inTangent, key.outTangent);
                        record.native_keys.Add(nativeKey);

                        var canonicalValue = ExtractorUtilities.ConvertCurveValueToCanonical(binding.propertyName ?? string.Empty, key.value, out var semantic, out var conversion);
                        record.canonical_semantic = semantic;
                        record.conversion = conversion;

                        var negate = conversion == "negate_z_for_right_handed_basis" || conversion == "negate_xy_for_right_handed_basis";
                        var canonicalKey = CreateKeyRecord(
                            key,
                            canonicalValue,
                            negate ? -key.inTangent : key.inTangent,
                            negate ? -key.outTangent : key.outTangent);
                        record.keys.Add(canonicalKey);
                    }

                    payload.curves.Add(record);
                }

                foreach (var binding in AnimationUtility.GetObjectReferenceCurveBindings(clip))
                {
                    var record = new ObjectReferenceCurveRecord
                    {
                        path = binding.path ?? string.Empty,
                        component_type = binding.type != null ? binding.type.FullName ?? binding.type.Name : string.Empty,
                        property_name = binding.propertyName ?? string.Empty,
                    };

                    var keys = AnimationUtility.GetObjectReferenceCurve(clip, binding);
                    if (keys != null)
                    {
                        foreach (var key in keys)
                        {
                            record.keys.Add(new ObjectReferenceKeyRecord
                            {
                                time_seconds = key.time,
                                value_ref = key.value != null ? ExtractorUtilities.AssetReference(key.value) : string.Empty,
                            });
                        }
                    }

                    payload.object_reference_curves.Add(record);
                }
            }

            private static KeyframeRecord CreateKeyRecord(Keyframe key, double value, double inTangent, double outTangent)
            {
                return new KeyframeRecord
                {
                    time_seconds = key.time,
                    value = value,
                    in_tangent = inTangent,
                    out_tangent = outTangent,
                    in_weight = key.inWeight,
                    out_weight = key.outWeight,
                    weighted_mode = (int)key.weightedMode,
                };
            }

            private string EnsureEntity(GameObject gameObject)
            {
                var id = ExtractorUtilities.StableSceneObjectId(gameObject);
                if (_entities.ContainsKey(id))
                    return id;

                var camera = gameObject.GetComponent<Camera>();
                var audioSource = gameObject.GetComponent<AudioSource>();
                var animator = gameObject.GetComponent<Animator>();
                var hasCharacterRig =
                    gameObject.GetComponentInChildren<SkinnedMeshRenderer>(true) != null ||
                    (animator != null && animator.avatar != null);

                var entity = new EntityRecord
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
                };

                _entities[id] = entity;
                return id;
            }

            private string AddAsset(UnityEngine.Object asset, string cedType)
            {
                if (asset == null)
                    return string.Empty;

                var id = ExtractorUtilities.StableAssetId(asset);
                if (_assets.ContainsKey(id))
                    return id;

                ExtractorUtilities.TryGetAssetIdentity(asset, out var guid, out var localId, out var path);
                _assets[id] = new AssetRecord
                {
                    asset_id = id,
                    ced_type = cedType,
                    name = asset.name ?? string.Empty,
                    source_ref = ExtractorUtilities.AssetReference(asset),
                    metadata = new AssetMetadata
                    {
                        asset_path = path ?? string.Empty,
                        asset_type = asset.GetType().FullName ?? asset.GetType().Name,
                        guid = guid ?? string.Empty,
                        local_file_id = localId,
                    },
                };
                return id;
            }

            private static SectionPayload CreateEmptyPayload(string displayName, string assetId)
            {
                return new SectionPayload
                {
                    display_name = displayName ?? string.Empty,
                    asset_id = assetId ?? string.Empty,
                    animation = new AnimationPayload(),
                    audio = new AudioPayload(),
                    activation = new ActivationPayload { post_playback_state = string.Empty },
                    signal = new SignalPayload { signal_asset_id = string.Empty },
                    generic = new GenericPayload { native_type = string.Empty, asset_ref = string.Empty },
                };
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
                    controller_ref = animator.runtimeAnimatorController != null ? ExtractorUtilities.AssetReference(animator.runtimeAnimatorController) : string.Empty,
                };
            }

            private static GameObject ResolveGameObject(UnityEngine.Object binding)
            {
                return binding switch
                {
                    GameObject go => go,
                    Component component => component.gameObject,
                    _ => null,
                };
            }

            private static string ClassifyTrack(TrackAsset track, GameObject binding)
            {
                if (track is AnimationTrack)
                    return binding != null && binding.GetComponent<Camera>() != null ? "camera.transform" : "animation.track";
                if (track is AudioTrack)
                    return "audio.track";
                if (track is ActivationTrack)
                    return binding != null && binding.GetComponent<Camera>() != null ? "camera.cut" : "event.state";
                if (track is SignalTrack)
                    return "event.trigger";
                return "timeline.track";
            }

            private static string ClassifySection(TrackAsset track, UnityEngine.Object asset, GameObject binding)
            {
                if (track is ActivationTrack)
                    return binding != null && binding.GetComponent<Camera>() != null ? "camera.cut" : "event.state";
                if (asset is AnimationPlayableAsset)
                    return "animation.section";
                if (asset is AudioPlayableAsset)
                    return "audio.section";
                return "timeline.clip";
            }

            private static string ClassifyClipAsset(TrackAsset track, UnityEngine.Object asset)
            {
                if (track is ActivationTrack)
                    return "event.state";
                if (asset is AnimationPlayableAsset)
                    return "animation.clip";
                if (asset is AudioPlayableAsset)
                    return "audio.asset";
                return "timeline.clip";
            }

            private static long ToMicroseconds(double seconds) => (long)Math.Round(seconds * 1_000_000.0);
            private static bool IsFinite(double value) => !double.IsNaN(value) && !double.IsInfinity(value);
        }
    }
}
