# CutsceneAI Current State

## Status

Foundation Milestone 0 is in progress on branch `foundation/v0.1`.

## Primary objective

Transfer an already-existing cutscene from one game engine to another with measurable high fidelity.

Initial direction: **Unity → Unreal**.

## Frozen architectural decisions

- source cutscene is ground truth
- source project is read-only by default
- CED is separate from CSIR
- engine mappings are separate from the canonical dictionary
- every element has an explicit transfer outcome
- target generation happens in staging before commit
- generated target is read back before validation
- deterministic engineering first
- AI/ML only for unresolved ambiguity, retargeting, reconstruction or evaluation

## Current foundation

- project README and Python tooling
- Foundation v0.1 architecture document
- ADR-0001: source cutscene is ground truth
- ADR-0002: explicit transfer outcomes
- transfer-outcome JSON contract
- Cutscene Element Dictionary v0.1 draft
- Unity CED mapping draft
- Unreal CED mapping draft
- CSIR v0.1 schema draft
- readiness subsystem contract
- engine adapter contract
- validation-layer contract

## Next development step

Review and freeze:

1. CED v0.1 scope
2. canonical coordinate conventions
3. exact timing model
4. minimum CSIR v0.1 schema
5. typed engine adapter interface
6. first benchmark cutscene specification

After these are frozen, implement the first **Unity read-only extractor**.

## Critical reminder

CutsceneAI does not primarily generate new cutscenes. It transfers an existing source cutscene. Do not reintroduce a text-to-motion or generative-performance system into the critical path unless a specific transfer problem later proves that it is necessary.
