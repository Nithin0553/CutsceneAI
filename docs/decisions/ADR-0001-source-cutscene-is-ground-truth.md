# ADR-0001: Source Cutscene Is Ground Truth

**Status:** Accepted

## Decision

CutsceneAI is a transfer/reconstruction system for existing cutscenes.

The source cinematic remains authoritative. CutsceneAI must not replace known source values with generated alternatives when exact or deterministic conversion is possible.

## Consequences

- Source adapters are read-only by default.
- Extraction precedes semantic interpretation.
- A lossless source snapshot is retained.
- AI/ML is reserved for ambiguous matching, retargeting, reconstruction and evaluation where deterministic methods are insufficient.
- Validation always compares target readback against source-ground-truth data.
