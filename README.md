# CutsceneAI

CutsceneAI is a research-grade cross-engine cinematic transfer studio.

## Primary objective

Transfer an **already-existing cutscene** from one game engine to another with the highest practical, measurable fidelity.

Initial target:

```text
Unity Cutscene
    ↓
Lossless Extraction
    ↓
CutsceneAI Engine-Neutral Representation
    ↓
Asset / Rig / Feature Mapping
    ↓
Transfer Plan
    ↓
Unreal Reconstruction
    ↓
Readback
    ↓
Validation / Correction
```

The reverse direction (Unreal → Unity) follows after the first complete Unity → Unreal proof.

## Core principles

1. The source cutscene is ground truth.
2. Source projects are read-only by default.
3. Never regenerate information that can be transferred exactly.
4. Preserve exact source data before adding semantic interpretation.
5. Use deterministic engineering first.
6. Use AI/ML only where ambiguity or incompatibility cannot be solved reliably otherwise.
7. Every transferred element must end in one explicit state: `EXACT`, `CONVERTED`, `RETARGETED`, `BAKED`, `RECONSTRUCTED`, `TARGET_MAPPED`, or `BLOCKED`.
8. Never silently drop unsupported cinematic behavior.
9. Every target result must be read back and validated.
10. Engine-specific logic belongs in adapters, not in the core.

## First end-to-end milestone

Transfer one real Unity Timeline containing one character, one skeletal animation, one moving prop, two cameras, one camera cut, camera transform/lens data, one audio clip, one event/marker, and an 8–12 second duration into an Unreal Level Sequence and verify it numerically.

See `docs/architecture/FOUNDATION_V0_1.md`.
