# Adaptive CED plan (29) vs stale Unreal planner (25) — source-safe recovery

## Symptom

Studio Review prepares a **29-action** Benchmark002 candidate (the 25 base
actions plus four source-census-adaptive Unreal property actions). After
clicking Generate, the Transfer execution report says:

```text
transfer-plan.json differs materially from source-derived JSON at
$.actions: length observed=29, recomputed=25.
```

Generation remains `NOT_STARTED`. A safe readiness check may show 0/10
actors and 0/5 required mapped assets, with an automatic import plan for
18 source files. A green readiness badge does not establish execution.

## Root cause

Unreal Editor runs a **persistent Python interpreter**. Updating GitHub and
restarting Studio alone does **not** reload modules already imported inside
Unreal. An older cached `transfer_backend` or `prepared_transfer`
recomputes the original 25-action CSIR-only plan against a newer
29-action CED+Unity-census prepared artifact. The independent immutable
plan verification correctly blocks mutation; **do not delete or bypass it**.

## Fix committed

1. `integrations/unreal/studio_planner_sync.py` pins and reloads the
   canonical on-disk planner modules in dependency order, checks for shadowed
   module origins, and never alters a candidate or project.
2. The editor worker runs synchronization **before**
   `prepared_transfer.verify()`, before automatic setup/imports and before
   level/sequence mutations.
3. Direct `build_prepared_files()` synchronization repeats the same
   check before its independent plan recomputation.
4. The new heartbeat requires `studio-editor-v0.5` for connected Unity
   automatic transfers. Older Unreal sessions must restart before queueing,
   rather than failing after the job begins.
5. Regression test `tests/studio/test_studio_planner_sync.py` simulates a
   stale 25-action Python module and verifies it refreshes from the current
   repository. Full CI also runs the existing adaptive planner regression.

This fix keeps the exact plan-content, source-hash, and provenance checks.

## Recovery steps (Windows)

1. Save any other Unreal work and fully **exit Unreal Editor**. Do not reuse
   or regenerate the blocked candidate and do not delete its audit artifacts.
2. Stop the old Studio local server (Ctrl+C).
3. In the original repository:

   ```powershell
   cd "B:\Research\CutSceneAI\CutsceneAI"
   git switch feature/studio-ui-connected-v0.3
   git pull origin feature/studio-ui-connected-v0.3
   python tools/studio_local_bridge.py
   ```

4. Start Unreal fresh with the previously selected **saved empty target
   level**. It may be reused if the old attempt truly imported no assets,
   created no actors and did not create its sequence; otherwise use a new
   backed-up empty level. Start the editor companion using the currently
   displayed Python command, not an old console history command.
5. In Studio Review, keep the newest property-bearing Unity feature census
   selected. Strict mode may remain off for this clearly labelled
   best-effort Benchmark002 regression. Click **Prepare transfer plan** to
   get a new immutable candidate ID, sequence path and plan.
6. Verify the Review action total (29 in this observed source case) and
   adaptive component decision rows. Then proceed to Transfer. Check for
   connected v0.5 companion, correct target project and empty level.
7. Generate **once**. Stop if real import partially succeeds and generation
   fails, and investigate that candidate's immutable receipt; never replay
   blindly.
8. Save All, close/reopen Unreal, and run real persistence/hierarchy audits.
   CineTwin behavioral parity remains a separate evaluation.

## Boundaries

The regression tests demonstrate that the editor uses the refreshed source
planner before mutation. They are not a substitute for running the new
29-action candidate in Unreal 5.8.3. Four **planned** native adaptive actions
must still be independently verified in native Level Sequence readback and
on-screen behavior. CED catalog recognition alone is not transfer fidelity.
