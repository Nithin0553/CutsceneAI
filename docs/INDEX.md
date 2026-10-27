# Documentation Index

This is the maintained navigation page for CutSceneAI Studio. Documents marked **historical** describe what was known at an earlier research milestone and are not statements of present-day transfer readiness.

## Start here

| Question | Read |
| --- | --- |
| What works today? | [Project status and transfer issues](ISSUES_AND_MILESTONES.md) |
| Where should code live? | [Repository guide](REPOSITORY_GUIDE.md) |
| How should I contribute safely? | [Development guide](../CONTRIBUTING.md) |
| How do I execute an audited transfer? | [Best-effort backend runbook](architecture/BEST_EFFORT_TRANSFER_BACKEND_V0_1.md) |
| What is the overall transfer architecture? | [Generalizable transfer architecture](architecture/GENERALIZABLE_CUTSCENE_TRANSFER.md) |
| How is cross-engine behavior evaluated? | [CineTwin overview](research/CINETWIN_PHASE_1.md), [behavior comparison](research/CINETWIN_PHASE_4_BEHAVIOR_COMPARISON.md) |
| How are training cases approved? | [Continual mapping memory](architecture/CONTINUAL_CUTSCENE_LEARNING_V0_1.md) |
| How do we register source datasets? | [Studio dataset design](architecture/STUDIO_DATASET_AND_ORCHESTRATION_V0_1.md) |
| How are backend changes reviewed? | [GitHub branch and PR audit](BRANCH_AUDIT.md) |

## Engine integrations

- [Unity extractor and CineTwin capture](../integrations/unity/com.cutsceneai.extractor/README.md)
- [Unreal adapter, mapping and readback](../integrations/unreal/README.md)
- [Engine adapter protocol](../packages/adapters/README.md)
- [Readiness and project intelligence](../packages/readiness/README.md)
- [Validation gates](../packages/validation/README.md)

## Design contracts

- [Foundation](architecture/FOUNDATION_V0_1.md)
- [Coordinate conventions](architecture/COORDINATE_CONVENTIONS_V0_1.md)
- [Timing conventions](architecture/TIMING_CONVENTIONS_V0_1.md)
- [Adaptive project intelligence](architecture/ADAPTIVE_PROJECT_INTELLIGENCE_V0_1.md)
- [Runtime compatibility](architecture/ENGINE_ADAPTER_COMPATIBILITY.md)
- [Architecture decisions](decisions/ADR-0001-source-cutscene-is-ground-truth.md)

## Benchmarks (retain as immutable evidence)

- [Benchmark 001](benchmarks/BENCHMARK_001.md) — [source freeze](benchmarks/BENCHMARK_001_SOURCE_FREEZE.md) · [target freeze](benchmarks/BENCHMARK_001_TARGET_FREEZE.md) · [validation](benchmarks/BENCHMARK_001_TARGET_VALIDATION.md).
- [Benchmark 002](benchmarks/BENCHMARK_002.md) — [source build](benchmarks/BENCHMARK_002_SOURCE_BUILD.md) · [pipeline corrections](benchmarks/BENCHMARK_002_PIPELINE_CORRECTIONS.md).

## Historical research and handoffs

The numbered [CineTwin research reports](research/) and [Benchmark 002 chat handoff](benchmarks/BENCHMARK_002_CHAT_HANDOFF.md) record earlier experiments, hypotheses and reproduced failures. Do not replace research history with current status assertions; use [Project status](ISSUES_AND_MILESTONES.md) for the live readiness overview. The obsolete original new-chat prompt was removed from the working tree because it incorrectly instructed users to restart the already-built Benchmark 002.
