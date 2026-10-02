# Benchmark 001 — Unreal Target Freeze

Status: **FROZEN AUTOMATED PASS — UNITY → UNREAL**

Benchmark001 has completed visual acceptance, automated target readback, semantic/numerical validation, and cryptographic target freeze.

## Validation result

- passed checks: `54`
- failed checks: `0`
- incomplete checks: `0`
- report status: `PASS`
- display rate: `60/1`
- playback range: frames `0 → 600`

## Frozen identities

### Source

- Engine: Unity
- Source CSIR SHA-256: `5da9ede712854e77bb51e914ccf99d6e5b7432e6b9d24acbbb971c2d539b5ef4`

### Target

- Engine: Unreal
- Engine build: `5.8.3-58210709+++UE5+Release-5.8`
- Sequence asset path: `/Game/CutSceneAI/Benchmark001/LS_Benchmark001`
- Unreal Level Sequence SHA-256: `384f246f066cbab18969d49d4a4824e8aa80c16f42175098796a3ed522618304`

### Transfer mapping

- Mapping SHA-256: `1fa9322d344cec34ff24a7672fec59164544a5cff4efe4f89a0856bd0c01fd03`

### Validation artifacts

- Expected snapshot SHA-256: `bd4e49c138fc00d1d3fd563ca9304d7e66c7c77e11b78a5f7fad258014a898af`
- Unreal readback SHA-256: `53551b043528a2df9b97d784e901a4f1200d82948fb5be88d01dfeede8a5e10e`
- Validation report SHA-256: `c63d76cda0422ae011bda46d114438dd42ac9ec9127c1e2d18d7bef0ba859df6`

### Software

- Repository: `Nithin0553/CutsceneAI`
- CutSceneAI git head used by the freeze tool: `094e926f9887139a3f6eb18522a764f257daa55e`

## Freeze meaning

This freeze proves that the accepted Benchmark001 target is tied to an exact source artifact, exact target Level Sequence artifact, exact mapping, exact source-derived expectation, exact target readback, exact validation report, and exact CutSceneAI code revision.

Any later source, mapping, target sequence, validator, or adapter modification creates a new benchmark revision unless the corresponding SHA-256 identities remain unchanged.

The portable manifest is stored in `BENCHMARK_001_TARGET_FREEZE_MANIFEST.json`.
