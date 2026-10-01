# Benchmark 001 — Unity Source Ground-Truth Freeze

Status: **FROZEN FOR UNITY → UNREAL TRANSFER**

## Source artifact

- Logical sequence: `Benchmark001_Timeline`
- CSIR schema: `0.1.0`
- Source engine: Unity `6000.3.8f1`
- CutSceneAI Unity adapter/extractor: `0.1.5`
- Source rate: `60/1` fps
- Duration: ~`10.0 s`
- SHA-256: `5da9ede712854e77bb51e914ccf99d6e5b7432e6b9d24acbbb971c2d539b5ef4`

This hash is the immutable identity of the accepted Benchmark 001 Unity export used as transfer ground truth. Any later source edit or re-export must be treated as a new benchmark source revision unless the SHA-256 is identical.

## Accepted transfer facts

- Character animation: `0.0 → 3.25 s`, source clip `mixamo.com`.
- Character Timeline clip offset is preserved canonically as `(0, 0, -7)` meters, corresponding to the authored Unity placement `(0, 0, +7)`.
- Moving prop motion is preserved with its infinite-track base offset and recorded transform curves.
- Camera A cut: `0.0 → 5.0 s`.
- Camera B cut: `5.0 → 10.0 s`.
- Camera B transform animation is preserved as an infinite AnimationTrack.
- Camera B field of view animates `35° → 25°`.
- Audio starts at `4.958367 s` and ends at `10.0 s`.
- Signal/event `Benchmark_Event_01` occurs at exactly `6.5 s`.
- Static scene context includes `Floor`, `Wall_Left`, `Wall_Right`, `Wall_Back`, `Wall_Front`, and `Landmark_Pillar` with canonical world transforms and scale.

## Source snapshot

- Root tracks: `7`
- Output tracks: `7`
- Extracted tracks: `7`
- Extracted entities: `18`
- Extracted assets: `10`

The 18 extracted entities include rendered child meshes of `CHARACTER_Guard` in addition to the benchmark-level entities. Those child mesh entities are preserved as source context but are not required target mappings for Benchmark 001 v0.1; the target mapping remains actor-level for the guard plus the explicitly mapped environment objects.

## Transfer rule

Unreal reconstruction must consume this CSIR as authoritative source data. Do not manually author target animation/camera timing to visually approximate the Unity scene. Target assets may be explicitly mapped, but timing, transforms, camera cuts, camera properties, audio timing, and event timing must come from CSIR.

After generation, the Unreal Level Sequence must be read back and compared against these frozen source facts before Benchmark 001 is considered complete.
