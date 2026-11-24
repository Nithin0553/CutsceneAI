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
using CutSceneAI.CineTwin;

namespace CutsceneAI.UnityExtractor
{
    [InitializeOnLoad]
    internal static class CutsceneAIStudioBridge
    {
        private const string Preference = "CutsceneAI.StudioBridge.SourceReadOnlyEnabled";
        private const string Kind = "cutsceneai.unity.source_bridge";
        private const string Action = "EXPORT_SELECTED_TIMELINE_AND_CENSUS";
        private const string CaptureAction = "CAPTURE_SELECTED_TIMELINE_BEHAVIOR";
        private const string EnableMenu = "Tools/CutsceneAI/Studio Bridge/Enable Source Bridge";
        private const string DisableMenu = "Tools/CutsceneAI/Studio Bridge/Disable Source Bridge";
        private const string HeartbeatFile = "unity-editor.json";
        private static double _nextPoll;
        private static string _lastPresenceError = "";

        // EditorPrefs are shared across all projects installed on a workstation.
        // Derive an opt-in key from the exact Unity project root so enabling one
        // editor never silently authorizes another project's source extraction.
        private static string PreferenceKey()
        {
            var root = Path.GetFullPath(Root()).TrimEnd(
                Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
#if UNITY_EDITOR_WIN
            root = root.ToUpperInvariant();
#endif
            using (var sha = SHA256.Create())
            {
                var digest = sha.ComputeHash(System.Text.Encoding.UTF8.GetBytes(root));
                return Preference + "." +
                    BitConverter.ToString(digest).Replace("-", "").ToLowerInvariant();
            }
        }

        [Serializable]
        private sealed class Heartbeat
        {
            public string kind = "cutsceneai.unity.editor_presence";
            public string schema_version = "1";
            public string project_root;
            public string heartbeat;
            public int editor_pid;
            public bool source_bridge_enabled;
            public string editor_mode;
            public string bridge_version = "unity-editor-v0.3";
        }

        // Every assembly/domain reload re-runs InitializeOnLoad and registers
        // the polling callback again. EditorPrefs retains explicit opt-in.
        private static void PresenceError(Exception error)
        {
            // Do not flood Unity Console every 0.7 seconds when a project is
            // read-only, locked or its heartbeat file cannot be replaced.
            var reason = error.GetType().Name + ": " + error.Message;
            if (reason == _lastPresenceError)
                return;
            _lastPresenceError = reason;
            Debug.LogWarning("[CutSceneAI] Source bridge heartbeat write failed for " +
                             "the current Unity project: " + reason +
                             ". Check project folder permissions and the StudioBridge directory.");
        }

        private static bool WritePresence(bool enabled)
        {
            try
            {
                var root = Root();
                var bridge = Path.Combine(root, "CutSceneAI", "StudioBridge");
                Directory.CreateDirectory(bridge);
                var target = Path.Combine(bridge, HeartbeatFile);
                // A unique staging path prevents a prior failed write or
                // second editor process from colliding with this heartbeat.
                var temporary = target + "." + Guid.NewGuid().ToString("N") + ".tmp";
                var payload = new Heartbeat
                {
                    project_root = Path.GetFullPath(root),
                    heartbeat = DateTime.UtcNow.ToString("o"),
                    editor_pid = System.Diagnostics.Process.GetCurrentProcess().Id,
                    source_bridge_enabled = enabled,
                    editor_mode = EditorApplication.isPlaying ? "PLAY_MODE" : "EDIT_MODE",
                };
                try
                {
                    File.WriteAllText(temporary, JsonUtility.ToJson(payload, true));
                    // Windows readers may briefly hold the destination without
                    // FileShare.Delete. Retry only a bounded sharing conflict;
                    // never truncate the visible heartbeat or delete it first.
                    for (var attempt = 0; attempt < 4; attempt++)
                    {
                        try
                        {
                            if (File.Exists(target))
                                File.Replace(temporary, target, null);
                            else
                                File.Move(temporary, target);
                            _lastPresenceError = "";
                            return true;
                        }
                        catch (IOException) when (attempt < 3)
                        {
                            System.Threading.Thread.Sleep(25 * (attempt + 1));
                        }
                    }
                    return false; // Unreachable: the fourth attempt propagates.
                }
                finally
                {
                    // Only remove this invocation's own staging file. Never
                    // delete an existing/last-good heartbeat on any failure.
                    try
                    {
                        if (File.Exists(temporary))
                            File.Delete(temporary);
                    }
                    catch (IOException) { }
                    catch (UnauthorizedAccessException) { }
                }
            }
            catch (IOException ex)
            {
                PresenceError(ex);
            }
            catch (UnauthorizedAccessException ex)
            {
                PresenceError(ex);
            }
            return false;
        }

        [Serializable]
        private sealed class Request
        {
            public string kind;
            public string schema_version;
            public string request_id;
            public string action;
            public string source_request_id;
            public string source_csir_sha256;
            public string plan_path;
            public string plan_sha256;
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
            public string capture_path;
            public string capture_sha256;
            public string plan_sha256;
        }

        static CutsceneAIStudioBridge()
        {
            EditorApplication.update += Poll;
        }

        [MenuItem(EnableMenu, priority = 120)]
        private static void Enable()
        {
            EditorPrefs.SetBool(PreferenceKey(), true);
            if (WritePresence(true))
                Debug.Log("[CutSceneAI] Opt-in source bridge enabled for this Unity project; " +
                          "reconnects automatically after script reload.");
            else
                Debug.LogError("[CutSceneAI] Source bridge was enabled but its heartbeat " +
                               "could not be written. Studio cannot connect until the " +
                               "Unity project folder is writable.");
        }

        [MenuItem(DisableMenu, priority = 121)]
        private static void Disable()
        {
            EditorPrefs.SetBool(PreferenceKey(), false);
            WritePresence(false);
            Debug.Log("[CutSceneAI] Source bridge disabled. No queued request will run.");
        }

        [MenuItem(EnableMenu, validate = true)]
        private static bool CanEnable() { return !EditorPrefs.GetBool(PreferenceKey(), false); }

        [MenuItem(DisableMenu, validate = true)]
        private static bool CanDisable() { return EditorPrefs.GetBool(PreferenceKey(), false); }

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

        private static PlayableDirector ResolveSourceDirector()
        {
            var selected = Selection.activeGameObject;
            var selectedDirector = selected == null ? null : selected.GetComponent<PlayableDirector>();
            if (selectedDirector != null)
            {
                if (!(selectedDirector.playableAsset is TimelineAsset) ||
                    !selectedDirector.gameObject.scene.isLoaded ||
                    string.IsNullOrEmpty(selectedDirector.gameObject.scene.path))
                    throw new InvalidOperationException(
                        "Selected director is not a Timeline in a saved, loaded Unity scene.");
                return selectedDirector;
            }

            PlayableDirector only = null;
            foreach (var director in Resources.FindObjectsOfTypeAll<PlayableDirector>())
            {
                if (director == null || !(director.playableAsset is TimelineAsset) ||
                    !director.gameObject.scene.isLoaded ||
                    string.IsNullOrEmpty(director.gameObject.scene.path))
                    continue;
                if (only != null)
                    throw new InvalidOperationException(
                        "Multiple saved Timelines are loaded. Select the intended PlayableDirector " +
                        "in Unity before pressing Transfer; no cutscene was guessed.");
                only = director;
            }
            if (only == null)
                throw new InvalidOperationException(
                    "No playable Timeline found in a saved loaded Unity scene. " +
                    "Open the cutscene scene in Unity Editor before pressing Transfer.");
            return only;
        }

        private static void Poll()
        {
            if (!EditorPrefs.GetBool(PreferenceKey(), false) ||
                EditorApplication.isCompiling || EditorApplication.isUpdating)
                return;
            if (EditorApplication.timeSinceStartup < _nextPoll)
                return;
            _nextPoll = EditorApplication.timeSinceStartup + 0.7;
            var bridge = Path.Combine(Root(), "CutSceneAI", "StudioBridge");
            // Emits a project-bound heartbeat even if there are no requests.
            // The host can show reconnection after Unity domain reload without
            // opening/restarting the Editor or executing an old request twice.
            if (!WritePresence(true))
                return;  // No source export while its connection is undetectable.
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
                        request.request_id != requestId ||
                        (request.action != Action && request.action != CaptureAction))
                        throw new InvalidOperationException("Unsupported source bridge request.");

                    // Structural exports must originate from the saved Edit Mode
                    // scene. A behavior request waits for an *already running*
                    // Play Mode; Studio never starts user scripts by silently
                    // entering Play Mode or saves the runtime-modified scene.
                    if (request.action == Action && EditorApplication.isPlayingOrWillChangePlaymode)
                    {
                        processed--;
                        continue;
                    }
                    if (request.action == CaptureAction && !EditorApplication.isPlaying)
                    {
                        processed--;
                        continue;
                    }
                    var evidence = Path.Combine(bridge, "evidence");
                    Directory.CreateDirectory(evidence);
                    if (request.action == Action)
                    {
                        var director = ResolveSourceDirector();
                        var export = UnityTimelineExtractor.Export(director);
                        UnityTimelineOffsetAugmenter.Augment(export, director);
                        var snapshot = Path.Combine(evidence, requestId + ".csir.json");
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
                    else
                    {
                        receipt.plan_sha256 = request.plan_sha256;
                        if (string.IsNullOrEmpty(request.source_request_id) ||
                            !Regex.IsMatch(request.source_request_id, "^[0-9a-f]{32}$"))
                            throw new InvalidOperationException("Invalid source snapshot identity.");
                        var sourceReceiptPath = Path.Combine(
                            receipts, request.source_request_id + ".json");
                        if (!File.Exists(sourceReceiptPath))
                            throw new InvalidOperationException("Source snapshot receipt is missing.");
                        var original = JsonUtility.FromJson<Receipt>(File.ReadAllText(sourceReceiptPath));
                        if (original == null || original.kind != Kind ||
                            original.request_id != request.source_request_id ||
                            original.status != "SUCCEEDED" ||
                            original.csir_sha256 != request.source_csir_sha256)
                            throw new InvalidOperationException("Source snapshot receipt has changed.");
                        var snapshotRel = "CutSceneAI/StudioBridge/evidence/" +
                            request.source_request_id + ".csir.json";
                        if (original.csir_path != snapshotRel ||
                            Sha256(Path.Combine(evidence,
                                request.source_request_id + ".csir.json")) != original.csir_sha256)
                            throw new InvalidOperationException("Source CSIR hash no longer matches.");

                        var expectedPlan = "CutSceneAI/StudioBridge/evidence/" +
                            requestId + ".cinetwin.sampling-plan.json";
                        var plan = Path.Combine(evidence, requestId + ".cinetwin.sampling-plan.json");
                        if (request.plan_path != expectedPlan || !File.Exists(plan) ||
                            Sha256(plan) != request.plan_sha256)
                            throw new InvalidOperationException("CineTwin plan hash or location mismatch.");
                        var director = ResolveSourceDirector();
                        var output = Path.Combine(evidence, requestId + ".cinetwin.behavior.json");
                        CineTwinBehaviorCapture.CaptureForStudio(director, plan, output);
                        receipt.capture_path = RelativeToRoot(output);
                        receipt.capture_sha256 = Sha256(output);
                        receipt.status = "SUCCEEDED";
                        Debug.Log("[CutSceneAI] Unity Play Mode CineTwin evidence saved: " +
                                  requestId + ". Native Unreal comparison remains pending.");
                    }
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
