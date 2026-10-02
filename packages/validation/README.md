# Validation Layers

Target validation compares **target readback** against the **source snapshot / CSIR**, never only against generation requests.

Validation is layered:

1. Structural
2. Numerical timing / transforms
3. Animation / pose / trajectory
4. Camera / framing
5. Audio / event timing
6. Visual
7. Semantic (later)

A transfer may only be committed automatically when all required validation gates for that transfer plan pass.

## v0.1 readback architecture

Benchmark001 now has a concrete target-readback path:

```text
Frozen Unity CSIR
      ↓
source-derived target expectation
      +
Saved Unreal Level Sequence
      ↓
Unreal readback extractor
      ↓
canonical target snapshot
      ↓
pure Python comparison
      ↓
validation report
```

The readback extractor does not call the generation planner. It reads the saved Unreal asset, bindings, tracks, sections, keys, camera cuts, audio sections, marked frames, mapped actor transforms, camera lens state, and imported animation/root-motion data.

Target transforms are converted back to CutSceneAI canonical space before comparison. Camera lens values are normalized to **vertical FOV degrees** even when Unreal realizes them as CineCamera focal length.

## Benchmark001 v0.1 gates

The first automated report checks:

- display rate and playback range
- mapped target bindings
- static mapped actor transforms in canonical space
- moving-prop and camera transform key times/values
- skeletal animation asset, section range, play rate and post-roll hold
- effective character root-motion displacement
- static camera vertical FOV and validation aspect
- animated camera vertical-FOV keys
- camera cut identity and timing
- audio asset/timing/loop flag
- event marker identity/timing

A result may be `PASS`, `FAIL`, or `INCOMPLETE`. Missing readback evidence is never converted into a false pass.

Visual validation remains a separate gate; numerical validation does not claim shader/material/lighting equivalence.
