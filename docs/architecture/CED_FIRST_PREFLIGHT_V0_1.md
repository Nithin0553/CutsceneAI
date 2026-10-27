# CED-first preflight v0.1 — review before conversion

**Status:** implemented in Python on an experimental feature branch. This is **Stage 1** of [CED Issue #74](https://github.com/Nithin0553/CutsceneAI/issues/74): discovery and reporting, **not** self-modifying CED or automatic GitHub notification.

## Principle

CED is the stable vocabulary of what a cinematic element **means**. The versioned Unity→Unreal capability registry says what the **current adapter can attempt**. CSIR retains original source data. CineTwin independently verifies **target behavior**, not just planned or authored actions.

```text
Unity structural CSIR (+ native type metadata)
            |
            v
CED taxonomy: is the element's meaning known?
            |
            v
Unity→Unreal capability registry: is there an applicable structural strategy?
            |
            v
Read-only preflight: known, partial, missing evidence, unknown native / unknown CED
            |
            v
User review and transfer readiness (strict or explicitly best-effort)
            |
            v
Action planner -> guarded Unreal generator -> saved target readback -> CineTwin
            |
            v
Later: approved discovery queue, generic adapter implementation and versioned update
```

## Current source of truth

- **Canonical engine-neutral concepts:** `packages/contracts/dictionary/cutscene-elements-v0.1.json` (unchanged).
- **Adapter strategy availability:** `packages/contracts/dictionary/unity-unreal-preflight-v0.1.json` (new; no claims of visual/audio/pose fidelity).
- **Audit implementation:** `packages/studio/ced_preflight.py` (no engine imports or mutation).
- **Read-only command:** `tools/ced_preflight.py`.
- **Best-effort planner:** `packages/studio/transfer_backend.py`, now consults preflight **before composing any actions**, embeds complete `ced_preflight` into the coverage report, and binds taxonomy/adapter file hashes into its plan and evidence.

An element may be an ordinary, known CED concept but **still lack a working target strategy**. Unsupported `event.state` is such a case. An unfamiliar Unity custom track extracted as generic `timeline.track` must not be treated as supported; its `metadata.native_type` is checked against recognized native aliases. Unknown property channels are reported individually.

## Status vocabulary

| State | Meaning | Acceptance |
| --- | --- | --- |
| `SUPPORTED_UNVERIFIED` | Known CED ID with a registered adapter strategy | May be planned; must still verify target |
| `KNOWN_PARTIAL` | Transfer path retains only part of original semantics | User review / loss accounting |
| `KNOWN_UNSUPPORTED` | Concept known but current target strategy absent | No promise of equivalent conversion |
| `UNKNOWN_NATIVE` | Native type hidden behind generic CED fallback | Needs classification |
| `UNKNOWN_CED` | Extracted canonical ID not in CED | Candidate new definition or extractor fix |
| `NEEDS_EVIDENCE` | No sufficient canonical meaning or native type | Needs source inspection |
| `MISSING_TARGET_MAPPING` | Referenced source asset / bound actor has no explicit mapping | Must resolve or explicitly omit |

A `REVIEW_REQUIRED` audit means some active source behavior is unknown, unsupported, partial or needs evidence. Muted/empty tracks are still listed but do not create active alerts.

## Usage: before running Unreal

```powershell
cd "B:\Research\CutsceneAI\CutsceneAI"

python tools\ced_preflight.py `
  --csir "D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002_Timeline-e6518af4.csir.json" `
  --mapping "integrations\unreal\benchmark002_cinetwin_parity_mapping.json" `
  --out "B:\Research\CutsceneAI\TransferPlans\Benchmark002_CED_Preflight_V1.json"
```

Output names are examples: do not overwrite an existing file. Report includes source locations (indices), observed native type, canonical concept, explanation, status and a deterministic per-feature fingerprint. No source project or target scene is changed. This report is **local**; it is **not** uploaded to GitHub.

Use `--strict` to exit nonzero when any active issue needs review, including partial conversion. Default standalone preflight is informative (exit 0 if it could inspect the source), even when review is required; this allows exploratory investigations.

The normal `tools/transfer_backend.py` command now automatically includes the CED preflight report in `coverage-report.json`, reports the number of active warnings, and binds file hashes in `evidence.json`. `--strict-ced` rejects planning if any active issue remains.

**Compatibility warning:** this changes the content of future transfer plans, coverage reports and evidence. **Do not reuse or overwrite Benchmark002 V5 prepared artifacts or old runtime receipts.** Use a new directory and restart Unreal after adopting the feature; comparison against old versions must be explicit. PR #52 remains the independent experimental transfer baseline until this feature has been reviewed.

## Safety and remaining work

- The current best-effort planner reports warnings but does **not yet require interactive acceptance** of each omission; strict mode blocks all reviewed/partial paths. The explicit user-review gate is a separate follow-up.
- Unknown native types are captured from CSIR metadata. No scene objects are introspected outside provided source data.
- Fingerprints include semantic/native type and feature kind but **not** source file paths, asset paths or object names. Reported `source_id` values may still be project-specific; share reports only after reviewing their contents.
- No automatic CED dictionary edits, GitHub Issues, email, background agent or generated adapter logic. The next stage should persist deduplicated discoveries locally and allow explicit opt-in notification with privacy filtering, then support a review/approval lifecycle.
- `SUPPORTED_UNVERIFIED` does not mean engine parity. Numerical motion, skeletal pose, camera framing, lighting, audio, event execution and rendered parity remain separate research gates.
