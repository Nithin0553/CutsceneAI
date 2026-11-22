# CutSceneAI Studio — Source-bound position and facing audit

**Component under review:** Unity canonical source transform → Studio transfer plan → Unreal Sequencer/native actor → independent CineTwin readback.  
**Software verification only:** Unity and Unreal were **not launched** for this audit. Live character orientation, imported mesh forward basis and rendered-frame fidelity remain unverified pending the separately authorized editor-testing phase.

## Authoritative spatial contract

- CSIR canonical world: right-handed, meters, +Y up, -Z forward, normalized quaternion `[x, y, z, w]`.
- Unreal: centimeters, +Z up and +X forward. Canonical position `(x,y,z)` becomes Unreal `(-100z,100x,100y)`; scale axes are permuted without negating scale.
- Roll/Pitch/Yaw are *Unreal semantic* channels, not Unity Euler channels. Quaternion signs `q` and `-q` describe the same facing orientation.
- Parent-local motion uses measured source parent and child **world** transforms; Unreal native transform keys are local to the attached target actor. Without this evidence, an animated attached actor cannot be claimed to preserve source world facing.

## Reviewed source-to-target paths

| Area | Source/implementation | Outcome |
| --- | --- | --- |
| Unity extraction | `UnityTimelineExtractor.cs`, `ExtractorUtilities.cs`, `CineTwinBehaviorCapture.cs` | Source world transform and quaternion data already exposed in canonical axes; capture remains the authority for evaluated animation |
| Basis and quaternion math | `integrations/unreal/csir_plan.py`, `readback_math.py` | Verified position/unit and quaternion-Euler basis mapping; reject zero-length/non-unit/nonfinite facing data instead of inventing identity |
| Baked world actor motion | `packages/studio/transfer_backend.py` | Reject repeated source timestamps/entity IDs; convert measured frames with rotation continuity and preserve the measured playback-end boundary |
| Source-owned moving character | `packages/studio/character_motion.py` | Use the same rotation continuity for the approved actor-owned motion strategy; existing root double-ownership checks remain mandatory |
| Attached child actors | `packages/studio/hierarchy_local.py` | Convert measured world poses into parent-local position/quaternion; preserve end boundary; refuse incomplete source evidence |
| Source/static scene placement | `integrations/unreal/scene_prep.py`, `csir_plan.parent_world_transform` | Missing parent identity/transform or incomplete static pose now refuses instead of placing objects at the origin with a guessed orientation |
| Native Sequencer transform | `integrations/unreal/build_level_sequence.py` | Keep the actual end-boundary key inside the transform section for interpolation during the last active frame interval |
| Native readback and comparison | `readback_level_sequence.py`, `cinetwin_target_evaluator.py`, `packages/cinetwin/behavior_compare.py` | Existing readback maps native RPY to canonical quaternion; independent matched-frame actor rotation errors are already measured, with `q`/`-q` equivalence |

## Defects corrected

1. **False half-turn while tipping or rotating vertically.** At +90/-90-degree pitch, an equivalent Unreal RPY decomposition can jump 180 degrees in *both* roll and yaw. The old per-axis unwrap could interpolate a huge false turn even though adjacent source quaternions differ by only 2 degrees. New `csir_plan.continuous_unreal_rotator` chooses the nearest of two mathematically equivalent Euler triples and is shared by authored track, measured world, moving-character and parent-local paths.
2. **Phantom facing from malformed source.** Zero-length source quaternions previously became identity silently. Static and sampled actor rotation now refuses nonfinite/non-unit input. No AI-generated offsets or alternative actor axes are inferred.
3. **Phantom world origin from a missing parent or incomplete source metadata.** Source children and static actors no longer obtain a default identity parent/world placement when their recorded transform is required but absent.
4. **Independently animated attached child silently omitted.** Missing parent metadata can cause native planning to refuse; without a verified source capture, the fallback must **block** rather than quietly skip the child transform action. With a verified capture, the existing measured parent-local strategy remains eligible.
5. **Last-frame position/facing incorrectly held.** Source sampling includes the exclusive playback-end boundary, but some actor and child baking paths omitted it. The final key now comes from the actual source sample and the native Sequencer transform section includes it for interpolation up to the end of playback. This also applies to turning cameras.

## Synthetic regression gates

`tests/studio/test_spatial_orientation_continuity.py` covers 89→91→93-degree pole crossing in source/target round-trip matrices, baked world actors, selected moving-character trajectories and attached children; invalid source quaternions, capture identity duplicates, static placement and parent evidence refusal, and quaternion sign equivalence. Existing `test_transfer_backend.py` verifies complete source-grid boundary keys for moving props, attached children and cameras. Other existing motion, hierarchy and engine API double tests remain in the full CI suite.

These checks establish **software math and evidence behavior**, not live actor, animation, imported FBX mesh forward-axis, IK rig bind-pose or rendered image parity. A target skeletal actor can have the correct actor world quaternion while its mesh's local forward direction differs because of FBX/import or component-relative orientation. The later editor acceptance must observe that separately and refuse unsupported rigs rather than applying a guessed 90/180-degree correction.

## Later editor acceptance (deferred)

In the already-connected Unity and Unreal editors, observe held-out examples of (a) static character facing, (b) continuous turning/moving actor, (c) camera following/vertical pitch, (d) attached child with changing parent orientation, and (e) clip final-frame motion. Compare independent actor and skeletal-root world orientation, mesh/component basis where available, and rendered-view evidence. Preserve original source project, use an isolated target and never replay an uncertain native job.

**This audit does not declare `SOFTWARE_READY_FOR_ENGINE_TEST` and does not merge to `main`.**
