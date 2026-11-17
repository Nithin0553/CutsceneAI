# Static collider geometry in Studio

This adapter stages editable Unreal shape volumes from a fresh Unity feature
census. Studio matches the census project and native GameObject and component
IDs to the selected CSIR. It uses the authored world center, orientation, and
dimensions to construct a new volume in the staged Unreal map alongside the
editable Level Sequence. Box, sphere and capsule use one planner and one
native staging and readback route.

| Unity source | Unreal representation | Translation |
| --- | --- | --- |
| BoxCollider | TriggerBox with BoxComponent | Permute the local axes and convert full widths in meters to half extents in centimeters |
| SphereCollider | TriggerSphere with SphereComponent | Convert the captured world radius to centimeters |
| CapsuleCollider | TriggerCapsule with CapsuleComponent | Rotate the native capsule axis to the captured Unity direction and convert the total height to half height |

The declared build scope is Unity 2022.3 or 6000.0–6000.3 and Unreal 5.8 with
the required Python APIs. Automated checks exercise Python planning and
simulated Unreal APIs. Unity compilation and native Unreal editor runs are
pending.

Use a mapped, active static GameObject whose hierarchy has no active Timeline
binding or attached rigidbody or articulation body. The Unity scanner rejects
sheared or mirrored transforms for native planning. The capsule route requires
uniform positive scale. Captures made before the orthogonal-transform and
owner-state fields were added remain readable for the source audit, and need
re-export for shape planning.

The target volume is a world-space authoring snapshot. It uses the
`NoCollision` profile with actor collision and overlap events disabled.
Source enabled and trigger flags stay in the receipts. Runtime contact,
layer filtering, triggers, physics materials, dynamic motion, and MeshCollider
cooking have separate evidence requirements. PR #114 supplies MeshCollider
and LODGroup source capture.

## Real-editor acceptance

1. Use backed-up test projects and a fresh Unreal map. Install the Unity
   extractor from this branch. Confirm a clean compilation. Use a saved
   Timeline with a camera cut and an unanimated, mapped scene prop. To
   obtain automatic mapping, the prop can be a static scene renderer with a
   uniquely source-identified FBX as described in
   [Static Scene Source Transfer](STATIC_SCENE_SOURCE_TRANSFER.md).
2. Mark the GameObject Static. Add an offset BoxCollider with unequal
   dimensions. Save the scene and export both CSIR and a fresh feature
   census. Select both in Studio and prepare the automatic candidate.
   Verify the exact component global ID and `collider_primitive_shape` action
   in `transfer-plan.json`. In `coverage-report.json`, verify that the
   occurrence has a native plan and awaits native readback.
3. Start the matching Unreal companion, run the approved candidate and save
   the generated sequence and map. Inspect the new `CSAI_COLLIDER_…` volume
   and `component_operations` in the automatic setup receipt.
4. Close and reopen Unreal, load the exact saved map and sequence, and run
   Studio's persistence audit from Results. Check registered-component
   readback for observed geometry, class, unit scale, and collision state.
   The geometry comparison permits 0.0001 m of center or dimension error
   and 0.05 degrees of box or capsule orientation error. Keep the generating
   and observing editor process IDs and immutable reports.
5. Repeat with a different project containing a rotated parent, an offset
   sphere, and capsules in different directions, plus a light shadow
   property in the same transfer. Include a Timeline-bound or sheared
   collider and a MeshCollider as unsupported controls. Save those reports.
   Change one capsule dimension in a copy of the output and confirm that
   fresh readback reports the resulting error.

The measured scope is static geometry. Physics interaction and callback
parity need independently sampled results from actual interactions in
the two engines before these use cases can advance beyond geometry.
