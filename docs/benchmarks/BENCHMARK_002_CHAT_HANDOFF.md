# Benchmark 002 — New Chat Handoff

## Purpose

This document is the continuity handoff for starting Benchmark002 in a fresh ChatGPT conversation. The new chat should treat this file plus the Benchmark002 spec/build docs as the authoritative starting point.

## Repository

- Repository: `Nithin0553/CutsceneAI`
- Local repository: `B:\Research\CutsceneAI\CutsceneAI`
- Current workflow: feature branch → implementation/tests → PR → CI → merge to `main`
- Before beginning local work: `git pull origin main`

## Benchmark001 is frozen

Benchmark001 is complete and must not be modified.

- Status: `FROZEN AUTOMATED PASS — UNITY → UNREAL`
- Automated validation: 54 PASS / 0 FAIL / 0 INCOMPLETE
- Frozen Unity CSIR SHA-256: `5da9ede712854e77bb51e914ccf99d6e5b7432e6b9d24acbbb971c2d539b5ef4`
- Frozen Unreal Level Sequence SHA-256: `384f246f066cbab18969d49d4a4824e8aa80c16f42175098796a3ed522618304`
- Freeze record: `docs/benchmarks/BENCHMARK_001_TARGET_FREEZE.md`
- Portable manifest: `docs/benchmarks/BENCHMARK_001_TARGET_FREEZE_MANIFEST.json`

Do not edit, regenerate, overwrite, or reuse Benchmark001 assets as Benchmark002 assets.

## Benchmark002 goal

Benchmark002 tests **cutscene-level generalization** under the same Unity project/runtime configuration. It should determine whether CED + CSIR + Project Intelligence + adaptive mapping can transfer a substantially more complex cutscene without Benchmark002-specific hacks.

Benchmark002 deliberately changes the cinematic structure while holding the Unity project constant. A later benchmark will test project-level/engine-version/render-pipeline generalization.

## Unity project decision

Reuse the existing Unity benchmark project. Do **not** create a new Unity project.

Create only:

- a new scene named `Benchmark002`
- a new Timeline/PlayableDirector
- a separate Benchmark002 asset namespace such as `Assets/CutSceneAI/Benchmark002/`

Benchmark001 scene/Timeline/assets remain untouched.

## Benchmark002 fixed specification

- Source: Unity Timeline
- Target: Unreal Level Sequence
- Display rate: **24 fps**
- Duration: **12.0 seconds**
- Validation output: **2048 × 858**
- Camera cuts: exactly **4.0 s** and **8.0 s**
- Events: exactly **2.5 s**, **6.0 s**, **9.5 s**

Starting hierarchy:

```text
Benchmark002
├── ENVIRONMENT
├── CHARACTER_A
├── CHARACTER_B
├── PROP_MOVING
├── PROP_PARENTED
├── CAM_A_Wide
├── CAM_B_Move
├── CAM_C_Close
├── LIGHT_KEY
├── AUDIO_AMBIENCE
├── AUDIO_CUE
└── CUTSCENE_DIRECTOR
```

Required challenges:

- two independently bound characters
- at least three animation sections total
- real overlap/blend on CHARACTER_A
- at least one root-motion clip
- a separate CHARACTER_B animation track
- one independently animated prop
- one authored parent relationship
- three cameras
- animated CAM_B transform
- animated CAM_C lens/FOV
- animated light intensity
- two overlapping audio sections
- at least one fade-in and fade-out
- three events, with at least one non-empty payload

Machine-readable spec:

- `docs/benchmarks/BENCHMARK_002_SPEC.json`

Human-readable benchmark definition:

- `docs/benchmarks/BENCHMARK_002.md`

Source build checklist:

- `docs/benchmarks/BENCHMARK_002_SOURCE_BUILD.md`

## Architecture rules

Core philosophy:

```text
Extract first.
Preserve whenever possible.
Convert when possible.
Retarget when necessary.
Reconstruct only when exact transfer is impossible.
Never regenerate information we already possess.
```

Fallback ladder:

`PRESERVE → CONVERT → RETARGET → RECONSTRUCT → REPORT UNSUPPORTED`

Stable semantic architecture:

```text
CED = stable engine-neutral meaning
CSIR = authoritative source ground truth
Project Intelligence Profile = observed engine/version/project facts
CSIR Adaptive Context = cutscene-specific source observations
Resolved Mapping Dictionary = dynamic source/target mapping decision
```

Do not mutate CED or source CSIR meaning based on the target engine.

Do not add code such as `if benchmark == "Benchmark002"` to decide transfer semantics. Benchmark-specific wrappers may select filenames/labels only; adapters, mappings, readback, and validation behavior must remain reusable.

Project Intelligence must prefer observed capabilities/settings over version-only assumptions.

## Existing reusable infrastructure

Important files already implemented:

- `docs/architecture/ADAPTIVE_PROJECT_INTELLIGENCE_V0_1.md`
- `packages/contracts/project/project-profile-v0.1.schema.json`
- `packages/contracts/csir/csir-adaptive-context-v0.1.schema.json`
- `packages/contracts/dictionary/adaptive-mapping-rules-v0.1.schema.json`
- `packages/contracts/dictionary/resolved-dictionary-v0.1.schema.json`
- `packages/contracts/dictionary/adaptive-rules-v0.1.json`
- `packages/readiness/adaptive_mapping.py`
- `integrations/unity/com.cutsceneai.extractor/Editor/UnityProjectIntelligence.cs`
- `integrations/unreal/project_intelligence.py`
- `integrations/unreal/validate_transfer.py`
- `packages/validation/benchmark_spec.py`
- `tools/check_benchmark_source.py`

Benchmark001 taught and permanently fixed:

- Unreal Python Rotator semantic argument ordering
- canonical-to-Unreal pitch semantics
- camera FOV/filmback realization
- Unreal version/API capability probing
- root-motion direction calibration
- actor-world root-motion yaw correction
- final skeletal-pose hold/post-roll
- readback-based validation instead of trusting generation
- grounded root-motion semantic validation

Do not reintroduce old fixes manually.

## Benchmark002 source readiness gate

After authoring the Unity source:

1. Run `Tools → CutsceneAI → Analyze Project`.
2. Export Benchmark002 CSIR.
3. Run:

```powershell
cd B:\Research\CutsceneAI\CutsceneAI

python tools\check_benchmark_source.py `
  --spec "docs\benchmarks\BENCHMARK_002_SPEC.json" `
  --csir "D:\path\to\Benchmark002.csir.json" `
  --output "D:\path\to\Benchmark002.source-readiness.json"
```

Interpretation:

- exit `0` / `READY` → source meets benchmark requirements
- exit `2` / `FAIL` → hard mismatch such as wrong timebase/duration
- exit `3` / `NEEDS_EVIDENCE` → authored feature is missing or extractor/CSIR does not preserve it

Do not begin Unreal generation until source readiness is `READY`.

## Expected gaps

Benchmark002 intentionally includes features that may expose missing reusable capabilities:

- animation blending
- parent relationship realization/readback
- animated light intensity
- richer audio fades
- event payload realization/readback

When one fails, determine whether the problem is:

1. source authoring,
2. Unity extraction,
3. CED/CSIR contract,
4. adaptive mapping/readiness,
5. Unreal realization,
6. Unreal readback, or
7. validation semantics.

Then fix the reusable layer, add a regression test, and record the finding. Do not manually repair the target.

## Immediate next step in the new chat

Start in the existing Unity benchmark project.

First action only:

1. create a new scene named `Benchmark002`;
2. create `Assets/CutSceneAI/Benchmark002/`;
3. create the empty hierarchy listed above;
4. do **not** create Timeline tracks yet;
5. show a screenshot of the Unity Hierarchy/Project view.

The assistant should guide one screen/stage at a time.
