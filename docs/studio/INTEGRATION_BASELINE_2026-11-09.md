# CutSceneAI Studio — integration baseline (2026-11-09)

**Status:** Code consolidation candidate; NOT a native fidelity certification or general release.
**Canonical review branch:** `feature/studio-consolidated-integration-20261109`
**Base:** `main` at `2f4507e94b390a8b167fd58559e659318a800b52`.
**Integrated implementation source:** `fix/studio-static-mesh-material-slots-v0.1` at `c0c52020f6af4eaaa37a3e85dae5f34982fafbb6` (PR #111), itself based on PR #110.

## Why a single review branch

Studio's working transfer implementation lives on a sequence of *stacked* PR bases rather than `main`. Comparing PR #111's head with `main` at the integration checkpoint showed 530 commits ahead, zero commits behind, and 213 changed paths (192 added, 19 modified, 2 deleted). These numbers are **not** 530 independent fixes; they reflect the stacked development history. The two deleted paths were `docs/benchmarks/BENCHMARK_002_NEW_CHAT_PROMPT.txt` and `docs/research/CINETWIN_MOTION_DIAGNOSTICS.md`; they are visible in the PR diff for review. No existing user-engine projects are part of this merge.

The chain contains the baseline work of PRs #49–#52 and #75–#83, the Studio sequence #87–#92, source identity merged into the integration branch at #102, and successive enhancements #104–#111. This integration branch **does not silently close or merge** those original PRs. Compare the final code, not a historical PR title, to decide whether an old proposal is redundant.

## What is implemented / independently established

- The user reports a Unity→Unreal transfer that **generates an editable cutscene but is visually/behaviorally imperfect**. This is first-hand runtime evidence of some functionality, not a complete acceptance report.
- Latest source branch PR #111 has a successful GitHub Actions test run: https://github.com/Nithin0553/CutsceneAI/actions/runs/42691655435.
- PR #110's Start Transfer state repair, PR #109 companion handshake, PR #108 manifest synchronization, PR #107 error disclosure, PR #106 layout/home, PR #105 explicit source census, and PR #104 native light/readback changes are included by ancestry.
- PR #111 adds a guarded static-mesh `static_materials` slot lookup and regression test to supplement the skeletal `materials` path. Its real Unreal 5.8 runtime behavior still requires a test against an exact Unity source material.
- Native editable sequence generation must be distinguished from source-faithful behavior, post-reopen persistence, material appearance, and audio waveform comparison.

## GitHub code checks (required on this exact branch)

Run CI on the integration branch and on its draft PR to `main`. Inspect the precise HEAD SHA rather than relying on an older branch's green badge. CI runs `compileall`, `pytest`, JavaScript syntax and Studio UI tests, Ruff checks, and `tools/repo_check.py`. Check the test skip reasons; engine-dependent skips are NOT real-editor passes.

From the repo root:

```powershell
python -m pip install pytest ruff jsonschema "langgraph>=1.0,<2"
python -m compileall -q packages tools integrations/unreal
python -m pytest -q
node --check apps/studio-web/app.js
node --check apps/studio-web/cinematic.js
node tests/studio/test_cinematic_ui.cjs
python -m ruff check tests
python tools/repo_check.py
```

## Windows Unity / Unreal acceptance before merge to main or closing #93

1. Back up the Unreal project; do not alter the original Unity project or the frozen benchmark snapshots.
2. Check out **this exact branch/commit**, restart Studio and the Unreal Editor so that cached Python companion modules do not survive branch changes, and verify worker version / checkout fingerprint.
3. Export the *selected* Unity Timeline CSIR and matching Source Census. Record Unity and Unreal versions, CSIR SHA-256, census SHA-256, source project, selected cutscene, engine project paths, and destination level.
4. Start a **fresh** transfer with agents disabled; allow only source-backed asset imports into a new staging namespace. Confirm editable target sequence exists, imports have expected native classes, and assets do not overwrite user content.
5. Exercise the repaired Start Transfer / Start New Transfer paths, no active job versus running job, and safe recovery after interruption.
6. Inspect prop static material slots and character skeletal material slots, with exact source material GUID / texture identity; preserve existing nondefault custom Unreal material assignments.
7. Run native readback, hierarchy and visual audit. Save level and sequence, close Unreal Editor, open a *new* Editor process and repeat persistence/readback. Record source/target CineTwin captures at matched time points where available.
8. Capture full receipts and release gate with `python tools/studio_release_audit.py`; do not mark unknown/partial as PASS. Run separate, opt-in AI experiment only when source-grounded repair evidence and cost consent are available.
9. Repeat on a second independent Unity source project/Timeline before making generalization claims.

Refer to `docs/studio/ISSUE_93_INTEGRATED_SMOKE_TEST.md`, `docs/studio/RELEASE_ACCEPTANCE.md` and `docs/studio/ISSUE_PR_TRIAGE_POLICY.md` for more detailed procedures.

## Issue / PR disposition rules

- **#93 integration:** keep open until merged code, automated checks, and fresh editor smoke test pass. The current successful-but-imperfect transfer is not evidence of zero regression across the new consolidated head.
- **#94–#98:** keep open: source completeness, executable CED adapters, motion/hierarchy, camera/lighting/material/audio, and cross-engine CineTwin evidence still have unresolved scope.
- **#99:** keep open: safe automated repair has not been demonstrated across all advertised supported domains.
- **#100:** keep open: held-out source-project learning improvement not established.
- **#101:** keep open: release, installation, security and real-editor acceptance incomplete.
- **Legacy stacked PRs #49–#52, #75–#83, #87–#92, #102, #104–#111:** preserve pending a merged reviewed integration, verify original changes are present (or intentionally superseded), then triage individually. Do not mass-close issues or delete branches as an alternative to acceptance testing.

## Next engineering issue once integration is accepted

Target #94 and #97 using exact source/target material and asset evidence, then #96 and #98 using measured walk/wave, camera, transforms, hierarchy and pose parity. Record each defect as source evidence → failing native adapter/readback → test and staged patch → independent engine re-test, without inventing semantic equivalence for missing custom features.
