# Repository Guide

## Layout and ownership

```text
.github/workflows/     automated checks
docs/
  INDEX.md             maintained documentation navigation
  ISSUES_AND_MILESTONES.md  current limitations and acceptance checks
  BRANCH_AUDIT.md      branch governance / cleanup candidates
  architecture/        data models, protocols, design and runbooks
  benchmarks/          frozen benchmark evidence, historical specs and results
  decisions/           architecture decision records
  handoffs/            current state overview (not benchmark history)
  implementation/      Unity implementation notes
  research/            recorded experiments, evidence and failure analysis
integrations/
  unity/               Unity Editor code (C#)
  unreal/              Unreal Editor Python adapter (requires unreal module)
packages/
  adapters/            target/source protocol
  contracts/           immutable versioned schemas and dictionaries
  cinetwin/            engine-free samples, reasoning and comparisons
  dataset/             source dataset registry
  learning/            verified mapping-case memory
  readiness/           source/target feature resolution
  studio/              session, planner, asset suggestions and motion fallback
  validation/          source/readback acceptance
tools/                 operator entry points (engine independent)
tests/                 test families mirror code ownership
```

## Boundaries

- `packages/` should be importable in normal Python without importing Unreal or Unity.
- `integrations/unreal/` owns `import unreal`, asset creation, target mutation, persistence and readback.
- `integrations/unity/` owns Unity Timeline APIs, capture and C# editor code.
- `tools/` should be executable operators rather than copies of business logic.
- `tests/` should cover new behavior generically and must never require an authoritative benchmark source file to be rewritten.
- `docs/benchmarks/` contains frozen measurements; new observations should be appended to new experimental reports, not overwrite freezes.

## Generated files versus source-controlled files

**Commit:** Python/C# source, versioned JSON schemas/dictionaries, example mappings with no private paths, immutable research specifications and redacted test fixtures.

**Do not commit:** exported source CSIR/capture files containing live project data, generated `transfer-plan.json`, `coverage-report.json`, `evidence.json`, runtime receipts, local Unity `Library/` or Unreal `Saved/` and `Intermediate/`, imported 3D media, downloaded model weights, machine-specific mapping credentials, temporary reports, virtual environments and caches.

Use externally named experiment directories such as `B:\Research\CutsceneAI\TransferPlans\...` to preserve old plans and receipts. Never overwrite an earlier research run.

## Safety rules

1. Verify the **exact source CSIR hash** and mapping/capture hashes before generation.
2. Use a separate target Unreal project backup and an unused Level Sequence path.
3. Check mapped actor labels and source hierarchy before any actor mutation.
4. Treat `GENERATED_UNVERIFIED` as an intermediate state; require target readback and measured CineTwin fidelity results to claim acceptance.
5. Do not change frozen Benchmark 001 or 002 original source materials during cleanup.
6. Keep the stacked experimental PRs separate until reviewed and merged in order.

## Naming conventions

- Python modules: `snake_case.py`; test modules: `test_<module>.py`.
- Data artifacts: clear descriptive names and explicit schema versions in documents.
- Working branches: `feature/<purpose>`, `fix/<purpose>`, `chore/<purpose>`.
- Research record: a scoped Markdown report with provenance, reproduction steps, actual observations and limitations.
- Never name a runtime asset as if it is verified until readback independently proves it.

## Architectural debt to address after hygiene

The current repository has a flat `integrations/unreal/` with several substantial Python modules and uses direct `sys.path` modification rather than a consistently packaged Python library. These need targeted refactoring with regression and real-engine checks—not mass renaming, because Unreal Editor import semantics and frozen experiment scripts depend on paths.
