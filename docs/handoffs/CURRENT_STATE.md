# CutsceneAI Current State

## Product definition

CutsceneAI transfers an already-existing cinematic cutscene from a source game engine into a target game engine with measurable fidelity.

The source cutscene is ground truth.

## Current milestone

Engine Milestone 2 — Unity read-only structural extractor v0.1.

## Initial transfer direction

Unity → Unreal first. Reverse transfer follows after the complete deterministic proof is working.

## Frozen architectural decisions

- source project is read-only by default
- source cutscene is authoritative ground truth
- CED is engine-neutral
- Unity/Unreal mappings live outside the canonical dictionary
- CSIR preserves canonical values plus source-native escape-hatch data
- canonical space is right-handed, +Y up, -Z forward, +X right, meters, quaternion XYZW
- timing is rational and source-preserving; no forced 24/30/60 fps normalization
- every transferred element ends in an explicit outcome: EXACT, CONVERTED, RETARGETED, BAKED, RECONSTRUCTED, TARGET_MAPPED, or BLOCKED
- target generation occurs in staging before commit
- generated target results must be read back before validation
- deterministic transfer is preferred over AI/ML
- AI/ML enters only when ambiguity/reconstruction cannot be solved reliably otherwise

## Foundation contracts

- `packages/contracts/dictionary/cutscene-elements-v0.1.json`
- `packages/contracts/dictionary/unity-mappings-v0.1.json`
- `packages/contracts/dictionary/unreal-mappings-v0.1.json`
- `packages/contracts/common/coordinate-system-v0.1.schema.json`
- `packages/contracts/common/rational-time-v0.1.schema.json`
- `packages/contracts/common/transfer-outcome-v0.1.schema.json`
- `packages/contracts/csir/csir-v0.1.schema.json`
- `packages/adapters/interface.py`

## First benchmark

`docs/benchmarks/BENCHMARK_001.md`

Benchmark 001 is a controlled 8–12 second Unity Timeline containing one character/animation, one moving prop, two cameras, one cut, camera motion/lens data, one audio clip, one event, and enough environment geometry to validate placement/framing.

## Unity extractor implementation

Package path: `integrations/unity/com.cutsceneai.extractor`

Current structural extraction covers Timeline identity/frame rate, recursive tracks, bindings, entity transforms, Camera/Animator metadata, clip timing/blends, animation/audio assets, raw + canonical animation keys, activation/camera-cut handling, SignalEmitter markers, generic fallback, source snapshot/provenance hash, and export to `CutsceneAI/Exports/*.csir.json`.

Structural extraction deliberately does not call `PlayableDirector.Evaluate()` or mutate/save source assets/scenes.

## Automated checks

Python CI statically verifies the Unity package baseline, editor-only assembly, required Timeline read APIs, absence of known source-mutating APIs, raw + canonical animation key preservation, and export menu presence.

## Manual gate required next

GitHub CI cannot compile Unity C# without a Unity runner/license. The next gate is local Unity verification:

1. pull latest `main` after the extractor PR merges
2. create/open Benchmark 001 Unity project in Unity 6000.0 with Timeline 1.8.10
3. install local package from `integrations/unity/com.cutsceneai.extractor/package.json`
4. confirm package compiles with zero errors
5. select the Benchmark PlayableDirector
6. run `Tools > CutsceneAI > Export Selected Timeline`
7. provide the generated `.csir.json` back to CutsceneAI
8. validate it against CSIR v0.1 and benchmark expectations

Do not start Unreal generation until this exported artifact passes validation.
