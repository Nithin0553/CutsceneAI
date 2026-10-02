# Benchmark 002 — Generalization Unity → Unreal Transfer

## Purpose

Benchmark001 proved the end-to-end pipeline on a controlled single-character sequence. Benchmark002 is deliberately different. Its purpose is to determine whether CutSceneAI generalizes through Project Intelligence + CED + CSIR + adaptive mapping, rather than through assumptions learned only from Benchmark001.

The benchmark must not copy Benchmark001 timing, camera count, character count, or output aspect.

## Source / target

- Source: Unity Timeline
- Target: Unreal Level Sequence
- Source display rate: **24 fps**
- Duration: **12 seconds**
- Validation output: **2048 × 858**
- Source remains authoritative.
- Benchmark002 reuses the existing Unity benchmark project but lives in a separate scene/Timeline/assets namespace; Benchmark001 remains untouched.
- Target assets may be prepared/mapped, but cinematic timing and authored behavior must come from source extraction.

## Source scene design

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

### Timeline

```text
0s                  4s                  8s                 12s
|-------------------|-------------------|-------------------|

CAM_A_Wide          CAM_B_Move          CAM_C_Close
[==================][==================][==================]

CHARACTER_A
Walk / root motion
[================]
             Turn / settle
             [==========]
             overlap/blend

CHARACTER_B
        Gesture / move
        [=======================]

PROP_MOVING
    [======================================]

LIGHT_KEY
[ intensity animation ==================== ]

AUDIO_AMBIENCE
[==========================================================]
                              AUDIO_CUE
                              [====================]

Events:
      E1                 E2                      E3
     2.5s               6.0s                    9.5s
```

## Authored requirements

Character A must contain two animation sections with a real overlap/blend interval. At least one of its clips must contain root motion. Character B must use an independently bound animation track so binding logic is exercised with more than one skeletal actor.

`PROP_MOVING` must use keyed/infinite transform motion. `PROP_PARENTED` must preserve an authored parent relationship rather than being flattened to an unrelated world-space object.

The three cameras must use different transforms. `CAM_B_Move` must animate position or rotation. `CAM_C_Close` must animate vertical FOV or an equivalent physical lens parameter. Cuts occur at exactly **4.0 s** and **8.0 s**.

`LIGHT_KEY` must animate intensity over a visible interval. This intentionally extends beyond Benchmark001 and should become a new deterministic adapter capability rather than a manual Unreal correction.

Two audio sections must overlap. At least one fade-in and one fade-out must be authored. Three events occur at **2.5 s**, **6.0 s**, and **9.5 s**; at least one event must carry a non-empty payload that can be represented by CSIR even if the target later requires a mapping decision.

## What Benchmark002 is testing

The important new question is not simply “can we generate another sequence?” It is:

```text
Can CutSceneAI analyze a substantially different cutscene in the same source project,
discover the relevant semantics,
resolve mappings from evidence,
generate the target,
read it back,
and validate it
without adding Benchmark002-specific hacks?
```

Any code path that checks the literal benchmark name to decide transfer semantics is a benchmark failure.

## Expected development behavior

Some requirements are intentionally beyond the current Unreal realization/readback coverage, notably animation blending, light animation, richer audio fades/event payloads, and parent relationship validation. Those gaps should first appear as NEEDS_EVIDENCE, BLOCKED, or INCOMPLETE, then be implemented as reusable CED/adapter capabilities.

Do not manually repair the target sequence.

## Acceptance

Benchmark002 passes only after the Unity source is frozen by SHA-256, Project Intelligence profiles are captured for source and target, adaptive mappings are resolved without benchmark-name special cases, Unreal generation completes from CSIR, the saved target is independently read back, all required automated checks report zero failed and zero incomplete, visual review confirms the intended cinematic result, and source/target/mapping/readback/validation/software identities are frozen.

The machine-readable definition is `BENCHMARK_002_SPEC.json`.

## Generalization scope

Benchmark002 tests **cutscene-level generalization** while holding the Unity project/runtime configuration constant. This deliberately isolates new cinematic structure from project-setting changes. Project-level generalization across different render pipelines, engine versions, import conventions, or project settings should be tested in a later benchmark rather than confounded with this one.
