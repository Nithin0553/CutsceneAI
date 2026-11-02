# Studio integrated branch — Issue #93 acceptance and smoke test

**Branch:** `integrate/studio-issue-93`  
**Review PR:** #102 (draft, base `feature/ced-adapter-execution`)  
**Status:** Source-level integration, not a certified Unity/Unreal runtime release.

## Integration map

The branch starts from `feature/ced-adapter-execution` (PR #92), which contains
the CED registry (PR #91), release safeguards (PR #89), opt-in LangGraph graph
(PR #88) and one-click Studio UI (PR #87), as well as its underlying Studio
UI/transfer plumbing. The source-scoped Unity exporter and asset work from
PR #90 is integrated on top.

For PR #90, 16 non-conflicting modified files are imported **unchanged** and
verified against their PR #90 blob IDs. The only overlapping file,
`packages/studio/transfer_backend.py`, has both PR #90's
`source_scope_matched` guard and PR #92's executable CED handler
`plan_for`/prepared-plan logic. The merge did **not** overwrite the newer
CED dispatcher with older transfer planner code.

Earlier research PRs (#49, #50, #52 and #75–#83) were reviewed by
changed-file scope to avoid reintroducing older builder behavior. This
integration branch already has a byte-identical `case_memory.py` to PR #50,
`asset_staging.py` to PR #82, `ced_discovery_registry.py` to PR #91,
and `root_world_lock.py`, `cinetwin_root_world_lock.py` and
`diagnose_cinetwin_parity.py` matching PR #83. Other shared files,
especially `build_level_sequence.py`, `transfer_backend.py`,
`prepared_transfer.py` and `ced_preflight.py`, evolved in later Studio
branches and are **not** byte-identical to their older experimental heads.
They must be compared and exercised, not wholesale overwritten by PR #83
or earlier PRs. The unfinished held-out runtime/rig/camera behavior from
PR #83 belongs under Issues #96–#98; learning claims from PR #50 belong
under #100. **PRs and user engine assets remain untouched.**

## Code acceptance

From a clone of this integration branch:

```powershell
git fetch origin
git switch integrate/studio-issue-93
git pull origin integrate/studio-issue-93
python -m pip install pytest ruff jsonschema "langgraph>=1.0,<2"
python -m compileall -q packages tools integrations/unreal
python -m pytest -q
node --check apps/studio-web/app.js
node --check apps/studio-web/cinematic.js
node tests/studio/test_cinematic_ui.cjs
python -m ruff check tests
python tools/repo_check.py
```

Report the exact commit, test counts, skipped tests and CI URL. The
`tests/studio/test_source_surface_gap.py` and
`tests/studio/test_feature_dispatch_v02.py` suites must pass **together**
with material/asset staging, UI, LangGraph, worker, persistence and release
gate tests. Tests that mock Unity or Unreal API do **not** certify real-editor
integration.

## Real Windows Unity → Unreal smoke test (manual engine acceptance)

1. Back up the entire Unreal project and keep the original Unity project
   unchanged. Use a new/isolated Unreal staging project or a fresh saved map;
   preserve frozen Benchmark001 and prior Benchmark002 experiments.
2. In the *actual Unity Editor*, install/update the extractor from
   `integrations/unity/com.cutsceneai.extractor` if required by the project.
   Open the user-selected existing cutscene Timeline and use
   **Tools → CutsceneAI → Export Selected Timeline**, then run
   **Discover Installed Feature Surface**. A current matching CSIR/census is
   required; older exported JSONs may lack model/material GUIDs.
3. Confirm that the source model paths, renderer GUIDs/material albedo IDs,
   GameObject Transform scope and native component census match the exact
   source project. Unresolved Unity components must remain explicit;
   a clean structural export is *not* proof of engine behavior.
4. Open the **backed-up target Unreal project** in the actual Unreal Editor.
   Launch Studio from the repository root with
   `powershell -ExecutionPolicy Bypass -File .\tools\start_studio.ps1`.
   In the browser open `http://127.0.0.1:8765`. Use the native project
   selection workflow to choose the correct Unity project and Unreal project.
5. Leave **Enable AI agents unchecked** for the baseline experiment.
   Approve source-asset-copy permissions, select the exported cutscene and
   connect the projects. On **Start Transfer**, inspect the candidate
   readiness, CED unknowns, asset manifest and generated stage.
   Where Studio instructs you, use the exact **Unreal companion command
   shown in the UI** in Unreal's Python Console, with the selected map
   loaded; avoid running arbitrary or stale editor commands.
6. Inspect the generated editable Level Sequence, imported native asset
   classes, source-mapped actors, camera tracks, animation clips, hierarchy,
   materials, light actors, audio and expected timeline duration. A transfer
   that reports `GENERATED_UNVERIFIED` is **not** a fidelity pass.
7. Save the staged level and sequence. Close the Unreal Editor, open a fresh
   Unreal Editor process, reload the same map and sequence, and run the
   Studio native persistence/hierarchy/visual audit. Check actual source-
   to-target CineTwin behavior observations at matching timestamps when
   available; do not substitute static plan comparisons for samples.
8. In the repo terminal, run `python tools/studio_release_audit.py`.
   Preserve the JSON gate and receipts from
   `~/.cutsceneai-studio/runs/candidates/`. The command exits 2 for
   missing/failed evidence; that is an honest **not release ready** result.
9. To evaluate the **optional** AI path, start a *separate fresh* staging
   candidate, configure `OPENAI_API_KEY` in the same Studio terminal and
   install `openai>=2,<3`, check **Enable AI agents**, and repeat.
   Check that the ordinary converter still runs first; LangGraph must
   diagnose only if gaps remain. Capture exact selected repair,
   evidence-bound native request, one-time receipt, re-audit and stop
   condition. A model call may cost money. Never publish the key.
10. Repeat on a different Unity cutscene/project for generalization.
    Unmapped URP/shader, collider, activation-signal runtime, custom scripts,
    skeleton retargeting, visual-frame or audio waveform behavior must be
    reported as unsupported/incomplete unless a proven adapter and actual
    source-target acceptance exist.

## Minimum result record

Record one row per source cutscene and test mode: integrated commit, source
CSIR hash, census hash, engine versions, destination project/level,
`ai_agents_enabled`, native asset count, sequence path, saved native
readback, behavior metric/threshold and confidence, unsupported CED
occurrences, final fidelity status, interrupted/restart status, release
gate output and logs/receipts.

**Exit rule:** Issue #93 can be closed after one integrated code line passes
all automated checks and a real backed-up Unity/Unreal smoke test confirms
the documented *supported scope* and no destructive regression. It does not
imply the separate conversion, fidelity, learning and release issues
#94–#101 are complete.
