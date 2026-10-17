# CineTwin Phase 4.2 — Layered motion ownership evidence

## Why this experiment is necessary

The 298-timestamp behavior comparison showed: source Character A actor travels 289.86 cm while the target Unreal actor remains stationary, even though target skeletal bones move. The attached prop shows a similar discrepancy. Camera C and Character B have large **static placement** offsets; Camera B and the moving prop have genuine actor-space trajectory disagreements.

A physical rendered object can move through different layers: the Actor/root component, a child SceneComponent, or skeletal bones. Separate actor/world observations alone cannot reliably identify the responsible layer. Unreal's official Cinematic Animation Track documentation describes *Swap Root Bone* options (Actor, Component, None), and Unreal also exposes attachments:

- https://dev.epicgames.com/documentation/en-us/unreal-engine/cinematic-animation-track-in-unreal-engine
- https://dev.epicgames.com/documentation/en-us/unreal-engine/root-motion-in-unreal-engine
- https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/Actor
- https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/SceneComponent?application_version=5.7

## New, non-destructive observation

The existing tick-synchronized Unreal probe now accepts an **optional** `capture_motion_layers=True`. At each requested timestamp, it additionally records for every directly mapped actor:

- the actor's attachment parent label and attachment socket;
- each SceneComponent's full runtime object path and class;
- each SceneComponent's parent-component path and owner actor;
- the evaluated component world transform, canonicalized into CSIR coordinates;
- target native skeletal root-bone translation through the already measured rig poses.

The pure-Python motion ownership analyzer distinguishes:

- **ACTOR_TRANSFORM_MOVES** — actor root actually travels;
- **COMPONENT_MOVES_ACTOR_STATIC** — component world-space motion exists with a stationary actor;
- **SKELETAL_ROOT_MOVES_ACTOR_STATIC** — the native root bone moves but actor/component origin does not;
- **NO_TRANSLATION_OBSERVED_ON_ACTOR_COMPONENT_OR_ROOT_BONE** — no translational carrier found in the measured layers.

It separately checks direct source-parent to target-actor attachment **only if both parent and child are mapped as independent actors**. Otherwise the relationship remains unverified rather than assumed missing.

The analyzer records separate maximum movement by component and bone-root and rejects missing samples, duplicate components, changed component topology, invalid coordinates and missing root bones.

These results are hypotheses about **where** motion is stored, **not** source/target animation equivalence. They cannot establish pose correspondence or rendered fidelity.

## Local 5-time test after CI and merge

After updating local main, open the existing Unreal Benchmark002 level and sequence. In the Unreal Output Log Python console run:

```python
import importlib, cinetwin_tick_evaluator
importlib.reload(cinetwin_tick_evaluator)

cinetwin_tick_evaluator.start(
    r"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002.cinetwin.sampling-plan.json",
    r"B:\Research\CutsceneAI\CutsceneAI\integrations\unreal\benchmark002_mapping.json",
    "/Game/CutSceneAI/Benchmark002/LS_Benchmark002",
    r"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002_Unreal_CineTwin_MotionLayers.json",
    probe_times=(0.0, 0.75, 1.5, 2.25, 3.0),
    ticks_per_sample=3,
    capture_motion_layers=True,
)
```

Wait for the SAVED or FAILED log message. The resulting log prints, for each of the eight mapped actors, its actor/component/root-bone displacement, inferred carrier and parent-attachment status.

Do not save the Unreal assets or alter the frozen Unity source. This captures five source-aligned times only; it is not a substitute for the 298-timestamp full comparison. A full run can be requested later after the runtime probe is verified.

## Future step

Use the measured motion carriers as inputs to a source-to-target pose anchor and rig correspondence model. For root-motion correction, verify a world-space trajectory of the **actual rendered skeleton**, not only the actor origin. For parented props, check the effective parent-component hierarchy before adding transform keys.

The implementation is only proven by Python CI until Unreal 5.8.3 runtime testing succeeds.
