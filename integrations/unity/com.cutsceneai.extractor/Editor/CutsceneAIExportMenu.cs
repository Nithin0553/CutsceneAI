using System;
using UnityEditor;
using UnityEngine;
using UnityEngine.Playables;
using UnityEngine.Timeline;

namespace CutsceneAI.UnityExtractor
{
    internal static class CutsceneAIExportMenu
    {
        private const string MenuPath = "Tools/CutsceneAI/Export Selected Timeline";

        [MenuItem(MenuPath, priority = 100)]
        private static void ExportSelectedTimeline()
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
                var outputPath = UnityTimelineExtractor.Export(director);
                Debug.Log($"[CutsceneAI] Timeline exported to: {outputPath}");
                EditorUtility.RevealInFinder(outputPath);
            }
            catch (Exception exception)
            {
                Debug.LogException(exception);
                EditorUtility.DisplayDialog("CutsceneAI Export Failed", exception.Message, "OK");
            }
        }

        [MenuItem(MenuPath, validate = true)]
        private static bool ValidateExportSelectedTimeline()
        {
            return GetSelectedDirector() != null;
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
    }
}
