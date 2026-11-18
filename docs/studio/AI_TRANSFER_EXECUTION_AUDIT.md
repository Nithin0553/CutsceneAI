# AI Transfer Execution Audit — Reader and Verification Guide

**Scope:** CutSceneAI Studio's *main AI-first transfer path*. Separate from
Friday's character animation, root-motion, and asset-compatibility assignment
(issue #125). This audit is **read-only** and cannot import, move, overwrite,
or repair anything.

## Why this exists

A model can recommend a native strategy without Unreal successfully executing
it. A native Level Sequence can be generated without proving Unity/Unreal
behavioral fidelity. Neither should be reported as an AI conversion success.

The Studio provides `GET /api/ai-transfer-audit` and a compact **AI transfer
audit** section on the Review Cutscene screen.

It independently joins four kinds of source-bound evidence:

1. **Model planning decision:** the exact candidate's
   `ai-conversion-decision.json`, its recorded strategy and native options,
   and SHA-256 hash bound to the active job.
2. **Immutable transfer plan:** the candidate's `transfer-plan.json`,
   candidate mapping copy, and `session.json` mapping fingerprint.
3. **Native Unreal builder receipt:** the exact job's
   `unreal-runtime-receipt-<job-id>.json`. Completed generation must agree
   with the native plan hash, expected Unreal project and map, generated Level
   Sequence object path, and saved job state.
4. **CineTwin position comparison:** if present, the exact job's source-bound
   `CineTwin_WorldPose_Diagnosis_*.json` is checked against the Unity source
   and behavior-capture hashes, target Unreal project, and generated sequence.
   It shows maximum measured actor and skeletal-root positional differences,
   but **does not** establish camera, rotation, skeleton, audio, rendered-image
   or full animation fidelity.

An AI planning choice does **not** prove FBX material fidelity; enabling the
embedded material importer is recorded only as a native conversion option.
A visual-only ActivationTrack approximation does **not** preserve Unity
GameObject activation callbacks, collision or physics semantics.

## Status interpretation

- `NO_ACTIVE_TRANSFER` / `NO_AI_CONVERSION_DECISION`: no active
  job-bound AI planning evidence (for example, an older deterministic transfer).
- `AI_PLAN_QUEUED`: the AI decision was recorded and its native conversion
  actions were prepared; no generation proof exists.
- `AI_NATIVE_RUNNING`: the active Unreal job is still executing.
- `AI_NATIVE_BLOCKED`: execution stopped; preserve failed candidate and
  inspect the exact native error; never replay a partially imported candidate.
- `AI_NATIVE_GENERATED_UNVERIFIED`: the separately checked Unreal builder
  receipt proves a Level Sequence was generated, but cross-engine fidelity
  remains unverified.
- HTTP `409`: invalid or mismatched AI/native provenance. Do not treat the
  result as an AI transfer success; inspect the original job and receipt.
- `MEASURED_NOT_FIDELITY_VERIFIED`: source-bound CineTwin positions were
  measured, but this is **not** a parity PASS. Maximum errors greater than
  2 cm highlight clear mismatches.
- `MEASUREMENTS_INCOMPLETE` or `NOT_MEASURED`: absent or incomplete native
  position proof.

## How to inspect locally

Keep the Studio localhost server running (only this computer can access it):

```powershell
Invoke-RestMethod "http://127.0.0.1:8765/api/ai-transfer-audit" |
    Format-List status,strategy,conversion_options,model_decision_recorded,native_builder_completed,cinetwin,fidelity_verified
```

The API never sends OpenAI API keys or raw Unity/Unreal file bytes. Project
paths remain in local internal receipts rather than in the public audit response.
The Review Cutscene screen updates the summary automatically.

## Acceptance

The pure audit's tests verify queued vs native generated states, mismatched
decision hashes, candidate-path escape, missing native execution receipts,
missing visual activation actions, a failed native receipt, and a diagnostic
belonging to another Unreal project. The Studio API has an independent
no-active-job and path-confusion test.

**Still required:** a fresh, real Unity 6.3 → Unreal 5.8 staging transfer with
the AI-first code loaded after a full Unreal Editor restart. Mock/CI success
does not prove cross-engine parity. Do not merge the integration PR into
`main` on the basis of the audit alone.
