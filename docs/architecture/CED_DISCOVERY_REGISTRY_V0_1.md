# CED Discovery Registry v0.1 — local evidence, no automatic taxonomy changes

**Status:** Python implementation on experimental branch. Complements [CED-first preflight](CED_FIRST_PREFLIGHT_V0_1.md) and [Issue #74](https://github.com/Nithin0553/CutsceneAI/issues/74).

## Why the registry is separate from CED

The source cutscene can contain a known concept that only transfers partially. Benchmark 002 V2 recognized 369 humanoid-bone curves, 105 track/clip offsets and 21 root-motion channels as known-but-partial. These are **not newly discovered cinematic concepts**, and should not create 495 duplicate development tasks.

The registry therefore records only `UNKNOWN_CED`, `UNKNOWN_NATIVE`, and `NEEDS_EVIDENCE` findings. `KNOWN_PARTIAL`, `KNOWN_UNSUPPORTED`, and `MISSING_TARGET_MAPPING` remain in the source preflight/coverage report for normal conversion-issue triage.

## How it works

```text
CED preflight for one source cutscene
   |
   |-- supported / known partial / unmapped -> normal conversion coverage
   |
   +-- unknown / needs evidence
           |
           v
      Stable feature SHA-256 fingerprint
           |
           v
      Opt-in local append-only JSONL registry
           |
           v
      NEW semantic signature or ALREADY OBSERVED?
           |
           v
      Developer review -> reusable adapter/rule -> real engine tests
           |
           v
      Human approval -> versioned CED OR mapping-rule update
```

The registry stores only the feature fingerprint, event/semantic classification, a safe CED token, hashed source identity, CED/adapter version and digest, total observed occurrences and a UTC time. It **does not** persist source scene names, actor names, asset references, local paths, private CSIR data or raw native class strings. Repeated preflights of the same source/version are idempotent.

The registry currently assumes a **single writer** and does not implement cross-process locking; do not have two automated processes append concurrently.

## Register an existing Benchmark 002 V2 report

```powershell
cd "B:\Research\CutsceneAI\CutsceneAI"

python tools\ced_discovery_registry.py `
  --report "B:\Research\CutsceneAI\TransferPlans\Benchmark002_CED_Preflight_V2.json" `
  --registry "B:\Research\CutsceneAI\TransferPlans\CED_Discoveries_V1.jsonl" `
  --dry-run
```

The V2 report currently has no unknown semantic groups, so expected **new signatures = 0** and **new observations = 0**. No registry file is created for an empty update. This is healthy—no fake discovery issue should be created.

## Opt in during a future CED preflight

```powershell
python tools\ced_preflight.py `
  --csir "SOURCE.csir.json" `
  --mapping "TARGET_MAPPING.json" `
  --out "NEW_CED_REPORT.json" `
  --discovery-registry "B:\Research\CutsceneAI\TransferPlans\CED_Discoveries_V1.jsonl"
```

The preflight now records a SHA-256 digest of input CSIR bytes in its report. Original source and target mappings remain unchanged. Re-running with the same source/version does not add duplicate observations. When genuinely new semantics appear, the console reports the number of new signatures and observations.

## What is **not** implemented

- No automatic GitHub issue, email, push notification, background event watcher, CED change, or model training.
- The registry does not label a partial conversion as a new concept; those require **fidelity engineering** and an independent saved-Unreal readback.
- No automated review/approval transitions yet. Candidate definitions, implementation, tests, approval and release need separate controlled changes and explicit developer review.
- Detection is limited to semantics present in the source CSIR and native metadata. Novel effects entirely omitted by the Unity extractor will not be discovered automatically.

**Next milestone:** review process/notification adapter with explicit opt-in and source-data redaction; separate CED semantic updates from engine-specific strategy changes. Never overwrite V5 transfer plans or previously emitted reports.
