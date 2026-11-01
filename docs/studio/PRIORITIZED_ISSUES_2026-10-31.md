# CutSceneAI Studio — prioritized GitHub issue queue (2026-10-31)

This is the active **issue-triage and execution order**, not a statement that all features work. The 22 previously open technical issues remain open after a title/body audit; their acceptance criteria require missing implementation and/or actual Unreal runtime evidence. A passing mock-based Python CI suite or functioning browser UI does **not** satisfy those requirements. New issue #84 tracks safe recovery from partial native imports.

## Current evidence baseline

- Integrated working branch: `feature/studio-ui-connected-v0.3` (known-good preceding triage: `cc9c079`; GitHub CI: 475 passed, 7 external-evidence tests skipped; JavaScript, lint, repository hygiene passed).
- `main` is behind the integrated Studio development branch; neither the draft PR chain nor Benchmark001 is merged/rewritten by this triage.
- Latest user observation: **the user reported that the Studio test succeeded locally** after the automatic transfer run. Treat this as user-reported positive runtime evidence, but the specific native setup receipt, Unreal generated sequence receipt, saved/reopened asset inventory, and independent fidelity measurements have not been inspected in this tracker. Do not equate this report with a structurally proven saved scene or with source-to-target parity.
- Added the opt-in, read-only [post-reopen persistence audit](POST_REOPEN_PERSISTENCE_AUDIT.md) to inspect the current Unreal project's saved assets, actors and sequence after reopening. Its report cannot independently prove a restart and does not claim fidelity.
- Source project and frozen Benchmark001 remain read-only. Do not overwrite existing target Level Sequences or delete in-use Unreal UObjects.

## Priority definitions

**P0 — next supported end-to-end run and correctness gate.** A bug here prevents or invalidates first real source-backed transfer or safe recovery.

**P1 — semantic fidelity, learning and generalization.** Begin once a real target can be built, saved, reopened and audited; can run in parallel when independently testable.

**P2 — advanced feature extension.** Keep tracked, but do not block the first demonstrable research-quality vertical slice.

## P0 — execute in this dependency order

| Order | Issue | Immediate deliverable / gate |
|---|---|---|
| 1 | [#84 — Safe interrupted-import recovery](https://github.com/Nithin0553/CutsceneAI/issues/84) | Fail closed before native mutation; durable partial-operation receipt; no blind replay. Mock tests first, engine proof to close. |
| 2 | [#55 — CUT-02 Asset/actor mapping](https://github.com/Nithin0553/CutsceneAI/issues/55) | Run authentic 18-source-file/10-actor preparation in backed-up Unreal 5.8; prove native assets, skeleton/type checks and exact source mappings. |
| 3 | [#54 — CUT-01 Level Sequence persistence](https://github.com/Nithin0553/CutsceneAI/issues/54) | Run prepared sequence builder, Save All, close/reopen, independently read back native data, attach logs/hashes. |
| 4 | [#62 — CUT-09 Hierarchy persistence](https://github.com/Nithin0553/CutsceneAI/issues/62) | Verify attachments, actor mobility and source/target hierarchy after Unreal restart. |
| 5 | [#68 — CUT-15 Source hierarchy coverage](https://github.com/Nithin0553/CutsceneAI/issues/68) | Classify all 19 unbound source records as helper/component/rig/semantic actor and report required missing behavior explicitly. |
| 6 | [#72 — CUT-19 Independent validator](https://github.com/Nithin0553/CutsceneAI/issues/72) | CineTwin source-target aligned observations, per-feature metrics and required-domain PASS/FAIL/INCOMPLETE. |
| ongoing | [#80 — Studio master release checklist](https://github.com/Nithin0553/CutsceneAI/issues/80) | Track complete vertical slice, trustworthy verified case-memory loop, held-out experiment and paper-ready evidence. |

## P1 — next fidelity and research work (rough dependency order)

| Issue | Target |
|---|---|
| [#74 CED-01](https://github.com/Nithin0553/CutsceneAI/issues/74) | Full CED-first discovery/versioned policy for unknown/custom elements and partial actions |
| [#61 CUT-08](https://github.com/Nithin0553/CutsceneAI/issues/61) | Moving-parent/child world-motion and attachment validation |
| [#56 CUT-03](https://github.com/Nithin0553/CutsceneAI/issues/56) | Rendered character placement versus actor/component/root |
| [#57 CUT-04](https://github.com/Nithin0553/CutsceneAI/issues/57) | Root-motion ownership, orientation and trajectory |
| [#63 CUT-10](https://github.com/Nithin0553/CutsceneAI/issues/63) | Camera world pose, movement and framing |
| [#59 CUT-06](https://github.com/Nithin0553/CutsceneAI/issues/59) | Skeletal blends/transitions and final-pose hold |
| [#60 CUT-07](https://github.com/Nithin0553/CutsceneAI/issues/60) | Weighted/overlapping transform curves |
| [#69 CUT-16](https://github.com/Nithin0553/CutsceneAI/issues/69) | Sequencer exclusive-end frame timing |
| [#66 CUT-13](https://github.com/Nithin0553/CutsceneAI/issues/66) | Real WAV/MP3, audio section timing/fade/loop/mix verification |
| [#70 CUT-17](https://github.com/Nithin0553/CutsceneAI/issues/70) | Materials, texture bindings, exposure and visual pipeline differences |
| [#58 CUT-05](https://github.com/Nithin0553/CutsceneAI/issues/58) | Explicit rig compatibility and retargeting |
| [#64 CUT-11](https://github.com/Nithin0553/CutsceneAI/issues/64) | Lens/filmback and measured composition parity |
| [#73 CUT-20](https://github.com/Nithin0553/CutsceneAI/issues/73) | Generalization on independent/held-out Unity projects and research evaluation |

## P2 — extend after P0/P1 baseline

| Issue | Target |
|---|---|
| [#65 CUT-12](https://github.com/Nithin0553/CutsceneAI/issues/65) | Photometric light curve/rendered shadow equivalence |
| [#67 CUT-14](https://github.com/Nithin0553/CutsceneAI/issues/67) | Safe executable signals/event payload semantics |
| [#71 CUT-18](https://github.com/Nithin0553/CutsceneAI/issues/71) | Physics, constraints, sockets and nondeterministic simulation |

## Closure policy and evidence contract

Do not close based on: mock-only tests, source-inventory presence, planned action support, a green UI, a saved `.uasset` without reopen, or merely having a corresponding draft PR. A completed technical issue must link an exact tested implementation commit, reproducible input fingerprint, a target Unreal project/version, a saved/reopened generated target (when applicable), an independent readback or behavioral result, and all its acceptance items. Mark unsupported items INCOMPLETE or BLOCKED; never suppress them to create a false PASS.

The first local editor experiment must retain: `automatic-setup.json`, `automatic-setup-receipt-*.json`, native asset-class/actor-label inventory, `transfer-plan.json`, `coverage-report.json`, `evidence.json`, native generation receipt, independently reopened readback report, and CineTwin sample comparison where present. Do not upload copyrighted third-party game assets to issues.

## Git workflow

The branch `feature/studio-ui-connected-v0.3` is the current working surface for Studio patches, not a mandate to blindly merge its 195-commit draft stack into `main`. Preserve the existing 13 open PRs while later reconciling dependencies/SHAs carefully. Develop the next P0 change as a focused commit, run Python + JavaScript + hygiene CI, report the commit, and only then have the user `git pull` and test the Unreal Editor companion.

## Latest completed gate: saved native structure (2026-10-31 local test)

The user ran the post-reopen native audit and reported:
`native_structure_status=PASS`; imported saved assets **18/18**, unique correctly typed mapped actors **10/10**, target level saved, LevelSequence saved, **12 sequence bindings** and **3 root tracks**. This verifies the native package/class/actor inventory for the current run, **not** all source tracks, performance, source/target runtime motion, or semantic parity. Two older setup receipt identifiers remain missing (`setup_receipt.target_sequence` and `setup_receipt.target_namespace`), so provenance remains `INCOMPLETE_LEGACY_RECEIPT`. Issues #54/#55 retain other acceptance criteria, including independently authored cases and complete per-feature evidence.

**Current next gate:** [#62 hierarchy persistence](https://github.com/Nithin0553/CutsceneAI/issues/62), using the read-only [Unreal hierarchy audit](POST_REOPEN_HIERARCHY_AUDIT.md). It compares direct actor parenting, socket and component mobility against authoritative Unity CSIR source IDs. Any unresolved intermediate transforms are `INCOMPLETE` and feed [#68](https://github.com/Nithin0553/CutsceneAI/issues/68). Actual CineTwin source-aligned world motion remains a separate [#72](https://github.com/Nithin0553/CutsceneAI/issues/72) acceptance gate. Mock CI for this audit: **508 passed, 7 skipped**; no native hierarchy result yet.

## Hierarchy failure and corrective implementation (2026-10-31)

**Real post-reopen hierarchy audit** of the initial Studio-generated candidate:
`HIERARCHY: FAIL`, `direct attachments 0/2`, `mapped source roots 0/0`, `unresolved source parents 8`. Both `MovingPropMesh` and `PROP_PARENTED` lacked their mapped Unreal parent and were observed detached. The eight source entities with unmapped immediate parents were `CAM_A_Wide`, `CAM_B_Move`, `CAM_C_Close`, `CUTSCENE_DIRECTOR`, `Ch26_nonPBR`, `Ch31_nonPBR`, `LIGHT_KEY`, and `PROP_MOVING`. These are not necessarily missing world actors; inspect the complete chain of source transform-only/helper nodes before classifying as lost content.

**Code change:** Studio automatic preparation now enables the existing `enable_cinetwin_hierarchy` policy in the **fresh copied mapping** instead of silently leaving it off. The source-authenticated plan runs `hierarchy_local.reconcile_hierarchy`, then the Unreal builder runs `hierarchy_realization.build_attachment_operations` and `cinetwin_hierarchy_runtime.apply_hierarchy` only if supported. Unsafe world-space child tracks are converted to validated parent-local motion or rejected **before** native mutation. The imported actor scene is saved after builder attachment updates. This path requires a brand-new trial; the old tested sequence and Benchmark001 are immutable.

**Verification so far:** source-to-plan prop regression + full repository CI, not yet a new real-editor hierarchy PASS. Re-run automatic transfer with a new candidate into a backed-up target, save/reopen Unreal, and rerun `studio_hierarchy_audit.audit_latest()`. The eight unresolved relationships remain #68 and will still be reported as incomplete until source intermediate nodes/proxies or other equivalent mappings are designed and independently checked. Keep #62 OPEN until real Unreal attached actor readback and motion parity are demonstrated. No amount of suppressed warnings substitutes for a verified source-parent transfer.


## Source-parent coverage follow-up (2026-11-01)

Real Unreal evidence confirms 2/2 mapped direct prop attachment links, and
18/18 imported assets and 10/10 actors. The hierarchy audit still reports
8 mapped actors with unmapped *source ancestor* GameObjects. A previous Unity
Benchmark002 CSIR shows the organizational group objects Benchmark002,
CHARACTER_A and CHARACTER_B at the ancestor levels. Benchmark002 has
nonidentity source translation. These are distinct from the 19 source
entities that have no independent actor bindings.

**Shipped:** source-ID parent-chain analysis and evidence-based world-pose
strategy classification in the transfer coverage report and read-only
Unreal hierarchy audit. World-space source motion can be planned without
blindly generating a parent that changes already-baked world keys. CI:
543 passed, 7 skipped, lint/hygiene PASS. See
[SOURCE_PARENT_RESOLUTION.md](SOURCE_PARENT_RESOLUTION.md).

**Still open P0:** [#85](https://github.com/Nithin0553/CutsceneAI/issues/85)
for full editable Unreal parent-group proxy actors, parent-local motion
conversion and real-engine proof. Prior existing generated sequence remains
untouched. Native structure PASS != all feature parity; #72 still requires
independent matching-time evaluation. Do not claim that warning
classification alone resolved incomplete transfer.
