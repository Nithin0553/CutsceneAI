# One-run CineTwin diagnosis — source Unity vs generated Unreal (Issue #80)

This replaces repeated one-off editor console probes with **one read-only evaluation run**.
It audits a saved Unreal Level Sequence, independently compares it to the
SHA-bound Unity CineTwin source capture, and emits a fresh JSON report.

## What is measured

- Provenance: CSIR SHA-256, capture hash and source project/sequence identity,
  mapping hash, loaded Unreal project and Level Sequence.
- Mapped actors: unique labels, class, actor/component parent hierarchy,
  skeletal mesh component/root bone, mapped target asset classes.
- Sequencer: binding names, track classes, animation assets, section frame ranges,
  root-motion flags, transform channel key counts and ranges.
- **Actual target motion**: evaluate every frame in the loaded Unreal Editor;
  compare mapped actor WORLD position with the Unity entity WORLD position.
- Character skeletal roots: compare frame-aligned source CineTwin root-bone WORLD
  position with evaluated target root-bone WORLD position, matching one unique
  normalized bone name (for example, mixamorig9:Hips versus Hips).
- Absolute world-position error and movement-only error after removing the
  frame-zero offset, first/last displacements, mean and maximum error, worst
  frame, and selected checkpoints.

**Not established:** rendered image or camera-framing equivalence, full joint
poses, lighting output, audio waveform, event execution, automatic actor/asset
staging, deployment, or packaged-runtime behavior. All results are diagnostics,
NOT a fidelity pass. Do not tick Issue #80 parity acceptance checkboxes merely
because a script completed.

## Update the existing checkout

From the existing repository folder in VS Code PowerShell, on the
feature/studio-supported-asset-import-v0.1 branch:

~~~powershell
git pull --ff-only origin feature/studio-supported-asset-import-v0.1
~~~

This does not delete or clean untracked Unity .meta files or mapping files.

## Run once in the open Benchmark 002 Unreal project

Paste this block into the Unreal Python Console with the correct target level loaded:

~~~python
import sys
sys.path.insert(0, r"B:\Research\CutsceneAI\CutsceneAI\integrations\unreal")
import diagnose_cinetwin_parity

report = diagnose_cinetwin_parity.run(
    csir_path=r"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002_Timeline-e6518af4.csir.json",
    capture_path=r"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002_Timeline.cinetwin.behavior.json",
    mapping_path=r"B:\Research\CutsceneAI\CutsceneAI\integrations\unreal\benchmark002_cinetwin_parity_mapping.json",
    sequence_path="/Game/CutSceneAI/Benchmark002/LS_Benchmark002_CED_V8",
    output_dir=r"D:\CutSceneAI - Studio\StudioAssetTests",
)
~~~

The console prints sample count, actor count, per-entity errors and the newly
created report path. Upload that one JSON report instead of dozens of
intermediate logs.

Only temporary Sequencer editor evaluation occurs. It restores the previous
open sequence and playhead in a finally block, and never saves, creates,
modifies or deletes any Unreal/Unity assets or levels. The report uses a
new timestamped filename and refuses to overwrite existing evidence.

## Interpret the report

- entities.Ch31_nonPBR.actor_world: Unity character origin versus Unreal actor.
- entities.Ch31_nonPBR.skeletal_root_world: **Unity Hips versus Unreal Hips**.
- initial_offset_target_minus_source_cm: initial placement/reference-pose mismatch.
- max_offset_removed_motion_error_cm: path error after removing initial offset.
- max_absolute_error_cm: worst matching-frame world-position error.
- target.binding_tracks: editable sequence track inventory and keys.
- target.asset_mappings: existing asset class presence, not playback equivalence.
- frames: all frame-by-frame measured source and target coordinates.
- errors and limitations: unresolved features and restoration failures.

This is new diagnostic evidence; frozen Benchmark001 and Benchmark002 source
captures and previous Unreal reports are not overwritten.
