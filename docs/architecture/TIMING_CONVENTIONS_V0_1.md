# CutsceneAI Timing Conventions v0.1

## Purpose

CutsceneAI must preserve source timing without forcing a universal 24, 30, 60, or other frame rate.

The source cutscene is temporal ground truth.

## Canonical rule

Time is represented exactly with rational values whenever it originates from a frame/tick domain.

A rate is:

```text
numerator / denominator units per second
```

Examples:

- 24 fps → `24/1`
- 29.97 fps → `30000/1001`
- 23.976 fps → `24000/1001`
- Unreal tick resolution 24000 → `24000/1`

## Required sequence timing

Every CSIR sequence stores:

- `source_rate`
- `display_rate` when exposed by the source
- `tick_resolution` when exposed by the source
- `playback_start`
- `playback_end`
- `duration`

The absence of an engine-specific tick resolution must not cause CutsceneAI to invent one in source data.

## Canonical timestamp

Discrete cinematic timing uses a rational timestamp:

```json
{
  "value": 48,
  "rate": {"numerator": 24, "denominator": 1}
}
```

This means frame/tick 48 at 24 units per second, i.e. exactly 2 seconds.

A timestamp may also preserve source sub-frame information with a rational offset.

## Conversion

Adapters convert native engine times to rational timestamps and target adapters choose a target-native representation that preserves the same physical time as closely as the target supports.

CutsceneAI must never solve a rate incompatibility by silently changing the source cutscene duration or event timing.

## Sections and clips

Every section/clip stores independently:

- timeline start
- timeline end
- source media/animation offset
- playback rate/time scale
- loop state
- blend-in duration
- blend-out duration

Timeline placement and source-asset sampling are different concepts and must not be collapsed.

## Curves

Curve keys preserve:

- key time
- value
- interpolation type
- in tangent when available
- out tangent when available
- tangent weights when available

Interpolation conversion is explicit and lossiness must be recorded.

## Audio and media

Audio/video timing is anchored to the same sequence time model. Media sample rate or audio sample rate is metadata and does not replace the cinematic timeline rate.

## Validation

Timing validation compares physical time after canonicalization.

Minimum first-benchmark checks:

- sequence duration error
- section start/end error
- camera-cut time error
- animation start/end error
- audio start error
- event/marker time error

Target acceptance for deterministically transferable timing is exact canonical equality where the target timebase can represent the timestamp; otherwise the adapter must report the smallest target quantization error.
