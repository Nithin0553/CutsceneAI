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
