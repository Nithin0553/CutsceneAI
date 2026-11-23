# Phase 10.4 — Full Source-Only Synthetic Acceptance and Phase 10.5 Handoff

**Integration target:** `integration/element1-9-guarded-repair-expansion-v0.1` (draft PR #149). **Phase 10.4 scope:** complete all software-only rehearsal and negative-test gates, not true Unity/Unreal or rendered fidelity acceptance. Phase 10.5 is opened as a **pre-engine release packaging, freeze and handoff preparation**; it must not silently certify a production release.

## Phase 10.4 full synthetic matrix

`packages/studio/studio_phase10_4_matrix.py` holds the exact **18-gate software acceptance matrix**, each requiring real identified test functions from existing source-only Studio integration suites:

1. Changed Unity CSIR/source hashes and immutable source receipts
2. Genuine Unity Play Mode CineTwin request/capture timeout behavior in a mocked editor
3. Unknown CED/plugins and unregistered native strategy refusal
4. Model-provider interruption and pre-native bounded recovery
5. Rehashed source, exact mapping, per-element review and native consent
6. Wrong Unreal project/level and live native preflight
7. Native setup failure, partial writes and no unsafe cancel
8. Restart after submission and once-only native job claim
9. Interrupted candidate preparation without silent resubmission
10. Distinct-process reopening requirements and false persistence proof refusal
11. Natural-language agent feedback, approval boundaries and repair budget
12. Unsupported shader/VFX/audio/events/physics not becoming false success
13. Immutable Element 9 source-complete results and bounded remeasurement
14. Foreign/held-out CineTwin sources and missing engine evidence
15. Complete mock source-to-Unreal pipeline and resulting incomplete fidelity gate
16. Active job-pointers, cross-run results and stale source exclusion
17. Project-local companion setup and deterministic workstation source distribution
18. Browser-mode/polling/late-response simulations, including default and advanced UI behavior

The matrix checks the exact names of required Python tests using their parsed AST; it checks JavaScript scenario definitions **and actual invocations**. The rehearsal runs all underlying test modules, verifies each specifically selected Python test reported **PASSED** (not skipped), counts all Node scenarios, verifies the exact source file SHA256 before/after and refuses incomplete/no-test output. Missing, renamed, skipped or uninvoked cases fail the gate.

```powershell
python tools/phase10_4_rehearse.py --output "D:\\Releases\\phase10_4-synthetic-evidence.json"
```

The CI workflow runs this command and publishes the immutable receipt named `phase10-4-synthetic-rehearsal-<git-sha>`. The receipt carries the exact suite/module hashes, 18 coverage rows, test outcome hashes, passing/required test counts, and **no native execution/fidelity claim**.

**Acceptance condition:** full pytest, all 26 standard/advanced Studio UI scenarios, Ruff/compileall, CED/repo integrity, Windows isolated setup bootstrap, actual ZIP assembly/integrity, exact Phase10.4 matrix and its named negative tests all pass at **one matching SHA**. This is a **source/software rehearsal**. No Unity or Unreal Editor was launched in CI.

## Phase 10.5 — Software package / pre-engine freeze handoff

A second tool, `tools/phase10_5_freeze_preflight.py`, independently checks:

- Exact 40-hex Git commit equals the local clean tracked checkout `HEAD`.
- Distribution ZIP is verified by `tools/build_studio_bundle.py --verify` with all per-file SHA256 values.
- Phase 10.4 receipt is genuine in format and records a passing full exact-gate rehearsal with **no replay or editor execution**.
- The receipt's original source/test inventory and SHA256 map recompute *identically* against the selected checkout.
- Python and JS test runners both have successful exit statuses and recorded stdout hashes.
- The result is a **pre-engine software handoff**, not a production-release seal. It always lists mandatory native and workstation acceptance as `INCOMPLETE`, `production_release_ready=false`, `final_freeze_authorized=false`.

```powershell
python tools/build_studio_bundle.py --output "D:\\Releases\\CutSceneAI-Studio-source.zip"
python tools/phase10_4_rehearse.py --output "D:\\Releases\\phase10_4-synthetic.json"
python tools/phase10_5_freeze_preflight.py --repo . --bundle "D:\\Releases\\CutSceneAI-Studio-source.zip" --rehearsal "D:\\Releases\\phase10_4-synthetic.json" --commit "<exact-40-character-HEAD-SHA>" --output "D:\\Releases\\phase10_5-pre-engine-handoff.json"
```

The exact-head CI runs this preflight and archives `phase10-5-pre-engine-handoff-<git-sha>`. A failed prerequisite stops the CI workflow, and the reviewer sees which evidence is missing.

## Phase 10.5 work and native gates still outstanding

Before final binary packaging/freeze or merging into the release-candidate branch, verify a clean Windows workstation install, Unity package compilation, Unity Play Mode capture, actual Unreal companion activation and source/target version parity, real model provider invocation, native asset generation/save/readback, a distinct Unreal process reopen, CineTwin and rendered/skin/audio/effects/physics equivalence for supported scopes, and held-out third-party project failures. Record **independent evidence bound to the exact commit**. Unsupported cases must be explicitly reported, not hidden.

The CI artifacts can support a **review for engine testing** but must not be used to claim that any untested cutscene transferred with complete fidelity. The original Element 7/9 release gate remains independently fail-closed, and the installer cannot bypass native or real-engine approval. Until the workstation/engine evidence exists, do **not** mark the Studio as fully frozen or ready for general production.

## CI artifacts and source of truth

- `studio-source-bundle-<SHA>`: source-only ZIP; SHA256 manifest, without executable engine binaries or model weights.
- `phase10-4-synthetic-rehearsal-<SHA>`: named 18-gate software rehearsal receipt.
- `phase10-5-pre-engine-handoff-<SHA>`: independently reconstructed software/handoff preflight and explicit native blockers.
- `ced-trained-policy-<SHA>`: CED policy and source-bound training report, independently validated by CI.

The release-candidate branch and `main` should remain unchanged until reviewers explicitly accept these software artifacts, finish the real-engine acceptance and authorize a final release freeze.
