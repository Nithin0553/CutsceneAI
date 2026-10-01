using System;
using System.Collections.Generic;

namespace CutsceneAI.UnityExtractor
{
    [Serializable]
    internal sealed class CsirDocument
    {
        public string schema_version = "0.1.0";
        public string cutscene_id;
        public string name;
        public SourceInfo source;
        public CoordinateSystem coordinate_system;
        public SequenceTiming timing;
        public List<AssetRecord> assets = new();
        public List<EntityRecord> entities = new();
        public List<TrackRecord> tracks = new();
        public List<RelationshipRecord> relationships = new();
        public SourceSnapshot source_snapshot;
        public Provenance provenance;
    }

    [Serializable]
    internal sealed class SourceInfo
    {
        public string engine = "unity";
        public string engine_version;
        public string adapter_version = "0.1.0";
        public string project_fingerprint;
        public string sequence_ref;
    }

    [Serializable]
    internal sealed class CoordinateSystem
    {
        public string handedness = "RIGHT_HANDED";
        public string up_axis = "+Y";
        public string forward_axis = "-Z";
        public string right_axis = "+X";
        public string linear_unit = "METER";
        public string angular_unit = "RADIAN";
        public string rotation_representation = "QUATERNION_XYZW";
    }

    [Serializable]
    internal sealed class RationalRate
    {
        public long numerator;
        public long denominator;

        public RationalRate(long numerator, long denominator)
        {
            this.numerator = numerator;
            this.denominator = denominator;
        }
    }

    [Serializable]
    internal sealed class RationalTime
    {
        public long value;
        public RationalRate rate;

        public RationalTime(long value, RationalRate rate)
        {
            this.value = value;
            this.rate = rate;
        }
    }

    [Serializable]
    internal sealed class SequenceTiming
    {
        public RationalRate source_rate;
        public RationalRate display_rate;
        public RationalRate tick_resolution;
        public RationalTime playback_start;
        public RationalTime playback_end;
        public double duration_seconds;
        public double preroll_seconds;
        public double postroll_seconds;
    }

    [Serializable]
    internal sealed class AssetRecord
    {
        public string asset_id;
        public string ced_type;
        public string name;
        public string source_ref;
        public AssetMetadata metadata;
    }

    [Serializable]
    internal sealed class AssetMetadata
    {
        public string asset_path;
        public string asset_type;
        public string guid;
        public long local_file_id;
    }

    [Serializable]
    internal sealed class EntityRecord
    {
        public string entity_id;
        public string ced_type;
        public string name;
        public string native_ref;
        public string parent_entity_id;
        public EntityMetadata metadata;
    }

    [Serializable]
    internal sealed class EntityMetadata
    {
        public string scene_path;
        public string hierarchy_path;
        public bool active_self;
        public TransformSnapshot local_transform;
        public TransformSnapshot world_transform;
        public CameraMetadata camera;
        public AnimatorMetadata animator;
    }

    [Serializable]
    internal sealed class TransformSnapshot
    {
        public Vector3Record position;
        public QuaternionRecord rotation;
        public Vector3Record scale;
    }

    [Serializable]
    internal sealed class Vector2Record
    {
        public double x;
        public double y;
    }

    [Serializable]
    internal sealed class Vector3Record
    {
        public double x;
        public double y;
        public double z;
    }

    [Serializable]
    internal sealed class QuaternionRecord
    {
        public double x;
        public double y;
        public double z;
        public double w;
    }

    [Serializable]
    internal sealed class CameraMetadata
    {
        public bool orthographic;
        public double orthographic_size;
        public double field_of_view_degrees;
        public bool use_physical_properties;
        public double focal_length_mm;
        public Vector2Record sensor_size_mm;
        public Vector2Record lens_shift;
        public double near_clip;
        public double far_clip;
        public double aspect;
    }

    [Serializable]
    internal sealed class AnimatorMetadata
    {
        public bool apply_root_motion;
        public bool has_avatar;
        public bool avatar_is_human;
        public string avatar_ref;
        public string controller_ref;
    }

    [Serializable]
    internal sealed class TrackRecord
    {
        public string track_id;
        public string ced_type;
        public string name;
        public string binding_entity_id;
        public bool muted;
        public List<SectionRecord> sections = new();
        public TrackMetadata metadata;
    }

    [Serializable]
    internal sealed class TrackMetadata
    {
        public string native_type;
        public string parent_track_id;
        public bool supports_notifications;
        public bool has_curves;
        public double start_seconds;
        public double end_seconds;
        public string binding_native_type;
    }

    [Serializable]
    internal sealed class SectionRecord
    {
        public string section_id;
        public string ced_type;
        public RationalTime start;
        public RationalTime end;
        public RationalTime source_offset;
        public double time_scale = 1.0;
        public bool loop;
        public SectionPayload payload;
        public NativeSectionPayload native_payload;
    }

    [Serializable]
    internal sealed class SectionPayload
    {
        public string display_name;
        public string asset_id;
        public AnimationPayload animation;
        public AudioPayload audio;
        public ActivationPayload activation;
        public SignalPayload signal;
        public GenericPayload generic;
    }

    [Serializable]
    internal sealed class NativeSectionPayload
    {
        public string native_asset_type;
        public double start_seconds;
        public double end_seconds;
        public double duration_seconds;
        public double clip_in_seconds;
        public double time_scale;
        public double blend_in_seconds;
        public double blend_out_seconds;
        public double ease_in_seconds;
        public double ease_out_seconds;
    }

    [Serializable]
    internal sealed class AnimationPayload
    {
        public bool apply_foot_ik;
        public List<CurveRecord> curves = new();
        public List<ObjectReferenceCurveRecord> object_reference_curves = new();
    }

    [Serializable]
    internal sealed class CurveRecord
    {
        public string path;
        public string component_type;
        public string property_name;
        public string canonical_semantic;
        public string conversion;
        public List<KeyframeRecord> keys = new();
    }

    [Serializable]
    internal sealed class KeyframeRecord
    {
        public double time_seconds;
        public double value;
        public double in_tangent;
        public double out_tangent;
        public double in_weight;
        public double out_weight;
        public int weighted_mode;
    }

    [Serializable]
    internal sealed class ObjectReferenceCurveRecord
    {
        public string path;
        public string component_type;
        public string property_name;
        public List<ObjectReferenceKeyRecord> keys = new();
    }

    [Serializable]
    internal sealed class ObjectReferenceKeyRecord
    {
        public double time_seconds;
        public string value_ref;
    }

    [Serializable]
    internal sealed class AudioPayload
    {
        public bool loop;
        public int channels;
        public int frequency;
        public int samples;
        public double clip_length_seconds;
    }

    [Serializable]
    internal sealed class ActivationPayload
    {
        public bool active = true;
        public string post_playback_state;
    }

    [Serializable]
    internal sealed class SignalPayload
    {
        public string signal_asset_id;
        public bool emit_once;
        public bool retroactive;
    }

    [Serializable]
    internal sealed class GenericPayload
    {
        public string native_type;
        public string asset_ref;
    }

    [Serializable]
    internal sealed class RelationshipRecord
    {
        public string relationship_id;
        public string ced_type;
        public string source_id;
        public string target_id;
        public RelationshipMetadata metadata;
    }

    [Serializable]
    internal sealed class RelationshipMetadata
    {
        public string reason;
    }

    [Serializable]
    internal sealed class SourceSnapshot
    {
        public string timeline_asset_guid;
        public long timeline_asset_local_file_id;
        public string timeline_asset_path;
        public string director_global_object_id;
        public string director_scene_path;
        public string director_name;
        public int root_track_count;
        public int output_track_count;
        public int extracted_track_count;
        public int extracted_entity_count;
        public int extracted_asset_count;
    }

    [Serializable]
    internal sealed class Provenance
    {
        public string extractor;
        public string extractor_version;
        public string extracted_at_utc;
        public string source_snapshot_hash;
        public List<string> notes = new();
    }
}
