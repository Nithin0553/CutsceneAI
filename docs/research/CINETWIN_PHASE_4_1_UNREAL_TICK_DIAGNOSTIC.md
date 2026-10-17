# CineTwin Phase 4.1 — Diagnose stale Unreal editor evaluations

## Evidence and motivation

The full synchronous CineTwin comparison used 298 matching source/target
timestamps (8 mapped native actors, 21 currently unmapped source entities,
2 skeletal rigs), and detected very large world-position differences.

Two independent target rigs showed **zero observed bone displacement** even
though Unity source behavior showed >100 cm of bone displacement for each.
Other results included source moving / target static actors, alongside target
actors that did move. This is an **observer reliability warning** rather than
proof that the target animations are missing.

Epic documents that the Unreal Editor **does not tick while executing a Python
script**. Sequencer set_global_position / force_update can synchronously
change actor properties, but additional component evaluation may be deferred
until later editor ticks. Reference:

- https://dev.epicgames.com/documentation/unreal-engine/write-editor-tests-with-python-in-unreal-engine
- https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/LevelSequenceEditorBlueprintLibrary?application_version=5.7
- https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/module/unreal?application_version=5.7
- https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/SkeletalMeshComponent

**Hypothesis:** capturing all 298 source times in one blocking Python call may
have read stale, not-yet-ticked skeletal transforms.

## New experiment

The new integrations/unreal/cinetwin_tick_evaluator.py is a separate,
nonblocking, editor-only observation probe. It reuses the existing source
sampling plan, target actor mapping, and native bone observation routines.

Instead of evaluating hundreds of instants synchronously:

1. Seek to one chosen source-aligned timestamp.
2. Release the Python command so the editor can tick.
3. Wait three real Slate editor ticks (configurable).
4. Sample the mapped actors and native skeletal bones.
5. Seek to the next time and repeat.
6. Save a new JSON artifact only after the probe completes.
7. Restore the previously open Sequencer and playhead.

The probe does **not** change animation assets, source CSIR, target level,
or saved timeline. It does not enable animation in editor or edit skeletal
component settings; instead it records relevant existing flags for diagnosis.

If a rig has no observed world bone movement at all, it reports
NO_BONE_MOTION_OBSERVED and quality: SUSPECT. It does not claim fidelity.

## One local test after CI and merge

First pull the latest main to the existing repository.

Keep the Unreal Benchmark002 level and Level Sequence open. In the Unreal
Output Log Python console, execute:

```python
import sys
sys.path.insert(0, r"B:\Research\CutsceneAI\CutsceneAI\integrations\unreal")
import cinetwin_tick_evaluator

cinetwin_tick_evaluator.start(
    r"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002.cinetwin.sampling-plan.json",
    r"B:\Research\CutsceneAI\CutsceneAI\integrations\unreal\benchmark002_mapping.json",
    "/Game/CutSceneAI/Benchmark002/LS_Benchmark002",
    r"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002_Unreal_CineTwin_TickProbe.json",
)
```

**Do not run another script or close Unreal until the Output Log prints
Tick-synchronized observations SAVED or Tick capture FAILED.**

By default the probe takes five source-aligned times: 0, 0.75, 1.5, 2.25,
and 3.0 seconds. The first five frames would miss most character motion,
so this probe deliberately spreads its measurements across the walk and
transition. It writes a distinct file and does not replace the full synchronous
capture.

The Unreal log will include a quality status and a movement amount for each
target skeletal rig. If the bones now move, we should replace the original
synchronous observation strategy with tick-synchronized full capture and
revalidate all 298 times. If the bones remain static, investigate editor
animation ticking, Sequencer binding, or invalid bone-readback behavior before
attempting any cinematic correction.

To cancel an active capture, use:
```python
cinetwin_tick_evaluator.stop()
```

## Limits

The editor must remain open and ticking. Unreal Python API compatibility
must be confirmed in the actual target editor; Python CI validates static
structure and pure logic but cannot execute Unreal runtime calls. Runtime
side effects of Sequencer/event scripts are still possible, so use a project
working copy if external scripts execute.

The probe records native rig world positions and target transforms; it does
not establish source-to-target bone correspondence, lighting, camera projection,
audio, event equivalence, or complete cutscene fidelity.
