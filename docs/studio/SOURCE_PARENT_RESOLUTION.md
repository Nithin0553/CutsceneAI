# CutSceneAI — Unity source parents and world-space conversion policy

## Observed Benchmark002 result

After an Unreal save/reopen, the Studio transfer showed 18/18 saved assets,
10/10 mapped actors, and **2/2 native mapped direct parent links** checked.
Eight other mapped actors have no *independently mapped source parent actor*.

A previously uploaded Benchmark002 Unity CSIR includes an organizational root
GameObject, Benchmark002, and CHARACTER_A/CHARACTER_B child groups. The root is
not an identity transform: its Unity world position is approximately
(0.01705, 0, -5.90216) meters. Blindly creating another parent in Unreal
and putting previously world-space-baked children beneath it would change
their evaluated motion. The current trial's exact CSIR hashes must still be
checked before treating the earlier export as identical.

## Automatic source parent classification (implemented)

The read-only package module source_parent_resolution.py analyzes the approved
source CSIR and *actual prepared transform actions*. It records each mapped
child, exact missing parent entity IDs, the complete source ancestor chain,
and whether a parent is a plausible static organizational group.

Static-group candidates require a finite, invertible world TRS; active source
GameObject; no animated track bound to the ancestor; no captured animator or
known explicit script/physics/constraint dependencies. This is limited proof
about represented Timeline source data, not a guarantee that Unity scripts
could not animate a GameObject at runtime.

Actions classify into:

- STATIC_WORLD_POSE_REPRESENTED_UNVERIFIED: static source world pose appears in
  the prepared actor transform track. Initial placement is authored, but
  independent target readback and dynamic equivalence remain unverified.
- CSIR_PARENT_COMPOSED_WORLD_CURVE_PLANNED_UNVERIFIED: the native CSIR adapter
  composed Unity parent transforms into authored world curves; a native target
  motion comparison is required.
- CAPTURED_WORLD_MOTION_PLANNED_UNVERIFIED: source-evaluated CineTwin world
  motion is prepared, but native Unreal playback has not been compared.
- CHILD_WORLD_BEHAVIOR_UNVERIFIED: no sufficiently evidenced world action.
- PARENT_BEHAVIOR_UNVERIFIED: the source ancestor might animate or has unknown
  properties; automatic omission is not evidence of equivalence.

The current hierarchy audit reports the real ancestral groups and the
classification for each of the eight missing native parent records. New
prepared transfer coverage reports include the same source strategy summary.

**World-space flattening is a valid target representation for a supported
static scene grouping at the level of visual motion. It is not an editable
reconstruction of the original source parent hierarchy.** Do not relabel
full native hierarchy transfer as PASS merely because an actor's world pose
was planned. Fidelity always requires independent matching-time observation.

## Next implementation: editable source group actors (#85)

The safe next capability is reconstructing static organizational groups as
editable Unreal parent actors, with world-to-parent-local key conversion.
Animated or scripted parent groups additionally require source-evaluated
CineTwin samples. Complete actor-group reconstruction must preserve source
entity IDs, camera paths, skeletal root ownership, prop attachments, scale
and parent save/reopen persistence, and reject unprovable behavior instead of
writing an incorrect cutscene.

Issue #68 covers source hierarchy representation; #85 tracks the additional
editable group actors, and #72 governs independent behavioral validation.
Benchmark001 must remain frozen. Do not regenerate/overwrite the already
saved successful test sequence just to collect this source classification.
