// Read-only census of source engine types, loaded scene components and assets.
// This is a source capability/discovery snapshot, NOT a transfer certificate.
// Compatible with Unity 2022 LTS and Unity 6 editor TypeCache/AssetDatabase.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
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

        [MenuItem("Tools/CutsceneAI/Discover Installed Feature Surface", priority = 91)]
        private static void Discover()
        {
            var data = new Census
            {
                engine_version = Application.unityVersion,
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
