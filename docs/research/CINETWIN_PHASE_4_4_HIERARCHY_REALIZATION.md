# CineTwin Phase 4.4 — Safe, opt-in Unreal hierarchy realization

## Evidence and purpose

A source-derived read-only hierarchy plan from the frozen Unity Benchmark002
reported exactly **one directly mapped actor attachment**:

- `PROP_PARENTED` must inherit motion from `PROP_MOVING`, using `KEEP_WORLD` attachment.

The plan also reported **seven unresolved source parents**. Those are not
blindly attached, and unresolved groups may eventually require independent
transform proxies or component-level correspondence.

An Unreal tick-synchronized motion-layer probe previously found that the
parented prop did **not** have the expected actor attachment. This change
adds a generic attachment capability to the Unreal reconstruction builder.

## What is implemented

Pure-Python planner: `packages/cinetwin/hierarchy_realization.py`.

- Starts with the existing source-ID-aware hierarchy plan.
- Sorts parent-child edges so parents are processed before children.
- Refuses children that have independent **world-space** transform tracks or
  explicit sampled root correction tracks; these require local-space
  conversion and cannot be safely combined with an actor attachment yet.
- For animated parents, finds the first authored world transform key and
  positions the parent at that pose *before* the child is attached. This
  avoids calculating the child's local offset against an unrelated editor pose.
- Does not bypass missing hierarchy nodes, infer unknown sockets or weld
  physics bodies.

Unreal runtime adapter: `integrations/unreal/cinetwin_hierarchy_runtime.py`.

- Looks up unique mapped target actors.
- Refuses to overwrite a different existing parent attachment.
- Uses `Actor.attach_to_actor` with `AttachmentRule.KEEP_WORLD` for all
  transform channels and `weld_simulated_bodies=False`.
- Immediately reads `get_attach_parent_actor()` to verify that Unreal
  established the requested relationship.
- Records newly attached children and initialized parent transforms so
  failures later in sequence construction can roll back those changes.
- Leaves the source scene and CSIR untouched. The adapter does **not** save
  the Unreal level.

Official Epic API references:

- [Actor.attach_to_actor / detach_from_actor](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/Actor?application_version=5.6)
- [AttachmentRule.KEEP_WORLD](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/AttachmentRule?application_version=5.0)
- [Dynamic Sequencer transforms](https://dev.epicgames.com/documentation/unreal-engine/creating-level-sequences-with-dynamic-transforms-in-unreal-engine)

## Safety boundary: DISABLED BY DEFAULT

The builder uses this feature only if the **target mapping** explicitly
contains `"enable_cinetwin_hierarchy": true`. Without that setting, the
existing reconstruction behavior is unchanged.

Do not enable or execute a full rebuild on the only copy of an Unreal project.
The current generator may intentionally replace a Level Sequence if
`overwrite_sequence` is enabled, and it prepares actors in the editor level.
That replacement cannot automatically recover an earlier sequence's original
content on all failures. Use an **isolated, backed-up target working copy** and
prefer a new sequence asset path while testing.

The generic attachment operation is not equivalent to a complete source
hierarchy if scene object instances are represented by components, hierarchy
proxies, sockets, simulated physics or time-changing parenting. These remain
explicitly unsupported.

## Independent acceptance test (planned after local backup)

1. Reconstruct a test target with the opt-in flag enabled using the same
   source CSIR.
2. Inspect direct actor attachment readback and ensure the expected parent
   is present.
3. Use the tick-synchronized observer with `capture_motion_layers=True`
   over timestamps spanning the parent's movement. The effective world
   position of the child **must** follow the source's evaluated child
   trajectory; parent identity alone is insufficient.
4. Only after those checks succeed, approve the generated target copy and
   decide whether to save the target level.

No standalone Unreal runtime test was possible in GitHub CI. Unity source
and benchmark assets remain frozen.
