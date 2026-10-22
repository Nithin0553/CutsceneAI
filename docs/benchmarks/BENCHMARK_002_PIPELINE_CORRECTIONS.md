# Benchmark002 — conversion corrections (staging)

Scope: reusable Unity CSIR → Unreal implementation, not a new Benchmark002-only mapping.
Source Unity scene, Benchmark001 frozen artifacts, and original Unreal target were not edited.

## Corrections implemented

1. **Initial placement:** scene preparation retains the static world-placement fallback for cameras that contain an AnimationTrack but no transform keys. It additionally supports an **opt-in provenance-checked CineTwin source behavior capture**, placing every mapped actor from Unity's *evaluated first-frame* world transform instead of a possibly stale editor position. Dynamic pose correctness still requires real target editor observation.
2. **Animation clip timing and root motion:** Unreal skeletal sections receive Unity clip source offsets in target tick-resolution units and easing through UE5.8's documented MovieSceneSectionEasingExtensions. Overlapping clips from the same source animation track become sections on a single target track; only the final section holds its end pose. Independent readback now checks trim and easing. Root-motion orientation and sampled trajectory corrections remain measured, with unsupported multiple corrections rejected before actor mutations. Cross-rig pose equality remains unproven.
3. **Transform motion:** plan generation processes every sequential section, accepts full quaternion rotation channels, frame-bakes native Unity curve tangents with unweighted Hermite interpolation, and marks baked keys linear in Unreal. Overlapping transform sections and weighted/nonfinite tangents are explicitly rejected instead of silently generating incorrect motion.
4. **Camera and remaining cinematic elements:** nonlinear camera vertical-FOV tracks are sampled to frames; light intensity becomes a component track with explicit source-derived expectation, native readback and numeric validation (not photometric parity); source audio fade durations become guarded Unreal easing. Camera optical/pixel fidelity, audio waveform matching and event payload execution remain outside this change.

## Known limitations

- No actual Unity or UE5.8 runtime is available in CI; GitHub CI tests Python planning and code contracts but cannot certify visual/pose parity.
- Root-motion imported asset correspondence and true cross-rig pose retargeting still require the 298-time source/target comparison.
- Timeline clips using Unity weighted tangents or unsupported interpolation must use a separate evaluator.
- Dynamic attachment reparenting, nontrivial nested animated parent hierarchy, physics, socket parenting and component-only mappings remain unproven.
- Engine-specific API availability for offsets, ease, light property binding and key interpolation is checked and failures are surfaced; stage on a disposable Unreal project copy.
- Audio easing is not assumed identical to native Unity mixing without an audio playback comparison.
- This branch is not safe to merge as "benchmark accepted" until the full runtime validation report passes.

## Opt-in first-frame source calibration

In a staging mapping JSON, set `source_behavior_capture_path` to the absolute
path of the previously generated, **complete Unity CineTwin behavior capture**
(e.g. `Benchmark002_Timeline.cinetwin.behavior.json`). Do not edit the frozen
source CSIR. The capture must have the same cutscene ID, source Timeline
reference and Unity project fingerprint, and must include playback frame zero
with world transforms for all mapped non-audio entities.

For example, the mapping entry is:

```json
{
  "source_behavior_capture_path": "D:\\\\CutSceneAI - Studio\\\\CutsceneAI_Benchmark001_Unity\\\\CutSceneAI\\\\Exports\\\\Benchmark002_Timeline.cinetwin.behavior.json"
}
```

Merge this key into the **existing staging mapping** rather than replacing its
entities/assets/output configuration. Use the copied Unreal test project and a
new sequence path; keep `overwrite_sequence=false`.

## Verification required in copied target

1. Generate an Unreal test sequence using the original frozen CSIR and a staging mapping on an isolated Unreal project copy.
2. Verify source animation trim/blending and character root motion at the walk-to-turn transition using the actual runtime, not just readback of section timing.
3. Capture 298 tick-synchronized times and compare against the existing Unity full behavior capture; exclude Unreal's exclusive 12-second endpoint only through the explicit boundary-aware policy.
4. Check first-frame position/orientation, track interpolation, bone pose correspondence, the moving camera's world component transform and lens behavior.
5. Independently read back the saved sequence and verify persisted hierarchy after editor restart; render source and target frames at matching times.
6. Do not claim final Benchmark002 acceptance unless spatial, skeletal, camera and relevant cinematic-effect gates pass.

Reference code: `integrations/unreal/csir_plan.py`, `scene_prep.py`, `build_level_sequence.py`, and `tests/unreal/test_benchmark002_parity_corrections.py`.
