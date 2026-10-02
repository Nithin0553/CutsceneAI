# Unreal Adapter Compatibility Ledger

This ledger is persistent engineering memory for incompatibilities discovered during
real CutSceneAI engine-transfer runs. Each incident must produce a code fix and a
regression guard so the same failure signature is not reintroduced.

## UE58-001 — Skeletal animation play rate

- **Observed:** Unreal 5.8 rejected a Python `float` assigned to
  `MovieSceneSkeletalAnimationParams.play_rate`.
- **Error signature:** `Cannot nativize 'float' as 'MovieSceneTimeWarpVariant'`.
- **Root cause:** Unreal 5.8 represents skeletal animation play rate with
  `MovieSceneTimeWarpVariant`.
- **Permanent fix:** route play-rate construction through
  `unreal_compat.make_fixed_play_rate()`, using `set_fixed_play_rate()` on 5.8.
- **Regression guard:** `tests/unreal/test_unreal_builder_ue58_contract.py`.

## UE58-002 — Sequencer section channel access

- **Observed:** `MovieScene3DTransformSection` has no `get_channels()` method.
- **Error signature:** `AttributeError: 'MovieScene3DTransformSection' object has no attribute 'get_channels'`.
- **Root cause:** Unreal 5.8 Sequencer Scripting exposes the supported channel query as
  `GetAllChannels` / Python `get_all_channels()`.
- **Permanent fix:** all channel access goes through
  `unreal_compat.get_section_channels()`, which prefers the 5.8 API and retains
  compatibility fallbacks.
- **Regression guard:** the builder contract test forbids direct `.get_channels()`
  usage in the Unreal builder.

## UE58-003 — CineCameraActor component access

- **Observed:** `CineCameraActor` did not expose `get_camera_component()` in the
  Unreal 5.8 Python wrapper.
- **Error signature:** `AttributeError: 'CineCameraActor' object has no attribute 'get_camera_component'`.
- **Root cause:** CineCameraActor exposes the specialized
  `get_cine_camera_component()` API, and reflected/editor APIs can differ from the
  base CameraActor wrapper even when the native C++ class inherits from CameraActor.
- **Permanent fix:** camera resolution is capability-driven through
  `unreal_compat.resolve_camera_component()`. It probes the cine-camera helper,
  generic camera helper, reflected `camera_component` property, and component-class
  discovery instead of assuming one actor method.
- **Preflight:** camera component resolution and lens-conversion feasibility are checked
  before scene preparation or Level Sequence creation.
- **Regression guard:** `tests/unreal/test_unreal_builder_ue58_contract.py`.

## CAMERA-001 — Unity/Unreal FOV convention mismatch

- **Observed during review:** the source curve is Unity `Camera.fieldOfView`, which is
  vertical FOV, while Unreal `CameraComponent.FieldOfView` is horizontal.
- **Risk:** copying the same numeric degrees would produce different framing even if the
  code ran without errors.
- **Permanent fix:** the reconstruction plan declares `source_fov_axis=vertical`.
  CineCameraComponent targets convert vertical FOV to `CurrentFocalLength` using
  filmback sensor height; generic CameraComponent targets convert vertical FOV to
  horizontal FOV using the target aspect ratio.
- **Outcome:** the adapter preserves camera semantics instead of only matching property
  names.

## CAMERA-002 — Static camera framing was not fully realized

- **Observed after the first successful Benchmark001 generation:** the source CSIR
  preserved static camera metadata, but the generator only animated Camera B lens data
  and did not realize Camera A's static FOV or either camera's source aspect ratio.
- **Source evidence:** Benchmark001 CAM_A has vertical FOV 60 degrees and aspect
  4.93486166; CAM_B starts at vertical FOV 35 degrees with the same aspect.
- **Risk:** the generated sequence can be structurally correct while the shot framing is
  visibly different from Unity.
- **Permanent fix:** every mapped camera now receives a `camera_setup` action carrying
  source projection, vertical FOV, aspect, and clip-plane provenance. CineCamera targets
  preserve aspect through filmback and realize FOV as focal length; generic cameras
  preserve aspect and convert vertical FOV to horizontal FOV.
- **Preflight:** camera setup feasibility is validated without mutating the target.
- **Regression guards:** camera-plan and Unreal-builder contract tests.

## ANIM-001 — Imported root motion can use a different forward basis

- **Observed after successful Benchmark001 generation:** the source walk/turn clip played
  correctly, but the guard travelled in the wrong world direction.
- **Root cause:** matching the source animation asset by identity is not sufficient to
  guarantee that its imported target root track uses the same engine-space forward basis.
  The source CSIR already contains Unity `RootT.x/y/z` curves, so direction should be
  calibrated from data rather than guessed from engine conventions.
- **Permanent fix:** the plan derives expected source root displacement from `RootT`,
  converts it to target world axes, then the Unreal adapter samples the imported target
  animation root track and computes the minimal horizontal yaw needed to align the two.
  The correction is applied as the Sequencer section's root-motion rotation offset; the
  imported animation asset itself remains unchanged.
- **Preflight:** expected and target root displacements plus the computed yaw correction
  are logged before target mutation.
- **Regression guards:** pure root-motion alignment tests plus Unreal adapter contract
  checks.

## ANIM-002 — Skeletal section post-clip pose preservation

- **Observed, first pass:** after the 3.25 second character animation finished, the
  target character returned to its reference/T-pose.
- **First attempted fix:** `KeepState` prevented the reference-pose restore, but at
  frame 199 (four frames after the 195-frame clip end at 60 fps) the held skeletal state
  was visibly invalid: the guard was lying on the ground.
- **Revised root cause:** completion mode controls what happens when a section stops
  evaluating; it does not itself guarantee that the skeletal section continues
  evaluating the animation's final frame after the section range. Unreal's Animation
  Track documentation defines post-roll as padding that holds the last animation frame.
- **Permanent fix for the frozen benchmark:** preserve `KeepState` as the completion
  policy and add explicit skeletal post-roll from the source clip end through the
  cutscene end, so the last animation frame remains evaluated during the intended pause.
- **Future extractor requirement:** preserve Unity Timeline pre/post-extrapolation
  explicitly in CSIR so future transfers can map source completion semantics rather than
  rely on this legacy benchmark fallback.
- **Regression guard:** the planner carries `hold_end_frame` and
  `hold_strategy=post_roll_last_frame`; the Unreal compatibility layer owns the
  version-adaptive post-roll setter.

## CAMERA-003 — Unity observed Camera.aspect is not a safe camera intrinsic

- **Observed:** preserving the frozen source `Camera.aspect` value produced an
  extremely wide CineCamera filmback and strong letterboxing in the Unreal viewport.
- **Root cause:** Unity's observed camera aspect can reflect the active Game/editor view.
  Treating that runtime value as an authored lens intrinsic makes target framing depend
  on the source editor window rather than on a controlled validation output.
- **Permanent fix:** keep the observed source aspect as provenance only. Camera
  realization now uses an explicit `output_resolution` gate from the mapping; the
  Benchmark001 default is 1920x1080 when no mapping value is supplied.
- **Outcome:** vertical FOV remains source-derived while horizontal framing becomes
  reproducible for a declared validation resolution.

## UE-PY-001 — Rotator positional argument semantic mismatch

- Observed: Benchmark001 CAM_A_Wide arrived with an approximately 25 degree sideways roll. Setting that roll to zero manually restored the intended level horizon.
- Source evidence: the Unity camera had an approximately 25 degree X pitch and no authored roll.
- Root cause: the Unreal Python Rotator wrapper exposes constructor fields in roll, pitch, yaw order, while native C++ FRotator documentation describes its three-value constructor as pitch, yaw, roll. The adapter passed positional values and therefore assigned semantic components incorrectly.
- Permanent fix: all Unreal Rotator construction now routes through unreal_compat.make_rotator_semantic() using explicit named roll=, pitch=, yaw= fields. The adaptive mapping rule requires the rotator.semantic_fields capability and explicitly forbids positional constructor assumptions.
- Scope: this also fixes skeletal root-motion yaw offsets, which had used a positional Rotator call.
- Regression guard: the Unreal contract test rejects the old positional patterns.
## CAMERA-004 — Canonical-to-Unreal pitch sign regression

- **Observed:** after switching Unreal Rotator construction to explicit semantic fields, Benchmark001 CAM_A_Wide no longer rolled sideways, but it looked upward and the first shot became mostly sky.
- **Source evidence:** the frozen CSIR camera quaternion represents the Unity-authored +25 degree X camera pitch (a downward-looking camera).
- **Root cause:** the canonical quaternion basis conversion was correct, but the generic Euler-matrix extraction used the wrong sign for Unreal Pitch. Unreal defines positive Pitch as nose-up; the source camera needs approximately -25 degrees in Unreal.
- **Permanent fix:** derive Unreal Roll/Pitch/Yaw from the converted target forward and right basis. Pitch is now atan2(forward.z, horizontal_length), yaw comes from the horizontal forward vector, and roll is measured relative to the zero-roll target basis.
- **Regression guards:** Unity +25 X camera rotation must resolve to Unreal Pitch=-25, Yaw=0, Roll=0; independent yaw and roll tests are also included.

## ANIM-003 — Root-motion trajectory correction must not use skeletal section orientation

- **Observed:** character trajectory alignment was implemented through MovieSceneSkeletalAnimationSection.start_rotation_offset; subsequent generated frames could leave the character with an invalid body orientation during/after the animation.
- **Root cause:** root-motion travel direction is a world-trajectory concern, while a skeletal-section rotation offset is evaluated in animation/root-bone space. Treating those spaces as interchangeable is unsafe for imported rigs.
- **Permanent fix:** CutSceneAI still measures source and imported-target root displacement, but applies the resolved horizontal yaw to the mapped character actor around Unreal world-up (+Z). The skeletal animation section is no longer rotated for trajectory correction.
- **Adaptive rule:** animation.root_motion now requires actor-world yaw calibration and explicitly forbids skeletal-section rotation for this purpose.
- **Regression guard:** the builder contract requires actor-world alignment and rejects the previous apply_skeletal_root_yaw(section, yaw) path.
## Failure-handling rule

The Unreal builder now deletes an incomplete generated Level Sequence when a build
exception occurs. Source CSIR remains immutable; level actor preparation is deterministic
and can be safely reapplied on the next run.

## Rule for future incidents

For every new engine/API failure:

1. Record the exact error signature here.
2. Identify the engine-version/API cause.
3. Centralize the compatibility behavior instead of scattering one-off workarounds.
4. Add a regression test that fails if the old mistake returns.
5. Keep the generated target disposable and reproducible from the frozen CSIR.
