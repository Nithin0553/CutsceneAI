# CineTwin Phase 4.5 — Mobility-compatible hierarchy reconstruction

## Runtime issue resolved by this change

The staged Unreal 5.8.3 reconstruction reached the planned `PROP_PARENTED → PROP_MOVING`
actor attachment, but Unreal refused the operation because a **Static**
`StaticMeshComponent` child cannot be attached beneath an animated/movable
parent. The error is an Unreal mobility constraint, not evidence of invalid
Unity source hierarchy.

References:
- [UE5.8 Actor Mobility](https://dev.epicgames.com/documentation/unreal-engine/actor-mobility-in-unreal-engine)
- [UE5.8 SetMobility](https://dev.epicgames.com/documentation/unreal-engine/API/Runtime/Engine/USceneComponent/SetMobility)
- [UE Python SceneComponent.set_mobility](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/SceneComponent?application_version=5.7)

## New reusable logic

When opt-in hierarchy reconstruction is enabled:

1. Before any new attachment, resolve all involved actor `SceneComponent` trees,
   read and validate their `mobility` enum, and verify `set_mobility` support.
2. Record **all** original component mobility states before making changes.
3. Promote only non-Movable components belonging to involved animated parents
   and attached child actors to `ComponentMobility.MOVABLE`.
4. Verify the mobility changes, prepare the authored parent starting transform,
   attempt `KEEP_WORLD` attachment, and verify the parent by readback.
5. If anything fails, detach newly attached children, restore previously
   captured component mobility, and restore initialized parent transforms.

This behavior is **not** enabled by default. It only runs with the explicit
`enable_cinetwin_hierarchy=true` target mapping option.

Converting a StaticMeshComponent from Static to Movable changes its lighting
and shadow behavior: baked static lightmaps no longer apply in the same way.
A correct cutscene transfer requires movable props to actually move, but
rendered-lighting fidelity must be checked independently.

## Staged Unreal trial

Use only the already-copied test project
`CutSceneAIStudio_CineTwin_Test`. The previous failed build did not create
a complete new sequence, but it already prepared several actors in **editor
memory** before the attachment error. Close the test project without saving
the level, then reopen the copy from disk before retrying.

The existing opt-in test mapping generates
`/Game/CutSceneAI/Benchmark002/LS_Benchmark002_CineTwin_Test`, with
`overwrite_sequence=false`. Keep the original `LS_Benchmark002`
unmodified.

After the patch is merged and pulled, rerun the same project-guarded Unreal
Python builder. Confirm both:

- a log line `[CineTwin] Prepared movable hierarchy components for PROP_PARENTED`;
- a log line `[CineTwin] Verified actor attachment PROP_PARENTED -> PROP_MOVING`.

Then use the tick-synchronized source-versus-target observer to **prove the
child's effective world trajectory**; a successful attachment alone is not
equivalent to motion fidelity. Do not save the level until this is verified.

Python CI tests simulate mobility promotion and rollback, but the actual
runtime code is still experimental until confirmed in the user's UE5.8.3
editor.

Remaining limitations: physics-simulated attachments, mesh baking, event-driven
reparenting, source transform proxies, and visual shadow parity require
additional specialized validation.
