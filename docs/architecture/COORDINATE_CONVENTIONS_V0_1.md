# CutsceneAI Coordinate Conventions v0.1

## Purpose

CutsceneAI must never assume that source and target engines share units, axes, handedness, rotation conventions, hierarchy semantics, or local/world transform rules.

This contract defines the canonical spatial representation used inside CSIR.

## Canonical coordinate space

CutsceneAI canonical space is:

- handedness: right-handed
- up axis: +Y
- forward axis: -Z
- right axis: +X
- linear unit: meter
- angle unit: radian internally; degrees may be retained as source metadata
- rotation storage: normalized quaternion `[x, y, z, w]`
- scale: unitless vector `[x, y, z]`

## Transform representation

Every transform sample MUST declare its space:

- `WORLD`
- `LOCAL`

Local transforms MUST identify their parent binding/entity when a parent exists.

CSIR may preserve both world and local transforms when the source engine exposes both, but one must be marked authoritative for reconstruction.

## Conversion rule

Adapters must perform:

```text
native source space
    ↓
canonical CutsceneAI space
    ↓
native target space
```

Core transfer logic must not contain Unity- or Unreal-specific axis or unit conversions.

## Precision

Canonical transform values use double-precision numbers in serialized contracts when available. Engine adapters may quantize only when required by the target engine and must record the quantization in provenance.

## Rotations

Quaternions are canonical because Euler ordering differs between engines and tools.

Adapters may preserve original Euler channels as source metadata for editability/debugging, but canonical comparison and transfer must not depend on Euler ordering.

Quaternion sign equivalence must be respected during validation: `q` and `-q` represent the same orientation.

## Scale

Negative and non-uniform scale must be preserved explicitly and flagged during readiness analysis because they may interact differently with hierarchy, animation, skeletons, physics, cameras, and rendering.

## Pivots and origins

Object transform and pivot/origin semantics are separate concepts. Adapters must not silently fold pivot offsets into object transforms without recording the conversion.

## Skeletal space

Skeletons must preserve:

- bone hierarchy
- reference/rest pose
- local bone transforms
- root definition
- bind/reference matrices when available

A semantic humanoid map is supplemental metadata and must never replace the complete source skeleton.

## Validation

Round-trip spatial tests must verify:

```text
source native
→ canonical
→ source native
```

and cross-engine tests must compare target readback in canonical space.

Minimum validation targets for the first benchmark:

- position
- orientation
- scale
- hierarchy
- camera transform
- moving prop transform
- character root trajectory
