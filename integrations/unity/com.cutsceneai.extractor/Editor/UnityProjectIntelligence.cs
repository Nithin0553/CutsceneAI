using System;
using System.Collections.Generic;
using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;

namespace CutsceneAI.UnityExtractor
{
    internal static class UnityProjectIntelligence
    {
        private const string MenuPath = "Tools/CutsceneAI/Analyze Project";

        [Serializable]
        private sealed class Profile
        {
            public string profile_version = "0.1.0";
            public string profile_id;
            public EngineInfo engine;
            public ProjectInfo project;
            public Conventions conventions;
            public List<Capability> capabilities = new();
            public Settings settings;
            public List<Evidence> evidence = new();
        }

        [Serializable]
        private sealed class EngineInfo
        {
            public string name = "unity";
            public string version;
            public string build;
            public string adapter_name = "cutsceneai.unity";
            public string adapter_version = "0.2.0-dev";
        }

        [Serializable]
        private sealed class ProjectInfo
        {
            public string fingerprint;
            public string project_ref;
            public string platform;
            public List<string> plugins = new();
            public List<string> packages = new();
        }

        [Serializable]
        private sealed class Conventions
        {
            public CoordinateConvention coordinate_system;
            public RotationConvention rotation;
            public CameraConvention camera;
            public AnimationConvention animation;
            public TimingConvention timing;
            public RenderConvention render;
        }

        [Serializable]
        private sealed class CoordinateConvention
        {
            public string handedness = "LEFT_HANDED_NATIVE";
            public string up_axis = "+Y";
            public string forward_axis = "+Z";
            public string right_axis = "+X";
            public string linear_unit = "METER";
        }

        [Serializable]
        private sealed class RotationConvention
        {
            public string representation = "QUATERNION_XYZW_NATIVE";
            public List<string> semantic_fields = new() { "x", "y", "z", "w" };
            public List<string> constructor_argument_order = new() { "x", "y", "z", "w" };
            public string positive_rotation_notes =
                "Extractor converts Unity native rotation into CutSceneAI canonical quaternion.";
        }

        [Serializable]
        private sealed class CameraConvention
        {
            public string fov_axis = "vertical";
            public string forward_axis = "+Z";
            public string up_axis = "+Y";
            public string roll_semantics = "rotation around camera forward axis";
            public string aspect_provenance = "runtime_view_observation_unless_authored";
        }

        [Serializable]
        private sealed class AnimationConvention
        {
            public string root_motion_space = "animator_root_curves_when_present";
            public string root_motion_forward_axis = "+Z native before canonical conversion";
            public string section_completion_model = "TimelineClip extrapolation";
        }

        [Serializable]
        private sealed class TimingConvention
        {
            public string timeline = "UnityEngine.Timeline";
        }

        [Serializable]
        private sealed class RenderConvention
        {
            public string color_space;
            public string render_pipeline;
        }

        [Serializable]
        private sealed class Capability
        {
            public string id;
            public string state;
            public CapabilityDetails details = new();
            public List<string> evidence_ids = new();
        }

        [Serializable]
        private sealed class CapabilityDetails
        {
            public string strategy;
        }

        [Serializable]
        private sealed class Settings
        {
            public string color_space;
            public string render_pipeline;
        }

        [Serializable]
        private sealed class Evidence
        {
            public string evidence_id;
            public string source;
            public string path;
            public string value;
            public double confidence = 1.0;
        }

        [MenuItem(MenuPath, priority = 90)]
        private static void AnalyzeAndWrite()
        {
            var profile = Analyze();
            var projectRoot = Directory.GetParent(Application.dataPath)?.FullName ?? Application.dataPath;
            var outputPath = Path.Combine(projectRoot, "CutSceneAI_ProjectProfile.json");
            File.WriteAllText(outputPath, JsonUtility.ToJson(profile, true));
            Debug.Log($"[CutsceneAI] Project intelligence profile written: {outputPath}");
            EditorUtility.RevealInFinder(outputPath);
        }

        internal static object Analyze()
        {
            var projectRoot = Directory.GetParent(Application.dataPath)?.FullName ?? Application.dataPath;
            var fingerprint = ExtractorUtilities.ProjectFingerprint();
            var renderPipeline = GraphicsSettings.currentRenderPipeline == null
                ? "BuiltIn"
                : GraphicsSettings.currentRenderPipeline.GetType().FullName;

            var profile = new Profile
            {
                profile_id = "unity:" + ExtractorUtilities.Sha256(fingerprint).Substring(0, 24),
                engine = new EngineInfo
                {
                    version = Application.unityVersion,
                    build = Application.unityVersion,
                },
                project = new ProjectInfo
                {
                    fingerprint = fingerprint,
                    project_ref = projectRoot.Replace('\\', '/'),
                    platform = Application.platform.ToString(),
                },
                conventions = new Conventions
                {
                    coordinate_system = new CoordinateConvention(),
                    rotation = new RotationConvention(),
                    camera = new CameraConvention(),
                    animation = new AnimationConvention(),
                    timing = new TimingConvention(),
                    render = new RenderConvention
                    {
                        color_space = QualitySettings.activeColorSpace.ToString(),
                        render_pipeline = renderPipeline,
                    },
                },
                settings = new Settings
                {
                    color_space = QualitySettings.activeColorSpace.ToString(),
                    render_pipeline = renderPipeline,
                },
            };

            profile.evidence.Add(new Evidence
            {
                evidence_id = "source.engine_version",
                source = "Application.unityVersion",
                value = Application.unityVersion,
            });
            profile.evidence.Add(new Evidence
            {
                evidence_id = "source.coordinate_basis",
                source = "unity.engine_contract",
                value = "LH native: +Y up, +Z forward, +X right; extractor canonicalizes to RH +Y/-Z/+X",
            });
            profile.evidence.Add(new Evidence
            {
                evidence_id = "source.camera_basis",
                source = "unity.camera_contract",
                value = "+Z forward, +Y up",
            });
            profile.evidence.Add(new Evidence
            {
                evidence_id = "source.camera_roll",
                source = "cutscene_extraction_required",
                value = "per-camera authored roll must be extracted from source transform",
                confidence = 0.5,
            });
            profile.evidence.Add(new Evidence
            {
                evidence_id = "source.camera_fov_axis",
                source = "UnityEngine.Camera.fieldOfView",
                value = "vertical",
            });

            profile.capabilities.Add(new Capability
            {
                id = "rotation.canonical_quaternion",
                state = "SUPPORTED",
                details = new CapabilityDetails { strategy = "ExtractorUtilities.CanonicalRotation" },
                evidence_ids = new List<string> { "source.coordinate_basis" },
            });
            profile.capabilities.Add(new Capability
            {
                id = "camera.forward_up_basis",
                state = "SUPPORTED",
                details = new CapabilityDetails { strategy = "Unity camera transform basis" },
                evidence_ids = new List<string> { "source.camera_basis" },
            });
            profile.capabilities.Add(new Capability
            {
                id = "camera.vertical_fov",
                state = "SUPPORTED",
                details = new CapabilityDetails { strategy = "Camera.fieldOfView" },
                evidence_ids = new List<string> { "source.camera_fov_axis" },
            });
            profile.capabilities.Add(new Capability
            {
                id = "animation.root_motion_curves",
                state = "CONDITIONAL",
                details = new CapabilityDetails { strategy = "RootT curves when present in AnimationClip" },
            });

            return profile;
        }
    }
}
