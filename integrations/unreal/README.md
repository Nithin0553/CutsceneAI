# CutSceneAI Unreal Generator v0.1

This is the first deterministic CSIR -> Unreal Level Sequence realization path for Benchmark 001.

## Scope

The generator currently reconstructs:

- existing level actor bindings by actor label
- skeletal animation sections from mapped Unreal animation assets
- source-to-target root-motion direction calibration without modifying imported assets
- explicit skeletal section completion semantics to avoid target reference-pose fallback
- transform animation for props/cameras from CSIR curves
- Unity infinite AnimationTrack base offsets from extractor v0.1.3
- camera lens/FOV animation with source-to-target FOV semantic conversion
- camera cuts
- audio sections
- event identity/timing as Unreal marked frames
- source display rate and sequence duration

It intentionally does **not** attempt asset import or skeletal retargeting yet. Benchmark 001 uses pre-imported equivalent assets so the first test isolates transfer logic from asset-conversion problems.

## Runtime compatibility

The adapter is capability-driven rather than hard-coded to one Unreal version. Unreal
5.8 is the current Benchmark 001 validation runtime, but the builder records the engine
version and probes the APIs/features it needs before target mutation. Where engine
versions expose equivalent semantics through different APIs, `unreal_compat.py` selects
the compatible path. Unsupported capabilities fail explicitly instead of being guessed.

See `docs/architecture/ENGINE_ADAPTER_COMPATIBILITY.md` and
`docs/research/UNREAL_ADAPTER_COMPATIBILITY_LEDGER.md`.

## Requirements

- a supported Unreal Editor runtime exposing the required probed capabilities
- Python Editor Script Plugin enabled
- Sequencer Scripting plugin enabled
- target level already open
- one actor with each mapped label present in the level
- target animation/audio assets imported and referenced by Unreal content paths
- a CSIR export produced by the Unity extractor v0.1.3 or newer

## Mapping

Copy `benchmark001_mapping.example.json` to a local file such as `benchmark001_mapping.json` and replace the Unreal asset paths with the actual imported assets in your project.

Actor labels are deliberately explicit. The generator aborts if a mapped actor label is missing or ambiguous rather than silently binding the wrong object.

`output_resolution` may be set in the mapping (for example `[1920, 1080]`) to define the reproducible camera-framing validation gate. Benchmark001 falls back to 1920x1080 when it is omitted; observed source editor-view aspect is retained only as provenance.

## Run inside Unreal

Open **Window -> Output Log**, switch the input mode to Python, then run:

```python
import sys
sys.path.append(r"B:/Research/CutSceneAI/CutsceneAI/integrations/unreal")
import build_level_sequence
build_level_sequence.build(
    r"D:/path/to/Benchmark001_Timeline-5c57872a.csir.json",
    r"B:/Research/CutSceneAI/CutsceneAI/integrations/unreal/benchmark001_mapping.json",
)
```

The generated asset defaults to:

```text
/Game/CutSceneAI/Benchmark001/LS_Benchmark001
```

The generator refuses to replace an existing sequence unless `overwrite_sequence` is explicitly set to `true` in the mapping.

## Important timing rule

Infinite Unity AnimationTracks can have a section range wider than their actual keyed motion. The generator uses the timestamps on the individual CSIR curve keys, not the section start, when creating Unreal keys.

## Event behavior in v0.1

Unity Signal Emitters are represented as Unreal Sequencer **marked frames** with the same identity and timing. This preserves the benchmark's event/marker requirement without inventing a Blueprint endpoint. Executable event-track translation will be added as a separate capability later.

## Validation target for Benchmark 001

After generation, the next step is Unreal readback into CSIR followed by structural/numerical comparison against the frozen Unity source artifact. Do not manually repair the generated Level Sequence before readback; failures should be fixed in the adapter so the benchmark remains reproducible.


## Project intelligence

Before transfer, the Unreal adapter can emit a read-only Project Intelligence Profile:

    import sys
    sys.path.append(r"B:/Research/CutSceneAI/CutsceneAI/integrations/unreal")
    import project_intelligence
    profile = project_intelligence.analyze_project()

Or write it to a JSON file:

    project_intelligence.write_profile(r"D:/path/CutSceneAI_UnrealProjectProfile.json")

The profile records engine/runtime capabilities and semantic conventions used by the
adaptive mapping resolver. Rotation construction is capability-driven and uses named
roll/pitch/yaw fields rather than positional Rotator arguments.
