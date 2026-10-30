# CutSceneAI Studio: best-effort transfer backend v0.1

## Goal and guarantees

This is a **real target generator** for source features supported by the
existing Unreal adapter, with explicit degradation/omission reports for source
features that cannot currently be converted. It is NOT a universal
game-engine-script or shader translator.

- Native CED/CSIR mapping stays deterministic; actual target asset/actor
  mapping and runtime APIs are checked inside Unreal.
- One unsupported source track cannot block planning other tracks.
- A valid CineTwin Play Mode capture can provide source-evaluated **world
  transform** samples for the affected actor across playback frames.
- A baked actor transform is not equivalent to skeletal joint animation, IK,
  mesh deformation, audio output, custom shader behavior, or scripts.
- Muted/inactive tracks are excluded and explicitly accounted for.
- Source data and output plan are hashed and recomputed before Unreal mutations.
- Best-effort target sequences cannot overwrite an existing Level Sequence.
- Source/target behavior is **not** accepted merely because a sequence exists.

The old strict generator is still available for high-fidelity transfers.
Use best-effort only when an explicitly reported partial output is acceptable.

## Step 1: create/read the source evidence (Unity)

Using existing extractor and CineTwin tools:

    Tools > CutsceneAI > Export Selected Timeline
    python tools/cinetwin.py plan SOURCE.csir.json SOURCE.cinetwin.sampling-plan.json
    Tools > CutsceneAI > CineTwin > Capture Selected Timeline Behavior (Play Mode)
    python tools/cinetwin.py verify SOURCE.cinetwin.sampling-plan.json SOURCE.cinetwin.behavior.json

Keep source CSIR untouched after capture; the behavior capture is anchored to
its exact SHA256. The source Timeline capture requires a disposable Unity
project/scene when user scripts have side effects.

## Step 2: create a read-only best-effort plan

    python tools/transfer_backend.py \
      --csir "<SOURCE.csir.json>" \
      --mapping "<LOCAL_TARGET_MAPPING.json>" \
      --capture "<SOURCE.cinetwin.behavior.json>" \
      --out "<NEW_EMPTY_TRANSFER_OUTPUT_DIR>"

The --capture option is optional. Without it unsupported motion cannot be
baked, and will be recorded as SKIPPED. With a verified capture, affected
mapped actors can receive evaluated actor-world transform keys.

Output files:

- transfer-plan.json: exact deterministic Unreal reconstruction actions.
- coverage-report.json: per-source-track outcomes NATIVE_UNVERIFIED,
  NATIVE_PARTIAL, BAKED_PARTIAL, INACTIVE or SKIPPED, plus unverified domains.
- evidence.json: exact source/mapping/capture identities and SHA-256 hashes.

**Do not rewrite any of these files after planning.** The runtime will
recompute the plan and refuse modified input.

## Hierarchy source conversion (moving parent + child)

When the mapping enables `enable_cinetwin_hierarchy=true`, the best-effort
planner reconciles source parent/child behavior before Unreal runs:

- A child with only a synthesized static source world pose has that redundant
  world-transform action removed. It inherits its parent's Unreal actor motion.
- A child with independent world-transform animation requires a verified
  CineTwin source capture. Both source world poses are sampled at each frame
  and converted to the child's parent-local transform using parent inverse TRS.
  Unreal's Sequencer TransformTrack receives those `PARENT_LOCAL` keys.
- Missing capture frames, zero-scale parents, unknown/foreign attachments,
  skeletal-root corrections or unexpected world tracks still block safely.
- `coverage-report.json` includes `hierarchy_reconstruction` naming the
  inheritance/conversion policy; child animation is `BAKED_PARTIAL`.
  Source/target dynamics and rendered fidelity remain unverified.

This change requires generating a fresh plan into a **new output directory**.
Do not reuse old plans or overwrite earlier failed runtime receipts.
Restart Unreal after pulling the new Python code; module imports are cached.

## Step 3: Unreal Engine runtime generation

Use a BACKED-UP copy of the Unreal target project and open the EXACT intended
level in Unreal Editor. Enable Python Editor Script Plugin and Sequencer
Scripting. Verify mapped actor labels and existing imported assets.

In Unreal Output Log, switch input to Python and run (substitute full paths):

    import sys
    sys.path.insert(0, r"B:\Research\CutsceneAI\CutsceneAI\integrations\unreal")
    import build_level_sequence

    sequence = build_level_sequence.build_prepared_files(
        r"D:\Path\To\SOURCE.csir.json",
        r"B:\Research\CutsceneAI\CutsceneAI\integrations\unreal\LOCAL_TARGET_MAPPING.json",
        r"D:\Path\To\Transfer01\transfer-plan.json",
        r"D:\Path\To\Transfer01\coverage-report.json",
        r"D:\Path\To\Transfer01\evidence.json",
        r"D:\Path\To\Transfer01\runtime-receipt.json",
        expected_project_path=r"D:\Research\Unreal\UnrealProjects\CutSceneAIStudio_CineTwin_Test\CutSceneAIStudio.uproject",
        expected_level_path="/Game/CutSceneAI/Benchmark002/L_Benchmark002",
    )

The backend verifies the loaded .uproject and open level, rejects
overwrite_sequence=true, recomputes the plan from frozen evidence and probes
Unreal's runtime capabilities/assets/actors BEFORE modifying the level. It
then creates the new Level Sequence and writes a machine-readable
runtime-receipt.json.

A successful runtime receipt reads GENERATED_UNVERIFIED, never PASS. If the
runtime preflight fails, no sequence is generated. Avoid rerunning a failed
build until the error is diagnosed; engine side effects must be reviewed.

WARNING: The current Unreal builder restores mapped actor transforms on
failure where possible, but it does not yet provide a complete project-level
transaction. Camera component changes, attachment state or assets changed
by external editor plugins may survive a failed attempt. Do not save
the target level until its results have been inspected.

## V7 runtime failure and source-easing recovery (2026-10-29)

A real Benchmark002 V7 Unreal 5.8.3 run passed source-bound plan verification, runtime capability preflight, actor preparation, camera setup and root-motion calibration, but **failed while building the first skeletal section** with `UnrealBuildError: Negative section easing duration.`

The Unity CSIR stores `native_payload.blend_in_seconds=-1` / `blend_out_seconds=-1` for *unset/no-blend* clips. The former planner propagated these negative sentinels to the Unreal sequence builder; Unreal `MovieSceneSectionEasingExtensions` requires nonnegative display-rate frame durations.

The corrected **pure Python planner** now:
- Interprets the documented source `-1.0` blend sentinel as *no explicit overlap blend*; uses a nonnegative source `ease_in_seconds` / `ease_out_seconds` value, if present, instead.
- Preserves positive authored crossfade durations.
- Rejects any other negative, nonfinite, or invalid source easing values at planning time.
- Adds Unreal-side early easing validation as defense in depth, *before* changing level actors or creating a Level Sequence.

A second V7 failure occurred during attempted rollback: the runtime called `EditorAssetLibrary.delete_asset()` on the incomplete Level Sequence while Unreal still held native references. Unreal reported `ForceDeleteObject failed` and a **potentially corrupt package**. The generator now refuses in-process force-deletion of a referenced, incomplete sequence; it logs `INCOMPLETE_UNSAVED_SEQUENCE` and makes best-effort actor pose/attachment restoration while leaving the session for manual recovery. This does **not** guarantee complete transactional rollback of camera components, attachments or externally saved files.

**Recovery requirements before rerun:**
1. Do not rerun V7, force-delete the package, or save the affected level from the failed editor session. Exit without saving.
2. Back up the target Unreal project and inspect the project after a fresh Unreal restart. If V7 exists or the editor reports damage, preserve it for diagnosis and prefer restoring a known-good project copy.
3. Preserve V7's `transfer-plan.json`, `coverage-report.json`, `evidence.json` and `runtime-receipt.json`; never edit/overwrite them. Plan V8 using a **separate cloned mapping** with an unoccupied `LS_Benchmark002_CED_V8` target and a **new output directory**.
4. Perform the same `--verify-existing` check on V8 before any Unreal execution and restart Unreal to load the corrected Python modules. A successful preparation/readback is not proof of target behavior equivalence.

This fix is reusable for all Unity Timeline clips; no Benchmark-specific special-casing, no original Unity asset modification, and no silent correction of malformed authored ease durations.

## Step 4: independent runtime validation

After generation, inspect the generated Unreal sequence, confirm target actor
bindings, compare source and target samples with CineTwin, and run the
generic saved target readback:

    import validate_transfer
    report = validate_transfer.run(
        "EXPERIMENT_ID",
        r"D:\Path\To\SOURCE.csir.json",
        r"B:\Research\CutsceneAI\CutsceneAI\integrations\unreal\LOCAL_TARGET_MAPPING.json",
        r"D:\Path\To\Validation",
    )

The generic validation checker is primarily structural and assumes target
features have been transferred by the native adapter. For best-effort partial
results, interpret it alongside coverage-report.json and the source/target
CineTwin behavior comparison; source features marked SKIPPED must never be
relabelled PASS. Skeletal bone-equivalence, executable events, waveforms,
physics and visual parity remain unverified unless tested separately.

## V8 static Sequencer transform readback evidence

The real V8 structural readback reported 46 PASS / 0 FAIL / 3 INCOMPLETE
(`CAM_A_Wide`, `CAM_C_Close`, `LIGHT_KEY`). The operator independently
inspected the saved readback JSON: all three actors have a **single frame-0
transform key**, with position and rotation nearly identical to the source
expectation. The missing `canonical_world_transform` field was a readback
representation gap, not proof of missing transform keys.

The revised **generic** target reader recognizes a single, explicitly labeled
`CutSceneAI Static Scene Pose` track, only when exactly one transform track
exists, its only key is at frame zero, it has no skeletal animation, and the
actor has **no attachment parent**. Its persisted Sequencer position/rotation
keys may then independently satisfy the expected static world position/rotation.
A moving track with one accidental key, parent-local attachment, or authored
skeletal track cannot pass by this fallback.

**Scale remains INCOMPLETE:** the existing generator keys only 6 channels
(location and rotation) in a static transform track. It does not persist scale
on this specific Sequence track. The reader deliberately does NOT fabricate
source scale or rely on transient, potentially unsaved editor level state.
The comparison core now checks every canonical static component separately
and marks missing/nonfinite position, quaternion or scale measurements
INCOMPLETE, never PASS.

After pulling this updated Python branch, rerun the **read-only**
`validate_transfer.run(...)` into a NEW result directory. For V8, the
expected outcome is six additional PASS position/rotation checks, with
three scale INCOMPLETE checks, assuming matching actual track labels/actor
attachment state. Structural readback still cannot establish root/pose
behavior, camera framing, waveform parity, or visual fidelity. A later
reusable generator improvement may persist all nine static transform
channels and independently verify saved level state on a new version.

## Research scope and roadmap

Implemented now: source coverage ledger; independent native per-track
planning; mapping-asset/track failures isolated; verified world-transform
fallback; hash-checked plans; safe target/project checks and partial runtime
receipts; existing native camera/transform/skeletal/audio/marker/light
realization and independent target readback.

Unimplemented and deliberately not claimed: full asset-import conversion,
automated source-to-target skeletal retargeting/skin weights, arbitrary shader
translation, arbitrary game scripts/Blueprints, physics reproduction,
universal media/codecs, audio waveform parity, rendered pixel parity, full
Unreal rollback of every modified actor/component and full in-engine test
on independently authored input scenes.

Extend existing universal engine adapter protocol for each extra semantic.
Never add special cases based on the names Benchmark001/002 or any
particular cutscene.
