// CineTwin Phase 1: capture observed source Timeline behavior in Play Mode.
// This is a separate assembly from the read-only structural CSIR extractor.
// Play Mode is required so sampled transforms are not written to the authored scene.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.Timeline;

namespace CutSceneAI.CineTwin
{
    internal static class CineTwinBehaviorCapture
    {
        private const string MenuPath =
            "Tools/CutsceneAI/CineTwin/Capture Selected Timeline Behavior (Play Mode)";

        [Serializable]
        private class SourceInfo
        {
            public string engine;
            public string engine_version;
            public string sequence_ref;
            public string project_fingerprint;
            public string csir_sha256;
        }

        [Serializable]
        private class PlannedEntity
        {
            public string entity_id;
            public string name;
            public string ced_type;
            public string hierarchy_path;
            public string parent_entity_id;
        }

        [Serializable]
        private class PlannedSample
        {
            public double time_seconds;
        }

        [Serializable]
        private class SamplingPlan
        {
            public string kind;
            public string cutscene_id;
            public SourceInfo source;
            public PlannedEntity[] entities;
            public PlannedSample[] samples;
        }

        [Serializable]
        private class WorldTransform
        {
            public float[] position_m;
            public float[] rotation_xyzw;
            public float[] scale_xyz;
        }

        [Serializable]
        private class CameraState
        {
            public float vertical_fov_degrees;
        }

        [Serializable]
        private class LightState
        {
            public float intensity;
        }

        [Serializable]
        private class EntityState
        {
            public string entity_id;
            public WorldTransform world_transform;
            public CameraState camera;
            public LightState light;
        }

        [Serializable]
        private class Sample
        {
            public double time_seconds;
            public EntityState[] entities;
        }

        [Serializable]
        private class CaptureLayer
        {
            public string layer;
            public string status;
        }

        [Serializable]
        private class Provenance
        {
            public string method;
            public string engine_version;
            public string captured_at_utc;
            public bool play_mode;
        }

        [Serializable]
        private class Capture
        {
            public string schema_version = "0.1.0";
            public string kind = "cinetwin.behavior_capture";
            public string cutscene_id;
            public SourceInfo source;
            public List<Sample> samples = new List<Sample>();
            public List<CaptureLayer> capture_layers = new List<CaptureLayer>();
            public List<string> errors = new List<string>();
            public Provenance provenance;
        }

        [MenuItem(MenuPath, priority = 141)]
        private static void CaptureSelectedTimeline()
        {
            var director = SelectedDirector();
            if (!EditorApplication.isPlaying || director == null)
            {
                EditorUtility.DisplayDialog(
                    "CineTwin",
                    "Enter Play Mode and select a GameObject with a Timeline PlayableDirector.",
                    "OK");
                return;
            }

            var planPath = EditorUtility.OpenFilePanel(
                "Choose CineTwin sampling plan", Application.dataPath, "json");
            if (string.IsNullOrEmpty(planPath))
                return;

            try
            {
                var plan = JsonUtility.FromJson<SamplingPlan>(
                    File.ReadAllText(planPath));
                ValidatePlan(plan, director);
                var entities = ResolveEntities(plan.entities, director.gameObject.scene);
                var capture = EvaluateInPlayMode(director, plan, entities);

                var projectRoot = Directory.GetParent(Application.dataPath).FullName;
                var folder = Path.Combine(projectRoot, "CutsceneAI", "Exports");
                Directory.CreateDirectory(folder);
                var filename = SanitizeFileName(director.playableAsset.name)
                    + ".cinetwin.behavior.json";
                var path = Path.Combine(folder, filename);
                File.WriteAllText(path, JsonUtility.ToJson(capture, true));
                Debug.Log("[CineTwin] Source behavior captured: " + path
                    + " (samples=" + capture.samples.Count
                    + ", entities=" + plan.entities.Length + ")");
                EditorUtility.RevealInFinder(path);
            }
            catch (Exception error)
            {
                Debug.LogException(error);
                EditorUtility.DisplayDialog(
                    "CineTwin Capture Failed",
                    error.Message + "\nNo capture has been accepted.",
                    "OK");
            }
            finally
            {
                EditorUtility.ClearProgressBar();
            }
        }

        [MenuItem(MenuPath, validate = true)]
        private static bool ValidateMenu()
        {
            return EditorApplication.isPlaying && SelectedDirector() != null;
        }

        private static PlayableDirector SelectedDirector()
        {
            var selected = Selection.activeGameObject;
            if (selected == null)
                return null;
            var director = selected.GetComponent<PlayableDirector>();
            return director != null && director.playableAsset is TimelineAsset
                ? director : null;
        }

        private static void ValidatePlan(SamplingPlan plan, PlayableDirector director)
        {
            if (plan == null || plan.kind != "cinetwin.sampling_plan"
                || plan.source == null || plan.entities == null
                || plan.entities.Length == 0 || plan.samples == null
                || plan.samples.Length < 2)
            {
                throw new InvalidOperationException(
                    "Invalid or incomplete CineTwin sampling plan.");
            }
            if (plan.source.engine != "unity")
                throw new InvalidOperationException("Plan source engine is not Unity.");

            var timelinePath = AssetDatabase.GetAssetPath(director.playableAsset);
            var expectedRef = plan.source.sequence_ref ?? "";
            if (string.IsNullOrEmpty(timelinePath)
                || !expectedRef.StartsWith(timelinePath + "|", StringComparison.Ordinal))
            {
                throw new InvalidOperationException(
                    "Selected director Timeline does not match the source plan.");
            }

            if (!AssetDatabase.TryGetGUIDAndLocalFileIdentifier(
                    director.playableAsset, out string guid, out long localId)
                || expectedRef.IndexOf("guid=" + guid, StringComparison.OrdinalIgnoreCase) < 0
                || expectedRef.IndexOf("local=" + localId, StringComparison.Ordinal) < 0)
            {
                throw new InvalidOperationException(
                    "Source Timeline GUID/local ID differs from the sampling plan.");
            }

            var previous = double.NegativeInfinity;
            foreach (var sample in plan.samples)
            {
                if (double.IsNaN(sample.time_seconds) || double.IsInfinity(sample.time_seconds)
                    || sample.time_seconds <= previous)
                {
                    throw new InvalidOperationException(
                        "Sampling plan times must be finite and strictly increasing.");
                }
                previous = sample.time_seconds;
            }
        }

        private static Dictionary<string, Transform> ResolveEntities(
            PlannedEntity[] planned, UnityEngine.SceneManagement.Scene scene)
        {
            // Scope to the director's scene, never use an unrelated loaded scene.
            var byId = new Dictionary<string, Transform>(StringComparer.Ordinal);
            var byPath = new Dictionary<string, List<Transform>>(StringComparer.Ordinal);
            foreach (var root in scene.GetRootGameObjects())
            {
                foreach (var transform in root.GetComponentsInChildren<Transform>(true))
                {
                    var id = "unity-object:"
                        + GlobalObjectId.GetGlobalObjectIdSlow(transform.gameObject);
                    if (!byId.ContainsKey(id))
                        byId.Add(id, transform);

                    var path = HierarchyPath(transform);
                    if (!byPath.TryGetValue(path, out var matches))
                    {
                        matches = new List<Transform>();
                        byPath.Add(path, matches);
                    }
                    matches.Add(transform);
                }
            }

            var result = new Dictionary<string, Transform>(StringComparer.Ordinal);
            foreach (var expected in planned)
            {
                if (string.IsNullOrEmpty(expected.entity_id)
                    || result.ContainsKey(expected.entity_id))
                    throw new InvalidOperationException(
                        "Source entity identifiers must be unique and nonempty.");

                if (!byId.TryGetValue(expected.entity_id, out var transform))
                {
                    if (string.IsNullOrEmpty(expected.hierarchy_path)
                        || !byPath.TryGetValue(expected.hierarchy_path, out var matches)
                        || matches.Count != 1)
                    {
                        throw new InvalidOperationException(
                            "Could not uniquely locate source entity: "
                            + expected.entity_id + " / " + expected.hierarchy_path);
                    }
                    transform = matches[0];
                    Debug.LogWarning("[CineTwin] Resolved by unique hierarchy path: "
                        + expected.hierarchy_path);
                }
                result.Add(expected.entity_id, transform);
            }
            return result;
        }

        private static Capture EvaluateInPlayMode(
            PlayableDirector director, SamplingPlan plan,
            Dictionary<string, Transform> entities)
        {
            var capture = new Capture
            {
                cutscene_id = plan.cutscene_id,
                source = plan.source,
                provenance = new Provenance
                {
                    method = "PlayableDirector.Evaluate",
                    engine_version = Application.unityVersion,
                    captured_at_utc = DateTime.UtcNow.ToString("o"),
                    play_mode = true
                }
            };

            var oldTime = director.time;
            var oldMode = director.timeUpdateMode;
            var oldState = director.state;
            var graphAlreadyValid = director.playableGraph.IsValid();
            try
            {
                director.timeUpdateMode = DirectorUpdateMode.Manual;
                if (!graphAlreadyValid)
                    director.RebuildGraph();
                director.Pause();

                for (var index = 0; index < plan.samples.Length; index++)
                {
                    var request = plan.samples[index];
                    director.time = request.time_seconds;
                    director.Evaluate();

                    var sample = new Sample
                    {
                        time_seconds = request.time_seconds,
                        entities = plan.entities.Select(
                            entity => CaptureEntity(
                                entity.entity_id, entities[entity.entity_id])
                        ).ToArray()
                    };
                    capture.samples.Add(sample);

                    if (index % 12 == 0)
                    {
                        EditorUtility.DisplayProgressBar(
                            "CineTwin Behavior Capture",
                            "Evaluating source Timeline at "
                            + request.time_seconds.ToString("F3") + " s",
                            (float)index / plan.samples.Length);
                    }
                }
            }
            finally
            {
                // Restore director playback mode/time. Play Mode scene changes
                // are discarded on exit; we never call SaveScene/SaveAssets.
                director.time = oldTime;
                director.Evaluate();
                director.timeUpdateMode = oldMode;
                if (!graphAlreadyValid)
                    director.Stop();
                else if (oldState == PlayState.Playing)
                    director.Resume();
                else
                    director.Pause();
            }

            capture.capture_layers.Add(new CaptureLayer
                { layer = "world_transform", status = "CAPTURED" });
            capture.capture_layers.Add(new CaptureLayer
                { layer = "camera_state", status = "CAPTURED" });
            capture.capture_layers.Add(new CaptureLayer
                { layer = "light_state", status = "CAPTURED" });
            foreach (var name in new[] {
                "skeletal_pose", "audio_output", "event_execution",
                "rendered_frame", "physics_state" })
            {
                capture.capture_layers.Add(new CaptureLayer
                    { layer = name, status = "NOT_IMPLEMENTED" });
            }
            return capture;
        }

        private static EntityState CaptureEntity(string entityId, Transform transform)
        {
            var p = transform.position;
            var q = transform.rotation;
            var s = transform.lossyScale;
            var state = new EntityState
            {
                entity_id = entityId,
                world_transform = new WorldTransform
                {
                    position_m = new[] { p.x, p.y, -p.z },
                    rotation_xyzw = new[] { -q.x, -q.y, q.z, q.w },
                    scale_xyz = new[] { s.x, s.y, s.z }
                }
            };
            var camera = transform.GetComponent<Camera>();
            if (camera != null)
                state.camera = new CameraState
                    { vertical_fov_degrees = camera.fieldOfView };
            var light = transform.GetComponent<Light>();
            if (light != null)
                state.light = new LightState { intensity = light.intensity };
            return state;
        }

        private static string HierarchyPath(Transform transform)
        {
            var path = transform.name;
            var current = transform.parent;
            while (current != null)
            {
                path = current.name + "/" + path;
                current = current.parent;
            }
            return path;
        }

        private static string SanitizeFileName(string value)
        {
            foreach (var c in Path.GetInvalidFileNameChars())
                value = value.Replace(c, '_');
            return value;
        }
    }
}
