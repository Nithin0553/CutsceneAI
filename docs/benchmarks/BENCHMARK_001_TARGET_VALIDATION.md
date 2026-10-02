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
