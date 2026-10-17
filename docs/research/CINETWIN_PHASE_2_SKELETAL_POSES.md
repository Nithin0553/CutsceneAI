# CineTwin Phase 2 — Evaluated Skeletal Pose Capture

## What changes

The first CineTwin experiment successfully captured 298 requested instants for 29
source entities (transforms, camera field of view and light intensity). The verifier
reported no failed measurements, but skeletal pose was not implemented.

This phase makes skeletal pose capture a first-class, **verified** source behavior
layer. It does not yet implement Unreal skeletal playback or cross-engine retargeting.

## Source of rig identity

The sampling planner uses **source Timeline animation tracks bound to actual
character entities**, not every mesh part tagged `entity.character`.
For Benchmark002 this should select precisely the two animated character roots.

A regenerated sampling plan includes `skeletal_entity_ids`. The frozen CSIR is
not modified. Previously generated sampling plans are obsolete for this new capture
contract; regenerate the plan using the same command as Phase 1.

## What is captured

In Unity **Play Mode**, after setting the selected PlayableDirector's time and
calling `Evaluate()`, the capture adapter obtains the bone Transform references
from the animated character's `SkinnedMeshRenderer.bones`.

It writes:

- stable source bone identifiers that include sibling indices, so repeated bone
  names do not collide;
- skeletal rig definitions, bone hierarchy paths and direct parent-bone identities;
- every bone's **evaluated local transform and world transform** in the same
  canonical coordinate basis as CSIR;
- each bone's state at **every requested time**, including subframe samples in
  overlap/blend regions.

This is not a reconstruction of isolated animation-clip keys. It measures the
final scene state following source Timeline evaluation. The data provides evidence
for future retargeting and a target engine behavior player.

## Reliability and scope

- The verifier rejects missing or duplicated rigs/bones and missing or nonfinite
  local/world transform components.
- If a Timeline-bound animated character does not expose a bone array through a
  `SkinnedMeshRenderer`, the prototype raises an error and refuses to label skeletal
  pose as captured. We must add a different rig adapter rather than pretending
  capture succeeded.
- Local transforms are relative to each bone's actual Transform parent. When the
  direct parent is not in the skinning-bone list, the recorded parent-bone identity
  is empty. The full hierarchy path is retained for later topology reconstruction.
- The capture does not yet sample facial blend shapes, external IK solutions,
  constraints, physics, audio output, executed events or rendered pixels. These
  still need explicit capture strategies.
- Unity `Evaluate()` can trigger scene scripts/signals. Use an isolated working
  copy for scenes with external side effects. No authored assets are saved.

Technical background:
- [Unity PlayableDirector](https://docs.unity.com/en-us/engine/6000.6/script-reference/unityengine/playables/playabledirector)
- [Unity SkinnedMeshRenderer.bones](https://docs.unity.cn/6000.0/Documentation/ScriptReference/SkinnedMeshRenderer-bones.html)

## Local integration test (after CI and merge)

1. Pull `main` in `B:\Research\CutsceneAI\CutsceneAI`.
2. Regenerate `Benchmark002.cinetwin.sampling-plan.json` from the **same frozen
   CSIR** using `python tools\cinetwin.py plan`. Expect 298 timestamps, 29
   entities and two requested skeletal rigs.
3. In Unity, open Benchmark002, enter Play Mode, select `CUTSCENE_DIRECTOR`
   and use the same CineTwin behavior capture menu. Select the newly regenerated plan.
4. Exit Play Mode. Do not save Benchmark002.
5. Run `python tools\cinetwin.py verify "<plan>" "<capture>"`.
   The capture should report `skeletal_rig_count: 2` and `failures: []`
   if all skeletal references are resolved.

The global result should still be `INCOMPLETE` while audio output, event
execution, rendered frames and physics remain unverified.

This phase was tested in Python CI only until manually compiled/exercised in Unity.
