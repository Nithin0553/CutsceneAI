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


## Project selection layout and startup behavior

- The project form places **Unity CSIR Export** and **Unreal Destination Level**
  in two separate columns. **Unity Source Census** uses a dedicated full-width
  panel, including source warnings and explanatory text. The refresh control
  occupies its own row. On smaller screens the selectors stack vertically;
  paths remain readable and cannot shrink the button or other labels.
- Every **new Studio browser session or page reload opens Home**, even if the
  server still has an older result or active transfer. Opening Home does not
  destroy or overwrite the saved candidate, native evidence or job.
- On Home, **View Previous Transfer Report** opens a previously completed
  result; **View Active Transfer** resumes an existing running transfer.
  **Start Transfer** leads to project connection/selection. A fresh transfer
  still requires a new connection and a source-census choice.
- Source identity mismatches are never hidden to improve appearance.
  If no matching Source Census is available, re-export in Unity,
  refresh exports and reconnect to the desired CSIR.


## Start Transfer appears disabled after a previous attempt

An older UI build restored `state.running=true` whenever an earlier
one-click-approved candidate matched the connected CSIR, **even when no
Unreal job had been queued**. It then disabled **Start Transfer** without
explaining why. The folder, census and source-permission selectors could
all show valid choices, as in the 2026-11-09 screenshot.

Studio now distinguishes three situations:

- **Ready and no pending candidate:** `Start Transfer` is enabled when
  you have selected the matching source census and confirmed import rights.
- **An earlier candidate was approved but never submitted:** the UI shows
  `Start New Transfer` with a clear explanation. This **reconnects the
  same project pair**, uses the same CSIR and revalidates the selected
  Source Census, then prepares and submits an entirely **new** candidate.
  It clears active pointers but never deletes the earlier candidate files,
  modifies source Unity assets, or replays an old Unreal job.
- **A job is genuinely queued/running:** the UI displays
  `View Active Transfer` instead of leaving a disabled Start button.
  The existing Unreal job must be inspected rather than automatically
  submitting another one. A completed or failed job still requires
  reconnection before a fresh candidate can be created.

If the selected source census disappears or changes after clicking
`Start New Transfer`, Studio aborts before preparation; it never falls
back to a different census silently. An active Unreal job appearing
during reconnection also blocks via the server's existing safety rule.

These are UI/state handling fixes with simulated browser tests. Fresh
Unity/Unreal Editor acceptance is still required.
