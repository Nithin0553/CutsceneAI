# Studio: selecting Unity CSIR and Source Census for each transfer

Studio no longer silently selects the first or newest Unity Source Census.

## User workflow

1. Export the selected Unity Timeline to CSIR using
   **Tools → CutsceneAI → Export Selected Timeline**.
2. In Unity, run **Tools → CutsceneAI → Discover Installed Feature Surface**
   to produce a fresh Source Census in `CutSceneAI/Exports`.
3. Start CutSceneAI Studio and select the Unity and Unreal projects.
4. Choose the **Unity CSIR Export** in the dropdown. Each option includes
   the exported filename, even when cutscene names repeat. Choose the
   destination Unreal level.
5. Click **Connect Projects**. Studio now lists the Source Census files
   whose Unity project identity and cutscene scene/object scope match that
   exact connected CSIR. Incompatible census exports are excluded from
   the dropdown, not silently accepted.
6. Select the **Unity Source Census** you want for THIS transfer. The
   selection displays the filename and unresolved/partial source counts.
   Studio will not start until you make a choice. A census with unresolved
   features can only be used under explicit, labelled best-effort mode;
   a matched census is *not* full Unreal fidelity evidence.
7. Click **Start Transfer**. Studio rechecks that the selected census
   still exists and matches the exact CSIR. If it was removed, overwritten
   with incompatible source data, or becomes invalid, preparation stops
   without selecting another census behind your back.
8. After exporting newer files while Studio is open, choose
   **Refresh CSIR & Census exports**. Select the desired CSIR; if it
   differs from the connected CSIR (or the destination level changes),
   click **Reconnect Projects** and then select the new matching census.
   A finished transfer also requires reconnecting for a fresh candidate.
9. Continue with the normal/optional-agent transfer. Each approved
   candidate records the source census path in its immutable mapping
   and plan; approval remains source/project/candidate-specific.

## Guarantees and limitations

- Explicit choice: no automatic newest-census fallback in the UI.
- Backend only accepts census exports under the connected Unity project,
  with identity and cutscene scope proved by the scanner.
- Selection is per connection/transfer, rather than a global preference
  that could accidentally apply to another Unity cutscene.
- Unknown source features are reported; choosing a census does not
  grant Unreal adapters or claim cross-engine fidelity.
- CSIR discovery requires an actual Unity extractor export, not a raw
  .unity scene or .playable asset. The Studio scans exported files from
  the chosen Unity project and cannot browse unrelated/unsafe paths.
- The Source Census scanner currently examines up to its configured
  recent-export limit. Click Refresh after generating a new export.

Tests: `node tests/studio/test_cinematic_ui.cjs`,
`python -m pytest tests/studio/test_studio_ui_feature_integration.py`.
Actual Unity and Unreal Editor behavior remains a separate acceptance test.
