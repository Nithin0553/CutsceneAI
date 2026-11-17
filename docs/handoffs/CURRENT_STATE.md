# CutSceneAI — Current Engineering State

**Reviewed:** 2026-11-17 · **Primary repository:** `Nithin0553/CutsceneAI` · **Target:** Unity Timeline → Unreal Level Sequence

This is the current orientation handoff. It is not certification of arbitrary source-to-target fidelity. Preserve historical benchmarks and their original evidence.

## Canonical baseline

- **Default branch:** `main`, at reviewed integration commit `5ea7a20401cc7cf6f7ae674973ea7811ffde2909` from [PR #112](https://github.com/Nithin0553/CutsceneAI/pull/112) (2026-11-09). The former `main` is preserved at `backup/main-before-studio-consolidation-20261109`.
- **Code:** Unity source CSIR and feature-surface extraction; CED/source-evidence contracts; adaptive mapping and best-effort planning; source-backed supported asset staging; Unreal scene/Level Sequence generation; editor preflight, native readback, persistence and CineTwin comparison tools; dark Studio UI with opt-in guarded LangGraph diagnosis; experimental dataset and approved-case memory.
- **CI:** [main run 42695836610](https://github.com/Nithin0553/CutsceneAI/actions/runs/42695836610) succeeded on the integration SHA. The GitHub issue records 746 Python tests passed, 7 engine skips, 13 Studio UI scenarios, Ruff and hygiene success. Engine skips are not real-editor passes.
- **User-reported runtime:** a fresh Benchmark002 transfer produced an editable target sequence and passed user-reported saved/reopened editor inspection. No independently retrieved time-aligned CineTwin metrics support overall pose, camera, shader, audio or event parity.
- **Benchmark001:** frozen historical proof; do not modify the original freeze. **Benchmark002:** active experimental source; prior measured actor travel/orientation mismatches and missing scenery mean complete fidelity is not established.
- **Learning:** candidate-memory and orchestration infrastructure exist, but a universal AI cinematic model has not been trained or validated on held-out projects.

## Next engineering step

1. Review [PR #113](https://github.com/Nithin0553/CutsceneAI/pull/113): support scene-renderable FBX scenery even without active Timeline tracks, with exact source identity, negative cases and no arbitrary asset substitution. Verify in Unity 6.3, then run fresh Unreal import, Level Sequence, saved/reopened readback and source-to-target composition checks.
2. Review stacked [PR #114](https://github.com/Nithin0553/CutsceneAI/pull/114): extensible component evidence capture for `LODGroup`, `MeshCollider` and unknown components. It captures source semantics but does **not** yet implement native Unreal collision/LOD adapters.
3. Continue issues [#94–#101](https://github.com/Nithin0553/CutsceneAI/issues) for source coverage, executable CED adapters, motion/hierarchy, camera/render/audio/event fidelity, independent CineTwin, bounded AI repairs, verified learning, and release acceptance. Do not mark unmeasured domains as PASS.
4. Preserve historical unmerged PRs [#6](https://github.com/Nithin0553/CutsceneAI/pull/6) and [#90](https://github.com/Nithin0553/CutsceneAI/pull/90) until their divergent changes are evaluated against `main`; never blindly merge old integration branches.

## Repository cleanup note (2026-11-17)

Twenty-five original stacked draft PRs were closed as superseded after verifying their exact head commits are ancestors of PR #112's integrated head. Their PR records and remote branch refs were retained. Eight active issues (#94–#101) remain open. GitHub branch deletion is a separate operation and requires reviewing local worktree/research dependencies before remote removal. See [Branch Audit](../BRANCH_AUDIT.md).

## Research invariants

- Source identity and rational timing are authoritative; source-derived copies and target runs have immutable fingerprints.
- Do not alter frozen benchmarks, source assets, existing Unreal projects, or previous experiment receipts as part of cleanup.
- `GENERATED_UNVERIFIED`, saved readback, source/target behavior comparison, and release readiness are different gates.
- Never fabricate unknown plugin behavior, rigs, shaders, physics, audio or event equivalence.
- Run a fresh test in a new staged target, then independently reopen and compare behavior before closing fidelity issues.

Read the [Documentation Index](../INDEX.md), [Issue/PR Triage Policy](../studio/ISSUE_PR_TRIAGE_POLICY.md), and [Studio Release Acceptance](../studio/RELEASE_ACCEPTANCE.md) before starting new conversion work.
