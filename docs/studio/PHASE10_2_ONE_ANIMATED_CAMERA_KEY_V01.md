# Phase 10.2 — Guarded Single Animated CineCamera Position-Key Repair (v0.1)

**Software-only adapter scope:** one user-approved, source-proven, **already-keyed**
Unreal CineCamera world **X/Y/Z location key** at exactly one interior display
frame. This is the ninth narrowly guarded repair family, **not** arbitrary
animation-curve repair or full moving-camera fidelity.

**Engine acceptance:** **NOT VERIFIED**. Synthetic Python fixtures do not
prove that Unreal Editor's Sequencer key API, asset save/reopen, independent
CineTwin remeasurement or rendered camera trajectory is correct.

## Why this scope

The prior [source-frame camera trajectory contract](PHASE10_2_ANIMATED_CAMERA_FRAME_GRID_V01.md)
already transfers one Unity-authored camera as a full baked frame grid. But
native post-generation repairs must not assume the same actor's base transform
is the motion owner. This new adapter changes **one existing Sequencer
scripting key value** on the exact originally staged camera binding. It
never moves the actor, inserts/removes keyframes, changes frame time, alters
rotation/scale/lens, or edits camera-cut sections.

## Evidence and deterministic authorization

1. Original source CSIR, mapping, source CineTwin capture, prepared transfer
   plan and Element 3/4/5 occurrence authorization must still match their
   saved file digests and exact job/candidate.
2. Element 6 must have the original builder completion proof. Element 7 must
   recompute independent native CineTwin results from **a distinct reopened
   editor process**, target project/package readback and identical sampling
   plan. Element 8 must identify the camera **entity occurrence** as one
   independently measured `WORLD_POSITION_OUTSIDE_TOLERANCE` with no
   competing rotation, native lens or camera-cut mismatch.
3. Exactly one mapped source `entity.camera`, one active camera transform
   source track, one unparented camera, and one complete native action of
   strategy `verified_cinetwin_camera_world_pose`. The original action must
   be derived from the **evaluated** Unity world trajectory, not guessed
   local curves. No prior Element 8 remeasurement or auto-retry budget use is
   acceptable for this first narrow adapter.
4. Every source display-frame pose must match the originally prepared
   native XYZ camera keys (0.1 cm), with matching source/native quaternion
   orientations (0.2°) and unit scale. The source camera must genuinely
   move at least 10 cm. Exactly **one interior** key at exactly **one XYZ
   axis** may have a native discrepancy between **3 and 30 cm**. Every
   other XYZ channel/frame must agree within 0.15 cm.
5. An eligible user explicitly asks to **fix an animated/moving camera
   position keyframe**, not a whole curve, multiple keys, shots, camera
   rotation, rig, scale, FOV, blend or timewarp. The deterministic intent
   router restricts the LLM's options to `report_only` and the installed
   `restore_single_animated_camera_position_key` strategy. The model
   receives no file path, key values or native mutation API. A native request
   contains only feedback ID, exact source occurrence and a digest of the
   recomputed evidence.
6. The Unreal executor independently reloads the exact current feedback,
   recomputes the entire Element 7/8 source/native proof, and confirms its
   digest. No generic model command, numeric parameters or exception-based
   permission exists. Existing job identity, expected project and level,
   automatic setup, one-time repair claims and max-two-receipts policy
   remain in the native executor.

## Native Sequencer key ownership / mutation

Before editing, the native code checks:

- The exact original `CineCameraActor` newly staged UObject path and label
  from the source-linked automatic setup receipt, resolved through
  `MovieSceneSequenceExtensions.locate_bound_objects` in the current editor
  world, not matched only by display label.
- No competing actor-binding transform/property track, parent/child
  attachments, nested shot, ControlRig, timewarp or unknown master-track
  writer. Exactly one source-generated `MovieScene3DTransformTrack` and
  section belong to that camera actor.
- Nine native transform channels, exactly all original consecutive
  display-frame source keys in the six Location/Rotation channels, and
  three scale channels without extra authored keys and with **unit
  defaults**. Native values match the immutable source plan in **every**
  channel and frame except the one separately measured source/native
  XYZ discrepancy. Any changed native key, extra/partial key, re-timing,
  alternate rotation values, or unknown channel **refuses** the repair.
- Changes only one `MovieSceneScriptingDoubleKey.set_value`. Fresh complete
  six-channel readback must then exactly match the original source plan.
  Saves the **generated Level Sequence asset** with a confirmed return.
  On failed setter, extra changes, readback or save, restores the old key
  in a `finally` block; a disk save exception is **not** a proven
  persisted rollback, so the run remains failed / manual inspection needed.

The native receipt is
`ONE_ANIMATED_CAMERA_POSITION_KEY_SAVED_REOPENED_CINETWIN_PENDING`, with
one changed key, source occurrence/digest and exact keyed-track readback
status. It explicitly leaves **source/target time-grid CineTwin
remeasurement after repair**, persistence in a **new editor process**,
rendered camera motion and full cutscene fidelity **false**.

## Negative and synthetic regression tests

Source/domain isolation (other changed XYZ frames, additional axis,
rotation, scale, stale/missing frame, missing source-to-plan parity, wrong
actor label), single-key user consent and repair-budget limits, a complete
nine-channel native key grid, extra/missing/reordered/subframe keys, unknown
scale defaults, other rotation/position channel changes, native save
failure rollback and a setter that mutates before throwing.

**Still unsupported**: repairing more than one key, multiple animated
cameras, source-authored weighted curves, animated camera orientation,
camera rigs, complex Timeline overlaps/blends, nested cinematic shots,
component-relative transforms, cinematic look matching, rendered image
parity and true general autonomous moving-camera repair. Those remain
report-only until separate native mutation and post-edit readback
contracts are implemented and real-editor tested.

See [Release Acceptance](RELEASE_ACCEPTANCE.md).
