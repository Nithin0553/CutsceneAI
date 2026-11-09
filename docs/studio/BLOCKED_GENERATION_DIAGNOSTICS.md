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
