# CutSceneAI — Current Engineering State

**Reviewed:** 2026-10-27 · **Scope:** Unity Timeline → Unreal Level Sequence

This page is a short orientation handoff, not evidence of successful target playback. See the [current issue matrix](../ISSUES_AND_MILESTONES.md) and the [documentation index](../INDEX.md) for maintained details.

## Current working milestones

- **Foundation:** CED / CSIR contracts, Unity structural extraction, Unreal planning and readback, and CineTwin evaluation tools are implemented for defined subsets of cinematic behavior.
- **Benchmark 001:** frozen research proof; automated target validation was accepted for its limited source/target setup. See [freeze record](../benchmarks/BENCHMARK_001_TARGET_FREEZE.md). Do not modify it.
- **Benchmark 002:** source authored and captured; best-effort V5 planning accounted for 12 source tracks, with 21 native action entries and `PROP_PARENTED` marked `STATIC_CHILD_INHERITS_PARENT`. Successful V5 Unreal sequence generation and saved behavior parity are **not yet established**.
- **Best-effort backend:** code for independent track planning, sampled transform fallback, parent-local reconstruction and source-bound evidence verification exists on experimental branch `feature/transfer-backend-best-effort-v0.1`. Python tests passing does not mean that Unreal generation passed.
- **Dataset/learning:** source dataset registry and human-approved mapping-case memory exist experimentally. No universal transfer model has been trained or validated.

## Current task order

1. Validate V5 generation on a backed-up target Unreal project and unused Level Sequence path.
2. Verify saved Level Sequence and actor hierarchy survive editor restart.
3. Independently compare source and target evaluated character, prop and camera trajectories; preserve failures in reports.
4. Address blockers using generic adapters, documented capability fallbacks and regression tests.
5. Demonstrate transfer on independently authored scenes before dataset expansion or AI training.

## Research invariants

- The source cutscene is ground truth, including rational timing and provenance.
- Unity source and frozen benchmarks remain unchanged during conversion work.
- Do not silently discard features or call partial runtime generation `PASS`.
- No benchmark-specific transfer hacks.
- Use a new staged target sequence, strict preflight, and independent saved-target readback.
- Report both source-feature coverage and post-generation fidelity.

## Branch dependency

Draft PRs [#49](https://github.com/Nithin0553/CutsceneAI/pull/49) → [#50](https://github.com/Nithin0553/CutsceneAI/pull/50) → [#51](https://github.com/Nithin0553/CutsceneAI/pull/51) → [#52](https://github.com/Nithin0553/CutsceneAI/pull/52) are stacked. `main` alone does not contain the latest Studio/backend work. Consult [branch audit](../BRANCH_AUDIT.md) before merging, checking out, or removing any refs.

For concrete instructions, start with [best-effort runbook](../architecture/BEST_EFFORT_TRANSFER_BACKEND_V0_1.md) and [repository guide](../REPOSITORY_GUIDE.md).
