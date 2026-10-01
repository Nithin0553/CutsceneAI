# Benchmark 001 — Controlled Unity → Unreal Transfer

## Purpose

Prove the complete deterministic transfer pipeline on one small, real, manually authored cutscene before introducing automatic asset matching, advanced retargeting, VFX reconstruction, or AI into the critical path.

## Source

Unity Timeline is the authoritative source.

## Target

Unreal Level Sequence.

## Scene requirements

The source cutscene must be 8–12 seconds and contain exactly the following minimum cinematic elements:

1. one humanoid character
2. one skeletal animation clip on that character
3. character root motion or keyed character transform motion
4. one independently moving prop
5. two cameras
6. one camera cut between those cameras
7. animated camera transform on at least one camera
8. explicit camera FOV or physical lens data
9. one audio clip
10. one event/marker
11. static environment geometry sufficient to judge placement and framing

## Asset-control rule

For Benchmark 001, use equivalent/prepared assets in both projects wherever practical. The benchmark is intended to isolate extraction, representation, timing, coordinate conversion, generation, and validation—not asset-search quality.

Asset mappings are manual and explicit.

## Pipeline under test

```text
Unity project
  ↓
project validation
  ↓
cutscene enumeration
  ↓
read-only Timeline extraction
  ↓
source snapshot
  ↓
CSIR v0.1
  ↓
manual mapping manifest
  ↓
transfer plan
  ↓
Unreal staging generation
  ↓
Level Sequence
  ↓
Unreal readback
  ↓
CSIR comparison
  ↓
commit or rollback
```

## Required acceptance checks

### Structural

- target sequence exists
- expected entity count preserved
- expected track types preserved
- camera cut preserved
- audio section preserved
- event preserved

### Timing

- sequence duration
- animation start/end
- moving-prop section timing
- camera cut timing
- audio start timing
- event timing

Where the target timebase can exactly represent source timestamps, canonical timing error must be zero. Otherwise report target quantization error explicitly.

### Spatial

Compare in CutsceneAI canonical space:

- character root position/orientation
- moving prop position/orientation
- both camera transforms
- hierarchy/parent relationships used by the cutscene

### Camera

- active camera identity over time
- cut time
- position/orientation
- FOV or physical-lens equivalence

### Animation

- animation asset mapping is correct
- start/end timing is correct
- playback speed is correct
- character root trajectory is preserved

### Audio / event

- mapped audio asset is correct
- audio start offset is preserved
- event name/type/payload is preserved where deterministically representable
- event time is preserved

## Explicitly out of scope for Benchmark 001

- automatic semantic asset matching
- different character skeleton retargeting
- facial animation
- complex VFX conversion
- materials/shader conversion
- runtime gameplay-driven motion
- physics/cloth/hair parity
- semantic reconstruction
- AI/ML

These are not excluded from CutsceneAI; they are excluded from this first proof so failures remain diagnosable.

## Pass condition

Benchmark 001 passes only when the Unreal result is generated from CSIR, read back from Unreal, and validated against the extracted Unity ground truth. Visual similarity alone is not sufficient.
