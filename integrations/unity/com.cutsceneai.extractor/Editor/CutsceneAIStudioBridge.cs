// Opt-in, file-queue Unity Editor companion for CutSceneAI Studio.
// It only reads the currently selected saved Timeline and the project's source
// capability census; no user-provided code, scene mutation or shell commands.
using System;
using System.IO;
using System.Security.Cryptography;
using System.Text.RegularExpressions;
using UnityEditor;
using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.Timeline;

namespace CutsceneAI.UnityExtractor
{
    [InitializeOnLoad]
    internal static class CutsceneAIStudioBridge
    {
        private const string Preference = "CutsceneAI.StudioBridge.SourceReadOnlyEnabled";
        private const string Kind = "cutsceneai.unity.source_bridge";
        private const string Action = "EXPORT_SELECTED_TIMELINE_AND_CENSUS";
        private const string EnableMenu = "Tools/CutsceneAI/Studio Bridge/Enable Source Bridge";
        private const string DisableMenu = "Tools/CutsceneAI/Studio Bridge/Disable Source Bridge";
        private static double _nextPoll;

        [Serializable]
        private sealed class Request
        {
            public string kind;
            public string schema_version;
            public string request_id;
            public string action;
        }

        [Serializable]
        private sealed class Receipt
        {
            public string kind = Kind;
            public string schema_version = "1";
            public string request_id;
            public string status;
            public string reason;
            public string csir_path;
            public string csir_sha256;
            public string census_path;
            public string census_sha256;
        }

        static CutsceneAIStudioBridge()
        {
            EditorApplication.update += Poll;
        }

        [MenuItem(EnableMenu, priority = 120)]
        private static void Enable()
        {
            EditorPrefs.SetBool(Preference, true);
            Debug.Log("[CutSceneAI] Opt-in source bridge enabled for the current Unity Editor.");
        }

        [MenuItem(DisableMenu, priority = 121)]
        private static void Disable()
        {
            EditorPrefs.SetBool(Preference, false);
            Debug.Log("[CutSceneAI] Source bridge disabled. No queued request will run.");
        }

        [MenuItem(EnableMenu, validate = true)]
        private static bool CanEnable() { return !EditorPrefs.GetBool(Preference, false); }

        [MenuItem(DisableMenu, validate = true)]
        private static bool CanDisable() { return EditorPrefs.GetBool(Preference, false); }

        private static string Root()
        {
            return Directory.GetParent(Application.dataPath).FullName;
        }

        private static string Sha256(string path)
        {
            using (var sha = SHA256.Create())
            using (var stream = File.OpenRead(path))
                return BitConverter.ToString(sha.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        }

        private static string RelativeToRoot(string absolutePath)
        {
            var root = Path.GetFullPath(Root()).TrimEnd(Path.DirectorySeparatorChar) +
                Path.DirectorySeparatorChar;
            var full = Path.GetFullPath(absolutePath);
            if (!full.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Export escaped the selected Unity project.");
            return full.Substring(root.Length).Replace('\\', '/');
        }

        private static void Poll()
        {
            if (!EditorPrefs.GetBool(Preference, false) ||
                EditorApplication.isCompiling || EditorApplication.isUpdating ||
                EditorApplication.isPlayingOrWillChangePlaymode)
                return;
            if (EditorApplication.timeSinceStartup < _nextPoll)
                return;
            _nextPoll = EditorApplication.timeSinceStartup + 0.7;
            var bridge = Path.Combine(Root(), "CutSceneAI", "StudioBridge");
            var requests = Path.Combine(bridge, "requests");
            if (!Directory.Exists(requests))
                return;
            var receipts = Path.Combine(bridge, "receipts");
            Directory.CreateDirectory(receipts);
            var paths = Directory.GetFiles(requests, "*.json");
            Array.Sort(paths, StringComparer.Ordinal);
            // Bound work per Editor update to keep editor interaction responsive.
            var processed = 0;
            for (var i = 0; i < paths.Length && processed < 6; i++)
            {
                var requestId = Path.GetFileNameWithoutExtension(paths[i]);
                if (!Regex.IsMatch(requestId, "^[0-9a-f]{32}$"))
                    continue;
                var target = Path.Combine(receipts, requestId + ".json");
                if (File.Exists(target))
                    continue;
                // Completed requests must not starve newer requests forever.
                processed++;
                var receipt = new Receipt { request_id = requestId, status = "BLOCKED" };
                try
                {
                    if (new FileInfo(paths[i]).Length > 4096)
                        throw new InvalidOperationException("Request is oversized.");
                    var request = JsonUtility.FromJson<Request>(File.ReadAllText(paths[i]));
                    if (request == null || request.kind != Kind || request.schema_version != "1" ||
                        request.request_id != requestId || request.action != Action)
                        throw new InvalidOperationException("Unsupported source bridge request.");

                    var selected = Selection.activeGameObject;
                    var director = selected == null ? null : selected.GetComponent<PlayableDirector>();
                    if (director == null || !(director.playableAsset is TimelineAsset) ||
                        string.IsNullOrEmpty(director.gameObject.scene.path))
                        throw new InvalidOperationException(
                            "Select a saved scene GameObject containing a PlayableDirector with a TimelineAsset.");

                    var export = UnityTimelineExtractor.Export(director);
                    UnityTimelineOffsetAugmenter.Augment(export, director);
                    var evidence = Path.Combine(bridge, "evidence");
                    Directory.CreateDirectory(evidence);
                    var snapshot = Path.Combine(evidence, requestId + ".csir.json");
                    // CreateNew prevents stale or maliciously pre-existing snapshots being overwritten.
                    using (var input = File.OpenRead(export))
                    using (var output = new FileStream(snapshot, FileMode.CreateNew, FileAccess.Write))
                        input.CopyTo(output);
                    var census = CutSceneAIFeatureSurfaceScanner.ExportCensus();
                    receipt.csir_path = RelativeToRoot(snapshot);
                    receipt.csir_sha256 = Sha256(snapshot);
                    receipt.census_path = RelativeToRoot(census);
                    receipt.census_sha256 = Sha256(census);
                    receipt.status = "SUCCEEDED";
                    Debug.Log("[CutSceneAI] Source bridge recorded CSIR + census: " + requestId +
                              ". Fidelity remains unverified.");
                }
                catch (Exception ex)
                {
                    receipt.reason = ex.GetType().Name + ": " + ex.Message;
                    Debug.LogWarning("[CutSceneAI] Source bridge blocked: " + receipt.reason);
                }
                // Never overwrite a previously recorded outcome, even after an Editor restart.
                using (var stream = new FileStream(target, FileMode.CreateNew, FileAccess.Write))
                using (var writer = new StreamWriter(stream))
                    writer.Write(JsonUtility.ToJson(receipt, true));
            }
        }
    }
}
