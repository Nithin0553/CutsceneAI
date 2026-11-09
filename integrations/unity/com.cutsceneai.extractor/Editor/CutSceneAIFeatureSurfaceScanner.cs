// Read-only census of source engine types, loaded scene components and assets.
// This is a source capability/discovery snapshot, NOT a transfer certificate.
// Compatible with Unity 2022 LTS and Unity 6 editor TypeCache/AssetDatabase.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using UnityEditor;
using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.SceneManagement;
using UnityEngine.Timeline;

namespace CutsceneAI.UnityExtractor
{
    internal static class CutSceneAIFeatureSurfaceScanner
    {
        [Serializable]
        private sealed class RegisteredType
        {
            public string role;
            public string full_name;
            public string assembly_name;
        }

        [Serializable]
        private sealed class SceneComponent
        {
            public string scene_path;
            public string object_path;
            public string global_object_id;
            public string component_type;
            public string component_assembly;
            public string component_global_id;
            public bool missing_script;
            public ComponentFeature feature;
        }

        [Serializable]
        private sealed class ComponentFeature
        {
            public string extraction = "UNSUPPORTED_COMPONENT_CLASS";
            public bool has_render_post_processing;
            public bool render_post_processing;
            public bool has_render_shadows;
            public bool render_shadows;
            public bool has_use_pipeline_settings;
            public bool use_pipeline_settings;
            public bool has_light_cookie;
            public bool has_cast_shadows;
            public bool cast_shadows;
            public bool has_geometry;
            public string shape;
            public bool enabled;
            public bool is_trigger;
            public Vec3 world_center_m;
            public Vec4 world_rotation_xyzw;
            public Vec3 world_size_m;
            public float world_radius_m;
            public string collider_scale_policy;
            // Source-native MeshCollider evidence: mesh identity is retained
            // rather than substituting a bounding-box collision shape.
            public bool mesh_collider_convex;
            public int mesh_collider_cooking_options;
            public string mesh_asset_path;
            public string mesh_asset_guid;
            public string mesh_global_id;
            public string mesh_name;
            public string physics_material_asset_path;
            public string physics_material_guid;
            // LODGroup is a renderer-binding graph, not a single mesh.
            public bool lod_enabled;
            public string lod_fade_mode;
            public bool lod_animate_cross_fading;
            public bool lod_last_billboard;
            public float lod_size;
            public Vec3 lod_local_reference_point;
            public List<LODSourceLevel> lod_levels = new List<LODSourceLevel>();
            public int signal_reaction_count;
            public List<string> signal_reactions = new List<string>();
            public List<NativeValue> native_properties = new List<NativeValue>();
            public bool native_properties_truncated;
        }

        [Serializable]
        private sealed class LODSourceLevel
        {
            public float screen_relative_transition_height;
            public float fade_transition_width;
            public List<LODSourceRenderer> renderers = new List<LODSourceRenderer>();
        }

        [Serializable]
        private sealed class LODSourceRenderer
        {
            public string renderer_global_id;
            public string renderer_path;
            public string renderer_type;
            public string mesh_asset_path;
            public string mesh_asset_guid;
            public string mesh_global_id;
        }

        [Serializable]
        private sealed class NativeValue
        {
            public string path;
            public string native_type;
            public bool bool_value;
            public float float_value;
            public int int_value;
            public string string_value;
            public int enum_value_index;
            public string enum_name;
            public bool object_reference_is_null;
            public string object_reference_global_id;
            public string object_reference_asset_path;
            public string object_reference_guid;
        }

        [Serializable]
        private sealed class Vec3
        {
            public float x, y, z;
            public Vec3(Vector3 v) { x = v.x; y = v.y; z = v.z; }
        }

        [Serializable]
        private sealed class Vec4
        {
            public float x, y, z, w;
            public Vec4(Quaternion q) { x = q.x; y = q.y; z = q.z; w = q.w; }
        }

        [Serializable]
        private sealed class AssetReference
        {
            public string asset_path;
            public string guid;
            public string native_type;
            public string extension;
        }

        [Serializable]
        private sealed class Census
        {
            public string kind = "cutsceneai.engine.feature_surface";
            public string schema_version = "0.2.0";
            public string engine = "unity";
            public string engine_version;
            public string project_fingerprint;
            public string captured_utc;
            public string verification = "SOURCE_DISCOVERY_ONLY_NOT_TRANSFER_VERIFIED";
            public List<RegisteredType> registered_types = new List<RegisteredType>();
            public List<SceneComponent> loaded_scene_components = new List<SceneComponent>();
            public List<AssetReference> imported_assets = new List<AssetReference>();
            public List<string> limitations = new List<string>
            {
                "Reflection sees loaded assemblies and installed packages, not classes in unopened plugins.",
                "Authoring-time data does not prove runtime script, physics or procedural behavior.",
                "A discovered class needs explicit source extraction, target adapter and independent parity validation.",
            };
        }

        private static string HierarchyPath(Transform transform)
        {
            var names = new List<string>();
            while (transform != null)
            {
                names.Add(transform.name);
                transform = transform.parent;
            }
            names.Reverse();
            return string.Join("/", names);
        }

        private static void IncludeType(Census data, string role, Type type)
        {
            if (type == null)
                return;
            data.registered_types.Add(new RegisteredType
            {
                role = role,
                full_name = type.FullName ?? type.Name,
                assembly_name = type.Assembly.GetName().Name,
            });
        }


        private static bool TryBoolProperty(Component component, string name, out bool value)
        {
            value = false;
            try
            {
                var property = component.GetType().GetProperty(name,
                    BindingFlags.Public | BindingFlags.Instance);
                if (property != null && property.PropertyType == typeof(bool))
                {
                    value = (bool)property.GetValue(component, null);
                    return true;
                }
            }
            catch (Exception) { /* Unsupported vendor reflection remains unverified. */ }
            return false;
        }


        // This traverses serializable authoring state without changing it.
        // These fields are *evidence* for explicit target adapters, never
        // arbitrary instructions to run inside Unreal.
        private static void CollectSerializableProperties(Component component,
            ComponentFeature feature)
        {
            try
            {
                var obj = new SerializedObject(component);
                var property = obj.GetIterator();
                int count = 0;
                bool enterChildren = true;
                while (property.NextVisible(enterChildren))
                {
                    enterChildren = true;
                    if (property.propertyPath == "m_Script") continue;
                    if (count >= 256)
                    {
                        feature.native_properties_truncated = true;
                        break;
                    }
                    var value = new NativeValue { path = property.propertyPath };
                    switch (property.propertyType)
                    {
                        case SerializedPropertyType.Boolean:
                            value.native_type = "bool";
                            value.bool_value = property.boolValue;
                            break;
                        case SerializedPropertyType.Integer:
                            value.native_type = "int";
                            value.int_value = property.intValue;
                            break;
                        case SerializedPropertyType.Float:
                            value.native_type = "float";
                            value.float_value = property.floatValue;
                            if (float.IsNaN(value.float_value) ||
                                float.IsInfinity(value.float_value))
                                continue;
                            break;
                        case SerializedPropertyType.String:
                            value.native_type = "string";
                            value.string_value = property.stringValue;
                            break;
                        case SerializedPropertyType.Enum:
                            value.native_type = "enum";
                            value.int_value = property.intValue;
                            value.enum_value_index = property.enumValueIndex;
                            var names = property.enumNames;
                            if (value.enum_value_index >= 0 &&
                                value.enum_value_index < names.Length)
                                value.enum_name = names[value.enum_value_index];
                            break;
                        case SerializedPropertyType.ObjectReference:
                            // Record identity only; never traverse or execute the
                            // referenced asset or scene object's serialized data.
                            value.native_type = "object_reference";
                            var reference = property.objectReferenceValue;
                            value.object_reference_is_null = reference == null;
                            if (reference != null)
                            {
                                value.object_reference_global_id =
                                    GlobalObjectId.GetGlobalObjectIdSlow(reference).ToString();
                                value.object_reference_asset_path =
                                    AssetDatabase.GetAssetPath(reference);
                                if (!string.IsNullOrEmpty(value.object_reference_asset_path))
                                    value.object_reference_guid = AssetDatabase.AssetPathToGUID(
                                        value.object_reference_asset_path);
                            }
                            break;
                        default:
                            continue;
                    }
                    feature.native_properties.Add(value);
                    count++;
                }
            }
            catch (Exception)
            {
                // Broken custom inspectors/proprietary components may not
                // expose safe serialized state. Preserve their class and ID
                // and keep extraction coverage incomplete.
                feature.native_properties_truncated = true;
            }
        }

        private static ComponentFeature CaptureComponent(Component component)
        {
            var feature = new ComponentFeature();
            if (component == null)
            {
                feature.extraction = "MISSING_SCRIPT";
                return feature;
            }
            // These types need no optional URP compile-time dependency.
            string name = component.GetType().FullName ?? "";
            CollectSerializableProperties(component, feature);
            if (name == "UnityEngine.Rendering.Universal.UniversalAdditionalCameraData")
            {
                feature.extraction = "URP_CAMERA_PROPERTIES_PARTIAL";
                bool flag;
                feature.has_render_post_processing =
                    TryBoolProperty(component, "renderPostProcessing", out flag);
                if (feature.has_render_post_processing) feature.render_post_processing = flag;
                feature.has_render_shadows =
                    TryBoolProperty(component, "renderShadows", out flag);
                if (feature.has_render_shadows) feature.render_shadows = flag;
                return feature;
            }
            if (name == "UnityEngine.Rendering.Universal.UniversalAdditionalLightData")
            {
                feature.extraction = "URP_LIGHT_PROPERTIES_PARTIAL";
                bool flag;
                feature.has_use_pipeline_settings =
                    TryBoolProperty(component, "usePipelineSettings", out flag);
                if (feature.has_use_pipeline_settings) feature.use_pipeline_settings = flag;
                return feature;
            }
            if (component is Light unityLight)
            {
                feature.extraction = "UNITY_LIGHT_NATIVE_PROPERTIES_PARTIAL";
                feature.has_cast_shadows = true;
                feature.cast_shadows = unityLight.shadows != LightShadows.None;
                return feature;
            }
            if (component is BoxCollider box)
            {
                Vector3 scale = box.transform.lossyScale;
                Vector3 size = Vector3.Scale(box.size, new Vector3(
                    Mathf.Abs(scale.x), Mathf.Abs(scale.y), Mathf.Abs(scale.z)));
                feature.extraction = "STATIC_COLLIDER_WORLD_SHAPE_CANDIDATE";
                feature.shape = "box";
                feature.has_geometry = true;
                feature.enabled = box.enabled;
                feature.is_trigger = box.isTrigger;
                feature.world_center_m = new Vec3(box.transform.TransformPoint(box.center));
                feature.world_rotation_xyzw = new Vec4(box.transform.rotation);
                feature.world_size_m = new Vec3(size);
                feature.collider_scale_policy = "LOSSY_SCALE_NO_SHEAR_PROOF";
                return feature;
            }
            if (component is SphereCollider sphere)
            {
                Vector3 scale = sphere.transform.lossyScale;
                feature.extraction = "STATIC_COLLIDER_WORLD_SHAPE_CANDIDATE";
                feature.shape = "sphere";
                feature.has_geometry = true;
                feature.enabled = sphere.enabled;
                feature.is_trigger = sphere.isTrigger;
                feature.world_center_m = new Vec3(
                    sphere.transform.TransformPoint(sphere.center));
                feature.world_rotation_xyzw = new Vec4(sphere.transform.rotation);
                feature.world_radius_m = sphere.radius * Mathf.Max(
                    Mathf.Abs(scale.x), Mathf.Abs(scale.y), Mathf.Abs(scale.z));
                feature.collider_scale_policy = "UNITY_SPHERE_MAX_AXIS_LOSSY_SCALE";
                return feature;
            }
            if (component is MeshCollider meshCollider)
            {
                // Collision behavior cannot be reconstructed from the visible
                // mesh alone. Keep exact source mesh reference and authored flags.
                feature.extraction = "MESH_COLLIDER_SOURCE_SNAPSHOT_NATIVE_UNVERIFIED";
                feature.enabled = meshCollider.enabled;
                feature.is_trigger = meshCollider.isTrigger;
                feature.mesh_collider_convex = meshCollider.convex;
                feature.mesh_collider_cooking_options = (int)meshCollider.cookingOptions;
                var mesh = meshCollider.sharedMesh;
                if (mesh == null)
                {
                    feature.extraction = "MESH_COLLIDER_SOURCE_MESH_UNRESOLVED";
                }
                else
                {
                    feature.mesh_name = mesh.name;
                    feature.mesh_global_id =
                        GlobalObjectId.GetGlobalObjectIdSlow(mesh).ToString();
                    feature.mesh_asset_path = AssetDatabase.GetAssetPath(mesh);
                    if (!string.IsNullOrEmpty(feature.mesh_asset_path))
                        feature.mesh_asset_guid =
                            AssetDatabase.AssetPathToGUID(feature.mesh_asset_path);
                    if (string.IsNullOrEmpty(feature.mesh_asset_guid))
                        feature.extraction = "MESH_COLLIDER_SOURCE_MESH_UNRESOLVED";
                }
                var material = meshCollider.sharedMaterial;
                if (material != null)
                {
                    feature.physics_material_asset_path =
                        AssetDatabase.GetAssetPath(material);
                    if (!string.IsNullOrEmpty(feature.physics_material_asset_path))
                        feature.physics_material_guid = AssetDatabase.AssetPathToGUID(
                            feature.physics_material_asset_path);
                }
                return feature;
            }
            if (component is LODGroup lodGroup)
            {
                feature.extraction = "LOD_GROUP_SOURCE_SNAPSHOT_NATIVE_UNVERIFIED";
                feature.lod_enabled = lodGroup.enabled;
                feature.lod_fade_mode = lodGroup.fadeMode.ToString();
                feature.lod_animate_cross_fading = lodGroup.animateCrossFading;
                feature.lod_last_billboard = lodGroup.lastLODBillboard;
                feature.lod_size = lodGroup.size;
                feature.lod_local_reference_point = new Vec3(lodGroup.localReferencePoint);
                var levels = lodGroup.GetLODs();
                if (levels == null || levels.Length == 0 || levels.Length > 32)
                {
                    feature.extraction = "LOD_GROUP_LEVELS_UNRESOLVED";
                    return feature;
                }
                foreach (var level in levels)
                {
                    var evidence = new LODSourceLevel
                    {
                        screen_relative_transition_height =
                            level.screenRelativeTransitionHeight,
                        fade_transition_width = level.fadeTransitionWidth,
                    };
                    foreach (var renderer in level.renderers)
                    {
                        if (renderer == null)
                        {
                            feature.extraction = "LOD_GROUP_RENDERER_UNRESOLVED";
                            continue;
                        }
                        Mesh mesh = null;
                        if (renderer is SkinnedMeshRenderer skinned)
                            mesh = skinned.sharedMesh;
                        else if (renderer is MeshRenderer)
                        {
                            var filter = renderer.GetComponent<MeshFilter>();
                            mesh = filter == null ? null : filter.sharedMesh;
                        }
                        var path = mesh == null ? "" : AssetDatabase.GetAssetPath(mesh);
                        var guid = string.IsNullOrEmpty(path) ? "" :
                            AssetDatabase.AssetPathToGUID(path);
                        var rendererEvidence = new LODSourceRenderer
                        {
                            renderer_global_id =
                                GlobalObjectId.GetGlobalObjectIdSlow(renderer).ToString(),
                            renderer_path = HierarchyPath(renderer.transform),
                            renderer_type = renderer.GetType().FullName,
                            mesh_asset_path = path,
                            mesh_asset_guid = guid,
                            mesh_global_id = mesh == null ? "" :
                                GlobalObjectId.GetGlobalObjectIdSlow(mesh).ToString(),
                        };
                        evidence.renderers.Add(rendererEvidence);
                        if (string.IsNullOrEmpty(guid) ||
                            string.IsNullOrEmpty(rendererEvidence.mesh_global_id))
                            feature.extraction = "LOD_GROUP_RENDERER_UNRESOLVED";
                    }
                    feature.lod_levels.Add(evidence);
                }
                return feature;
            }
            if (component is UnityEngine.Timeline.SignalReceiver receiver)
            {
                feature.extraction = "SIGNAL_REACTIONS_INSPECTED_NO_TARGET_EVENT_BINDING";
                try
                {
                    foreach (var signal in receiver.GetRegisteredSignals())
                    {
                        var reaction = receiver.GetReaction(signal);
                        if (reaction == null) continue;
                        for (int k = 0; k < reaction.GetPersistentEventCount(); k++)
                        {
                            var target = reaction.GetPersistentTarget(k);
                            var method = reaction.GetPersistentMethodName(k);
                            feature.signal_reactions.Add((target == null ? "MISSING_TARGET" :
                                GlobalObjectId.GetGlobalObjectIdSlow(target).ToString()) +
                                ":" + method);
                            feature.signal_reaction_count++;
                        }
                    }
                }
                catch (Exception)
                {
                    feature.extraction = "SIGNAL_REACTION_REFLECTION_INCOMPLETE";
                }
                return feature;
            }
            feature.extraction = "NOT_YET_EXTRACTED";
            return feature;
        }

        [MenuItem("Tools/CutsceneAI/Discover Installed Feature Surface", priority = 91)]
        private static void Discover()
        {
            var data = new Census
            {
                engine_version = Application.unityVersion,
                project_fingerprint = ExtractorUtilities.ProjectFingerprint(),
                captured_utc = DateTime.UtcNow.ToString("o"),
            };
            foreach (var type in TypeCache.GetTypesDerivedFrom<Component>())
                IncludeType(data, "component", type);
            foreach (var type in TypeCache.GetTypesDerivedFrom<ScriptableObject>())
                IncludeType(data, "scriptable_object", type);
            foreach (var type in TypeCache.GetTypesDerivedFrom<PlayableAsset>())
                IncludeType(data, "playable_asset", type);
            foreach (var type in TypeCache.GetTypesDerivedFrom<TrackAsset>())
                IncludeType(data, "timeline_track", type);
            data.registered_types = data.registered_types
                .OrderBy(row => row.role).ThenBy(row => row.full_name).ToList();

            for (var sceneIndex = 0; sceneIndex < SceneManager.sceneCount; sceneIndex++)
            {
                var scene = SceneManager.GetSceneAt(sceneIndex);
                if (!scene.isLoaded)
                    continue;
                foreach (var root in scene.GetRootGameObjects())
                {
                    // Iterate source GameObjects first so even null/missing
                    // MonoBehaviour components are recorded against the correct
                    // child path, not incorrectly attributed to the scene root.
                    foreach (var transform in root.GetComponentsInChildren<Transform>(true))
                    {
                        var go = transform.gameObject;
                        foreach (var component in go.GetComponents<Component>())
                        {
                            var absent = component == null;
                            data.loaded_scene_components.Add(new SceneComponent
                            {
                                scene_path = scene.path,
                                object_path = HierarchyPath(go.transform),
                                global_object_id = GlobalObjectId.GetGlobalObjectIdSlow(go).ToString(),
                                component_type = absent ? "MISSING_MONOBEHAVIOUR_SCRIPT" :
                                    component.GetType().FullName,
                                component_assembly = absent ? "" :
                                    component.GetType().Assembly.GetName().Name,
                                component_global_id = absent ? "" :
                                    GlobalObjectId.GetGlobalObjectIdSlow(component).ToString(),
                                missing_script = absent,
                                feature = CaptureComponent(component),
                            });
                        }
                    }
                }
            }
            foreach (var path in AssetDatabase.GetAllAssetPaths())
            {
                if (!(path.StartsWith("Assets/", StringComparison.Ordinal) ||
                      path.StartsWith("Packages/", StringComparison.Ordinal)) ||
                    AssetDatabase.IsValidFolder(path))
                    continue;
                Type assetType;
                try
                {
                    assetType = AssetDatabase.GetMainAssetTypeAtPath(path);
                }
                catch (Exception)
                {
                    assetType = null;
                }
                data.imported_assets.Add(new AssetReference
                {
                    asset_path = path,
                    guid = AssetDatabase.AssetPathToGUID(path),
                    native_type = assetType == null ? "UNKNOWN_NATIVE_ASSET" :
                        (assetType.FullName ?? assetType.Name),
                    extension = Path.GetExtension(path),
                });
            }
            data.imported_assets = data.imported_assets
                .OrderBy(row => row.asset_path).ToList();

            var projectRoot = Directory.GetParent(Application.dataPath).FullName;
            var outputDir = Path.Combine(projectRoot, "CutSceneAI", "Exports");
            Directory.CreateDirectory(outputDir);
            var name = "feature-surface-unity-" +
                DateTime.UtcNow.ToString("yyyyMMddTHHmmssfffZ") + "-" +
                Guid.NewGuid().ToString("N").Substring(0, 8) + ".json";
            var output = Path.Combine(outputDir, name);
            // Unique filename, write outside Assets; never update native assets/scenes.
            using (var stream = new FileStream(output, FileMode.CreateNew, FileAccess.Write))
            using (var writer = new StreamWriter(stream))
                writer.Write(JsonUtility.ToJson(data, true));
            Debug.Log("[CutSceneAI] Source feature surface saved: " + output +
                " | types=" + data.registered_types.Count +
                " components=" + data.loaded_scene_components.Count +
                " assets=" + data.imported_assets.Count +
                " | conversion fidelity NOT VERIFIED");
        }
    }
}
