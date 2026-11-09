# Studio blocked-generation diagnosis

When Studio shows **BLOCKED_OR_FAILED**, **Generated Sequence: Not generated**,
and an independent release gate failure at `native_generation`, the
primary problem is **an unsuccessful native Unreal transfer**. Missing
CineTwin captures, rendered-frame parity, saved-sequence persistence,
full skeletal pose, audio/event behavior and held-out learning are
downstream verification limitations, not ten independent causes of the
generation error.

## What the new Results page shows

For a failed job, the Studio Results page now displays:

- The **actual Unreal worker exception message** captured at failure
  (the prior UI displayed only `BLOCKED_OR_FAILED`).
- The **native execution stage** when a current worker records it
  (identity validation, plan verification, destination level, asset/actor
  staging, readiness, Level Sequence generation, or level save).
- Asset staging status and the failing operation/recovery text from the
  exact per-job native setup receipt when available.
- The persistent **job ID and creation time**, so a previously saved
  failure is not confused with the latest transfer.
- A **Copy failure details** button. Review copied content for private
  local paths before sending it elsewhere.

The UI never changes a failure into a success claim. If automatic
asset/actor staging was partial, **do not replay that candidate**—inspect
the staged Unreal project, preserve its receipts, correct the cause and
then create a separate, fresh transfer.

The new native stage field applies only to jobs executed after the updated
worker has been loaded. Older failed jobs still expose their original
`error` and `setup_status` fields, and the Results page labels an
unknown failure stage accordingly.

## Read the error from a pre-update job (PowerShell, read-only)

You can retrieve the existing failure without upgrading Studio:

```powershell
$root = Join-Path $env:USERPROFILE '.cutsceneai-studio\runs'
$active = Get-Content (Join-Path $root 'active-job.json') -Raw | ConvertFrom-Json
$jobFile = Join-Path $root ("jobs\" + $active.job_id + ".json")
$job = Get-Content $jobFile -Raw | ConvertFrom-Json
$job | Select-Object created_at,job_id,status,generation_status,setup_status,execution_stage,failure_stage,error,setup_receipt_file | Format-List
```

If `setup_receipt_file` exists, inspect only that recorded receipt for
`failed_step`, `error.message`, `status` and `recovery`. Avoid
executing its contents and never delete or overwrite assets just to reset
the status.

Also search the Unreal Editor Output Log for
`[CutSceneAI Studio] Job stopped:`. Exact job evidence is needed to
fix native importer or Sequencer code responsibly.

## Prior issue and PR review

- Issue #93 / PRs #102, #104–#106: the integrated Studio and native
  editor handoff, one-click UI, source selector and Results.
- Issue #94: source asset identity and staging.
- Issues #95–#98: native CED, character motion, cinematic fidelity and
  CineTwin checks. These require more than an exception label.
- Issue #101: independent release verification.

This change is about **observability, not automatic recovery**.
The concrete native failure is still unknown until the user's saved
job error or import receipt is examined. No branch, Unreal assets or
historical native evidence were deleted.


## Nov 9 manifest-verification failure: cached Python module mismatch

The observed native failure was:

`Source assets or prepared plan changed; regenerate setup manifest.`

The earlier `studio_auto_assets.verify()` implementation reran the source
inspection in Unreal and compared its entire result with the immutable
Studio-prepared manifest. Its error did not identify which field differed.

**Confirmed code-level problem:** Studio's `studio_planner_sync.synchronize()`
reloaded the transfer planner but omitted `studio_auto_assets`,
`studio_source_identity`, and `studio_source_materials`. Those
modules are referenced by `studio_auto_scene.assets_plan` inside Unreal's
long-lived Python interpreter. Since recent branches changed the source
light class and material/asset planner, a previously imported asset
inspector could disagree with a newly generated manifest even when
the Unity files were unchanged.

The new worker reloads those canonical repo modules **before any native
scene mutation**; existing imported module references are refreshed in
place, not pointed at a different checkout. New manifests also pin
inspector/identity/material implementation hashes. If files or adapter
source really changed after preparation, the transfer still fails closed
and reports the first relevant evidence class rather than the generic
"source assets or plan changed" message.

**This is an integration root cause supported by source-code inspection**,
but the original job does not contain a field-level diff. We cannot
prove which of the possibilities caused that individual candidate to
fail without inspecting its saved exact manifest, source hashes and
editor Python module state.

### Safe retry after installing the fix

1. Stop Studio and completely **close Unreal Editor**. Save and back up
   existing staging projects as appropriate. Closing Unreal clears any
   cached old Python source modules.
2. Check out `fix/studio-stale-auto-asset-manifest-verifier` in the same
   repository that both Studio and Unreal companion scripts use.
3. Restart Studio via `tools/start_studio.ps1`, then open the intended
   Unreal staging project and the saved target level.
4. On Home click **Start Transfer**, select the exact CSIR and matching
   Source Census again, and use the prescribed companion command.
5. **Create a NEW unique candidate.** Do not replay or edit the failed
   `20261109T182755Z_d621b56b` candidate; immutable old manifests
   predate source-code pinning and were rejected.
6. If any new candidate still fails, copy the precise **Native error**
   from Results, and check whether it says `Unity CSIR source export`,
   `prepared target mapping`, `immutable transfer plan`,
   `Source asset contents`, or `source ... planning`. Do not
   bypass hash comparisons or suppress the gate.

Successful import and Level Sequence generation still do **not** imply
CineTwin or rendered-frame parity.


## Nov 9 follow-up: old companion still accepted a newly prepared candidate

A second actual job, `ad10e38a5a27436988384910204e219f`,
created `2026-11-09T18:52:50.868355+00:00`, still showed
`UNKNOWN_NATIVE_STAGE` and the **old generic** source-manifest error.
The updated PR #108 verifier would instead classify a manifest mismatch
by source hash, adapter hash, asset identity, or changed planning field.
This is strong evidence that the Unreal process had not loaded the newly
patched verifier, although it does not independently establish the precise
reason the original manifest comparison differed.

**Confirmed additional interface defect:** Unreal's heartbeat always
reported `studio-editor-v0.5`, even after major updates. Studio validated
this same constant across incompatible worker implementations. It could
therefore submit another candidate to a stale embedded Python interpreter.

The new `studio-editor-v0.6` companion reports its **worker code SHA256
captured at Python import**, and the canonical checkout path. The Studio
host compares both against its trusted repository and refuses the transfer
with `UPGRADE_COMPANION` when the worker is old, came from another
checkout, or remained loaded across a code update. Missing and relative
checkout paths are rejected. Do not delete heartbeat or job records to
bypass this rule.

**Important preflight safety fix:** The previous worker could call
`_ensure_target_level()` *before* `studio_auto_assets.verify()`. For an
automatic fresh-level request, that meant an empty target level might have
been created despite a later setup receipt saying no import/actor mutation.
The worker now verifies the source-asset manifest before even attempting
new-level creation, and records `VERIFYING_SOURCE_ASSET_MANIFEST` in
new failures.

### Check that the correct Unreal worker is running

1. Stop Studio, save the Unreal project and **fully close Unreal Editor**.
2. Fetch the new branch `fix/studio-worker-version-handshake-and-safe-preflight`.
   Run Studio and the Unreal companion from the **same clone**.
3. On Windows, a read-only inspection of the latest worker heartbeat is:

```powershell
Get-Content "$env:USERPROFILE\.cutsceneai-studio\runs\unreal-worker.json" -Raw |
  ConvertFrom-Json |
  Select-Object worker,checkout_root,worker_source_sha256,heartbeat
```

4. A current, live worker must say `studio-editor-v0.6`; it must also
   report a matching checkout and a matching SHA256 (the host checks
   both). If it says `v0.5` or lacks the new fields, do not click
   **Start Transfer**. Restart Unreal and run the latest companion.
5. Create one completely **fresh** candidate; never rerun the prior
   `ad10e38a5a27436988384910204e219f` job or its candidate.
6. If a new transfer still fails, its **Execution stage** and **Native
   error** should expose whether the CSIR, target mapping, transfer plan,
   source assets, or inspector code actually changed. Inspect that exact
   mismatch; never suppress hash checks.

These are code-level fixes with CI regression coverage. They still need
real Unreal Editor validation before asserting the Benchmark002 transfer
is complete.
