# CineTwin Phase 3 — Unreal behavior observation (first runtime probe)

## Why this is needed

The Unity source has already produced and structurally verified:

- 298 evaluated Timeline times;
- 29 entities;
- two complete native source skeletal rigs, including intermediate blend instants;
- no missing or invalid observations for the implemented layers.

These are **source** measurements, not proof of cross-engine equivalence.
Unreal must now provide its *own evaluated* state at the **same times**.

## First implementation

- Generic `packages/cinetwin/target_observation_plan.py` resolves
  source entity IDs to mapped Unreal actor labels.
- It records unmapped source entities honestly; it blocks if a source skeletal
  rig has no target actor or if two entities map to one target actor.
- `integrations/unreal/cinetwin_target_evaluator.py` scrubs an existing
  Unreal Level Sequence using `MovieSceneSequencePlaybackParams` in TIME mode.
- Sampling uses a `JUMP` update method and forces Sequencer evaluation,
  then reads actual editor-world actor transforms and native Unreal skeletal
  bone names, hierarchy, and world transforms.
- Target actor world transforms and world bone positions are converted into
  CutSceneAI canonical coordinate space. Native target bone rotations remain
  labelled as native Unreal quaternions to avoid pretending retargeted bone
  orientation equivalence has been established.
- It does **not** modify source CSIR, transfer rules, Unreal animations, actor
  assets, level data, or sequence assets. Only playhead/temporary editor-world
  evaluation state is changed. The previous open sequence and playhead are
  restored when the APIs allow it.
- Full 298-time capture is possible, but **first smoke test only five times**
  and verify that your actual Unreal 5.8.3 runtime supports all methods.

This is an **observer**, not the eventual CineTwin Player. It is not yet a
source-vs-target semantic comparator, and it does not assert bone correspondence
or equivalence merely because two skeletons have bones.

## Evidence and API references

- Unreal 5.8 [Sequencer Python scripting](https://dev.epicgames.com/documentation/unreal-engine/python-scripting-in-sequencer-in-unreal-engine).
- [LevelSequenceEditorBlueprintLibrary.set_global_position](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/LevelSequenceEditorBlueprintLibrary?application_version=5.7).
- [SkinnedMeshComponent.get_bone_transform](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/SkinnedMeshComponent?application_version=5.5).

These Python APIs are experimental and can change between versions. The
runtime observer fails closed instead of silently falling back to frame-only
rounding (which would invalidate source subframe blends).

## One local smoke test (after merge)

Open the existing Unreal Benchmark002 **level** and Level Sequence. In Unreal
**Tools → Debug → Execute Python Script** or **Window → Output Log** with Python
input enabled, run:

```python
import sys
sys.path.insert(0, r"B:\Research\CutsceneAI\CutsceneAI\integrations\unreal")
import cinetwin_target_evaluator

result = cinetwin_target_evaluator.run(
    r"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002.cinetwin.sampling-plan.json",
    r"B:\Research\CutsceneAI\CutsceneAI\integrations\unreal\benchmark002_mapping.json",
    "/Game/CutSceneAI/Benchmark002/LS_Benchmark002",
    r"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002_Unreal_CineTwin_Smoke.json",
    max_samples=5,
)
print("SAMPLES:", result["coverage"]["sample_count"])
print("MAPPED ENTITIES:", result["coverage"]["mapped_entity_count"])
print("UNMAPPED ENTITIES:", result["coverage"]["unmapped_source_entities"])
print("SKELETAL RIGS:", result["coverage"]["skeletal_rig_count"])
```

The output is saved separately and intentionally ignored by the frozen-source
workflow. The **Unreal** state may temporarily change when Sequencer scrubs.
If the actual engine API raises an error, capture the exact error and improve
the compatibility adapter; do not manually edit the cutscene.

## Next test and research

After a successful small probe, capture all source times, validate target
observations, and build source-versus-target comparison of world trajectories.
Pose comparison first requires stable source-to-target bone correspondence and
a retargeting policy; source Unity bone names and target Unreal bone names
must not be assumed equivalent.

This phase deliberately does not claim direct playback of Unity's evaluated
poses in Unreal, renderer parity, or automatic correction.
