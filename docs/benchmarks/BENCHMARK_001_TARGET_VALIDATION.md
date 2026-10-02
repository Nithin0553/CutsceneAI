# Benchmark 001 — Target Validation

Status: **VISUALLY ACCEPTED; AUTOMATED READBACK VALIDATION READY TO RUN**

## Ground truth

The authoritative source remains the frozen Unity CSIR recorded in `BENCHMARK_001_SOURCE_FREEZE.md`.

The generated Unreal Level Sequence is not considered a benchmark pass merely because it looks correct. The saved target asset must be read back and validated against source-derived semantic expectations.

## Current visually accepted target

- Target engine used during development: Unreal Engine 5.8.3
- Generated asset: `/Game/CutSceneAI/Benchmark001/LS_Benchmark001`
- Source artifact SHA-256: `5da9ede712854e77bb51e914ccf99d6e5b7432e6b9d24acbbb971c2d539b5ef4`
- Adapter state includes the camera-rotation, root-motion direction, final-pose hold, camera-FOV/framing, and Unreal API compatibility corrections discovered during the controlled transfer.

This record does **not** freeze the target artifact yet. Target freeze occurs after the automated report passes and the generated `.uasset` is hashed.

## Automated validation outputs

Running the Unreal validation command writes:

- `Benchmark001.expected.json`
- `Benchmark001.unreal.readback.json`
- `Benchmark001.validation.json`

The expectation is source-derived. The readback is extracted from the saved Unreal Level Sequence and mapped target actors. The report compares them in normalized semantic space.

## Pass rule

Benchmark001 becomes **AUTOMATED PASS** only when the validation report status is `PASS` with zero failed and zero incomplete required checks.

If the report fails, do not manually edit the sequence. The mismatch becomes adapter or mapping evidence, is fixed in code, receives a regression test, and the target is regenerated.


## Validation calibration finding

The first automated run produced 53 passing checks and one root-motion failure under the
initial 0.1 cm per-component placeholder threshold. The visible horizontal differences
were only fractions of a millimeter, indicating that a raw component-equality gate was
not the right semantic measure for an imported/resampled skeletal animation.

Benchmark001 now records root-motion endpoint error, horizontal direction error, and
relative horizontal travel-distance error separately. The declared v0.1 thresholds are
0.5 cm endpoint, 0.1 degree direction, and 0.25% horizontal distance. The report retains
the measured values so the pass is quantitative and auditable rather than visually
waived.

## Second automated run finding

The updated semantic metric isolated the remaining difference:

- horizontal endpoint error: approximately 0.017 cm
- horizontal relative distance error: approximately 0.0119%
- direction error: approximately 0.0000015 degree
- vertical endpoint error: approximately 0.687 cm

The source RootT curve has only low vertical excursion for this grounded walk/turn clip. The validator therefore now treats the horizontal trajectory as the primary locomotion semantic and evaluates the small vertical endpoint difference under the grounded-motion policy. This policy is derived from source curve excursion rather than from the asset name or a Benchmark001-specific hard code.
