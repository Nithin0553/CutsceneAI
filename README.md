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
| Source-backed asset staging | Implemented for selected supported assets and provenance; no universal automatic import |
| Dataset registry and approved-case memory | Experimental infrastructure integrated; transfer improvement on unseen projects not established |
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

## Launch the full Studio UI on Windows

A reviewed Phase 10.5 source distribution has a guarded one-command launch
path. From a new checkout or the extracted, SHA-verified source ZIP, run:

```powershell
.\tools\launch_studio.ps1
```

It installs an isolated local Python environment when needed, starts and
stops a temporary live localhost smoke test, then runs the supervised Studio
server. Open **http://127.0.0.1:8765** in your browser. No native Unity/Unreal
operation is performed without connecting editor companions and explicit
source-bound transfer approval.

See [Phase 10.5 software packaging, engine-test handoff and complete first
testing procedure](docs/studio/PHASE10_5_FINAL_SOFTWARE_PACKAGE_AND_LIVE_ENGINE_TEST_ENTRY.md).
A passing ZIP/host CI run only qualifies the build for **real-engine testing**;
it does not establish cutscene parity or authorize a production release.

## Quick start (Python-only)

**Requirements:** Python 3.11+, Git. Unity and Unreal are needed only for actual engine operations.

```powershell
python -m pip install pytest ruff jsonschema
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

- [CED preflight and unknown-element reporting](docs/architecture/CED_FIRST_PREFLIGHT_V0_1.md)
- [Documentation Index](docs/INDEX.md) — start here for architecture, workflow and benchmarks.
- [Project Status and Issues](docs/ISSUES_AND_MILESTONES.md) — twenty tracked conversion gaps and acceptance criteria.
- [Development Guide](CONTRIBUTING.md) — isolated branches, test requirements, artifact policy.
- [Benchmark 001 Freeze](docs/benchmarks/BENCHMARK_001_TARGET_FREEZE.md) — frozen research evidence; do not edit.
- [Benchmark 002](docs/benchmarks/BENCHMARK_002.md) — more complex Unity → Unreal experiment.

## Development and branch policy

`main` contains the consolidated Studio transfer stack from [merged PR #112](https://github.com/Nithin0553/CutsceneAI/pull/112) (November 9, 2026). Its integration smoke test and automated checks were accepted for the supported scope, **not** universal cutscene fidelity or release certification.

Active follow-on work is [PR #113](https://github.com/Nithin0553/CutsceneAI/pull/113) (source-backed static-scene mapping), followed by stacked [PR #114](https://github.com/Nithin0553/CutsceneAI/pull/114) (typed source-component capture). Both remain draft and need actual Unity/Unreal runtime verification before merging. Legacy [PR #6](https://github.com/Nithin0553/CutsceneAI/pull/6) and [PR #90](https://github.com/Nithin0553/CutsceneAI/pull/90) have divergent commit history and require individual review.

Historical stacked draft PRs whose exact heads were ancestors of #112 have been closed as superseded; their commits, discussion, and remote branches were not deleted. Outstanding fidelity and release research remain in [issues #94–#101](https://github.com/Nithin0553/CutsceneAI/issues). See [Current Engineering State](docs/handoffs/CURRENT_STATE.md), [Branch Audit](docs/BRANCH_AUDIT.md), and [Release Acceptance](docs/studio/RELEASE_ACCEPTANCE.md).

No original benchmark scenes, frozen source artifacts, Unreal assets, or historical experiment evidence should be changed as part of repository housekeeping.

## License

No open-source license is declared here. Redistribution and reuse rights should not be assumed until the repository owner chooses a license.
