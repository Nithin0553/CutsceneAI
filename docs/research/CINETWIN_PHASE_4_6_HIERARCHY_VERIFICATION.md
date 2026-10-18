# CineTwin Phase 4.6 — Independent sampled hierarchy behavior verification

## Runtime evidence

The copied Unreal test project successfully generated
`LS_Benchmark002_CineTwin_Test` with the mapped source relationship
`PROP_PARENTED → PROP_MOVING`, after automatically making the child mesh
movable.

Its five-time tick-synchronized observer confirmed that:

- both parent and child **actors** moved 300.000 cm;
- both corresponding components moved 300.000 cm;
- the child's actor attachment matched the source parent.

These observations verify actual motion propagation, **not** full source/target
placement fidelity. Epic's attachment rule `KeepWorld` preserves the world
transform when the attachment is established, but it does not guarantee
the authored source parent-relative offset:

- https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/EAttachmentRule
- https://docs.unity3d.com/6000.0/Documentation/ScriptReference/Transform.InverseTransformPoint.html

## New automatic comparison

`packages/cinetwin/hierarchy_verify.py` compares the original Unity
behavior capture against the independent Unreal tick-synchronized capture.
The verifier is intentionally **read only**, and does not run either engine.

For every directly mapped parent-child pair it compares, at every target
observation timestamp:

1. Target attachment actually exists and points to the expected mapped parent.
2. Source and target **child world positions**.
3. Source and target **child offsets expressed in the parent's local frame**,
   accounting for the captured parent quaternion and scale.
4. Parent world-position disagreement, to separate root placement error from
   the child's relative offset error.

It rejects inconsistent CSIR provenance, missing parent/child entity IDs,
invalid or nonmatching sample times, missing attachment readback, nonfinite
coordinates and invalid parent transforms.

Defaults: **1 cm diagnostic tolerance** for child world position and
parent-relative offset. These are research thresholds, not universal cinematic
perceptual guarantees.

It reports `MATCH_AT_SAMPLED_TIMES` or `MISMATCH_DETECTED`, plus
per-timestamp measurements. It does **not** treat five sampled instants
as full 298-time or full-render fidelity; source actor parenting may involve
shear, constraints, physics or dynamic reparenting not represented in a
position/quaternion/lossy-scale (TRS) capture.

## Next local verification (one step)

Keep the copied Unreal test editor open, and **do not save** its modified
level yet. In VS Code PowerShell, after pulling the new main branch, run:

```powershell
python tools\cinetwin.py hierarchy-verify `
"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002.cinetwin.sampling-plan.json" `
"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002_Timeline.cinetwin.behavior.json" `
"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002_CineTwin_HierarchyValidation.json" `
"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002_CineTwin_HierarchyPlan.json" `
"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002_CineTwin_OffsetComparison.json"
```

The script prints both local-offset and child-world errors. A nonzero exit
code means evidence was invalid or sampled mismatches exceeded tolerance;
the JSON report is still written for a measured mismatch.

If the local attachment matches but the child world position differs, address
the parent's start pose/trajectory first. If local offset is also incorrect,
investigate the first-key initialization, KEEP_WORLD basis and local-to-world
transfer rule; do not insert arbitrary world-space correction keys before
the evidence explains the cause.

Remaining source parents that are not mapped independently remain unresolved.
This is not a validation of character bone pose parity or of camera/lights/audio.
