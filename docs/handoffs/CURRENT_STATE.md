# CutsceneAI Current State

## Product definition

CutsceneAI transfers an already-existing cinematic cutscene from a source game engine into a target game engine with measurable fidelity.

The source cutscene is ground truth.

## Current milestone

Foundation Milestone 1.

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

## Architecture documents

- `docs/architecture/FOUNDATION_V0_1.md`
- `docs/architecture/COORDINATE_CONVENTIONS_V0_1.md`
- `docs/architecture/TIMING_CONVENTIONS_V0_1.md`

## First benchmark

`docs/benchmarks/BENCHMARK_001.md`

Benchmark 001 is a controlled 8–12 second Unity Timeline containing one character/animation, one moving prop, two cameras, one cut, camera motion/lens data, one audio clip, one event, and enough environment geometry to validate placement/framing.

Equivalent/prepared assets and manual mappings are intentionally used so the first proof isolates transfer mechanics rather than asset-search or retargeting complexity.

## Next implementation step

Implement the Unity source-side adapter for Benchmark 001 in this order:

1. Unity project validation/version detection
2. Timeline enumeration
3. relevant binding/asset discovery
4. read-only extraction of sequence timing
5. read-only extraction of entities/bindings
6. track/section extraction
7. transform/camera/audio/event extraction
8. source snapshot generation
9. CSIR v0.1 serialization
10. fixture-based tests before connecting Unreal generation

Do not start automatic asset matching, ML, advanced retargeting, VFX reconstruction, or semantic correction until the deterministic benchmark path is validated end to end.
