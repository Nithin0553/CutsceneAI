# CutSceneAI Studio

**Research software for transferring an existing cinematic cutscene between game engines.**

CutSceneAI currently targets **Unity Timeline → Unreal Engine Level Sequence**. It preserves source-derived evidence, builds a deterministic conversion plan, attempts a guarded target reconstruction, and separates *generation* from independent *fidelity verification*. It does **not** yet support arbitrary cutscenes, automatic asset/rig conversion, or guaranteed playback parity.

## Current state

| Component | Status |
| --- | --- |
| Unity Timeline structural extraction and CineTwin evaluated sampling | Implemented for supported elements |
| CSIR / CED contracts and adaptive mapping | Implemented foundation |
| Native Unity → Unreal conversion planner and source coverage ledger | Implemented |
| CineTwin world-transform and parent-local best-effort fallback | Implemented in Python; Unreal acceptance pending |
| Unreal Sequencer builder, runtime preflight, saved readback | Implemented for supported elements; project-specific runtime checks required |
| Asset discovery and suggestions | Read-only candidates; no universal automatic import |
| Dataset registry and verified case retrieval | Experimental, on development branches |
| End-to-end generalization, skeletal retargeting, visual/audio/event equivalence | Not established |

**Research integrity:** A green Python test suite proves code contracts, not cutscene fidelity. Results are only accepted after target asset creation, persistence/readback, and independently observed source–target comparison.

## Transfer pipeline

```text
Existing Unity Timeline
    |
    v
Unity CSIR + Project Intelligence + CineTwin observed source behavior
    |
    v
Target asset/actor mapping + coverage/readiness audit
    |
    v
Best-effort transfer plan + evidence hashes + unsupported-feature report
    |
    v
Unreal preflight -> guarded Level Sequence generation
    |
    v
Saved target readback + CineTwin target observation
    |
    v
Compare -> report PASS / FAIL / INCOMPLETE per required feature
```

## Repository map

| Directory | Responsibility |
| --- | --- |
| `packages/contracts/` | Versioned CED, CSIR, source, validation, and benchmark data contracts |
| `packages/cinetwin/` | Sampling, source–target comparison, hierarchy and motion reasoning |
| `packages/adapters/` | Engine adapter interface |
| `packages/readiness/` | Adaptive mappings and capability analysis |
| `packages/studio/` | Transfer orchestration and best-effort planning |
| `packages/dataset/`, `packages/learning/` | Experimental source dataset and approved case memory |
| `packages/validation/` | Contract, benchmark and readback validation |
| `integrations/unity/` | Unity Editor extraction/capture package |
| `integrations/unreal/` | Unreal Sequencer realization, preflight and readback |
| `tools/` | Headless Python entry points; Unreal-only scripts belong to its integration |
| `tests/` | Python/contract tests, simulated Unreal interfaces and static Unity checks |
| `docs/` | Architecture, benchmarks, research records and development policies |

See [Repository Guide](docs/REPOSITORY_GUIDE.md) for file ownership and safe development practices.

## Quick start (Python-only)

**Requirements:** Python 3.11+, Git. Unity and Unreal are needed only for actual engine operations.

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check tests
```

Prepare a best-effort transfer **without modifying the engines** (requires a real source CSIR and an explicitly curated target mapping):

```powershell
python tools/transfer_backend.py --csir SOURCE.csir.json --mapping TARGET_MAPPING.json --out OUTPUT_DIRECTORY
python tools/transfer_backend.py --csir SOURCE.csir.json --mapping TARGET_MAPPING.json --out OUTPUT_DIRECTORY --verify-existing
```

When CineTwin evidence is available, add `--capture SOURCE.cinetwin.behavior.json` to **both** commands. The plan includes `transfer-plan.json`, `coverage-report.json` and `evidence.json`. Keep these files immutable, use unique output directories, and never assume the plan itself is a successful transfer.

The Unreal generation procedure and safety gates are documented in [Best-Effort Transfer Backend](docs/architecture/BEST_EFFORT_TRANSFER_BACKEND_V0_1.md). Do not run the generator on your only Unreal project copy.

## Documentation

- [Documentation Index](docs/INDEX.md) — start here for architecture, workflow and benchmarks.
- [Project Status and Issues](docs/ISSUES_AND_MILESTONES.md) — twenty tracked conversion gaps and acceptance criteria.
- [Development Guide](CONTRIBUTING.md) — isolated branches, test requirements, artifact policy.
- [Benchmark 001 Freeze](docs/benchmarks/BENCHMARK_001_TARGET_FREEZE.md) — frozen research evidence; do not edit.
- [Benchmark 002](docs/benchmarks/BENCHMARK_002.md) — more complex Unity → Unreal experiment.

## Development and branch policy

`main` is the stable research baseline and is intentionally **behind** the unmerged experimental transfer branch. The currently active draft PR chain is [#49](https://github.com/Nithin0553/CutsceneAI/pull/49) → [#50](https://github.com/Nithin0553/CutsceneAI/pull/50) → [#51](https://github.com/Nithin0553/CutsceneAI/pull/51) → [#52](https://github.com/Nithin0553/CutsceneAI/pull/52). Review and merge these in dependency order; do not cherry-pick or merge this documentation cleanup blindly into `main`.

No original benchmark scenes, frozen source artifacts or Unreal assets should be changed as part of repository housekeeping.

## License

No open-source license is declared here. Redistribution and reuse rights should not be assumed until the repository owner chooses a license.
