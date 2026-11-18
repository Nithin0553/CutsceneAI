# CutSceneAI Studio — End-to-End Software Completion Contract

**Software release candidate:** `feature/studio-e2e-release-candidate-v0.1`  
**Combined baseline:** original integration draft PR #124 + Friday's draft PR #126.  
**Constraint:** Finish and verify the *software* with synthetic and contract tests
before requesting the first new Unity/Unreal workstation test. Do **not** merge
into `main` yet. Do **not** report full source-target cinematic fidelity from CI.

## Product goal

A project-level AI agent examines the selected Unity source scene, its Timeline,
assets, motion/hierarchy/component evidence, and the actual loaded Unreal
destination. It determines **which installed source-backed conversion adapters
are eligible**, prepares a provenance-locked native conversion, executes only
guarded engine operations, measures supported properties, and clearly labels
losses. If a detected discrepancy has a verified isolated repair, an AI-selected
bounded correction can be attempted and remeasured; otherwise the product must
refuse it with a meaningful explanation.

**No unrestricted model-generated Python/Blueprint/C++**, invented mesh/bone
mappings, arbitrary source-file access, silent overwrite, or claim of perfect
conversion. Every capability is versioned, testable, and either VERIFIED,
PARTIAL, UNSUPPORTED, or INSUFFICIENT_EVIDENCE.

## Software pipeline and current state

| Domain | Current source-grounded implementation | Software completion gap |
| --- | --- | --- |
| Project selection | Folder discovery, exact Unity project and Unreal `.uproject`, target level identity, permissions | Finalize first-run setup, errors, and project-switch recovery |
| Unity source | CSIR, scoped source-component census, source GUID/FBX/meta hashes, Play Mode CineTwin sample capture | Compile/review changed Unity extractor after software freeze; add missing semantic exporters as typed schema extensions |
| Unreal destination | Editor-thread worker, project and level checks, actor census, IK/asset probes, exact hashes | Complete broader read-only component/shader/asset capability inventory and validate feature flags |
| AI planner | OpenAI Responses structured choice, redacted counts, approved IK retarget and source-bound one-character actor-world motion actions | Broad root-only/compound/multi-character strategies remain unsupported/refused; no universal adapter claims |
| Native conversion | Immutable transfer plan, source-provenanced import/retarget/material/camera/track adapters, no-overwrite checks | Extend supported asset types, time-varying root/actor ownership, tested non-humanoid/humanoid policy, and never silently promise equivalent simulation |
| Native execution | Same-project/level verification, immutable native generation, partial-import inspection receipts, no-replay native recovery and live idle Python refresh | True editor-process persistence, more asset-class coverage and exceptional corrupt-package recovery remain separate |
| AI evaluation and correction | CineTwin actor/root, mapped joint angular-motion magnitude diagnostics, LangGraph analysis, physical camera FOV comparison, native cut binding/section audit and narrow source-bound repair strategies | Calibrated joint orientation-axis/bind-basis parity, exact rendered projection/cut parity and additional *registered* safe repair adapters |
| Review UI | Dark minimal Studio, one-click transfer, AI planning progress, provenance audit, pre-native cancellation and subdued live Unity/Unreal bridge health | Complete setup, support/refusal scope and recovery guidance for all declared domains |
| Release evaluation | Canonical per-job release gate, exact native readback, AI/IK and reopened temporal checks, recomputation of source-bound actor/rig/camera comparison | Complete visual/audio/physics/event/held-out acceptance artifacts and sign-off criteria |
| CI and packaging | Integrated synthetic transfer smoke, Windows Python bootstrap, UI contracts, lint, source syntax and regression/security coverage | Full native companion installer and self-contained desktop distribution are not yet verified |

## Required software completion gates before engine testing

1. **One-click orchestration**: state machine covers start, Unity capture, both
   project inspections, model invocation, planning, prepare, native execution,
   results, pre-native cancellation, and terminal failure; never queue twice.
   A transient worker disconnect must not cause an unsafe plan or replay.
2. **Model decisions are consequential but bounded**: at least one eligible
   asset, character, camera, and motion scenario has a typed strategy that
   actually changes the native plan and is rejected by the independent engine
   preflight if stale/ambiguous. Add positive and refusal unit fixtures for each.
3. **Cross-engine semantic inventory**: every source component used by the
   test scenes is mapped to supported, partial, or unsupported with provenance.
   No unsupported motion/rig/camera/asset type may silently become accepted.
4. **Project preservation**: no original Unity asset edits; no target sequence
   overwrite; no arbitrary project changes; side effects confined to a new
   candidate and explicit target level with native receipts.
5. **Independent measurement**: full source frame grid and matching Unreal
   samples for supported actor/root transforms, selected joints, timing and
   visibility; planned vs actual asset classes, source identifiers, hierarchy
   and retarget output are checked. Source-scope misses must remain failures or
   incompletes, not fabricated data.
6. **Error states**: source mismatch, unavailable engine API, stale worker,
   unsupported IK/motion, absent key, timeout, partial import, changed hashes,
   wrong level, and lack of readback all have deterministic, no-replay behavior.
7. **Review & release contract**: UI differentiates AI decision, native
   generation and verified behavior. Release gate is fail-closed, source-bound,
   and requires a separate Unreal process to establish persistence.
8. **Automated freeze**: entire Python/JS/contract suite green; the code-only
   integrated transfer scenario and negative security/identity cases pass;
   no TODO claiming an unsupported feature is transferred.
9. **Live engine bridge continuity**: after explicit initial opt-in, Unity
   reconnects after ordinary C# domain reload; the already-open Unreal Editor
   refreshes trusted Python worker/adapters only when native execution is
   idle. Stale/wrong-project/invalid heartbeats must refuse native work;
   changed source must not resubmit a queued, running or uncertain candidate.
   Compiled native engine changes may still require an editor restart.

**Engine acceptance remains a subsequent distinct gate** even after these
software criteria. Unity compilation, true OpenAI provider calls, Unreal
asset/sequence save/reopen and real cross-engine visual/audio fidelity can only
be proven on the workstation. The user has requested that testing phase be
deferred until software freeze.

## Work allocation

- **Primary developer (this branch):** orchestration, safety/recovery, AI
  provenance audit, canonical release gate, UI and integration tests.
- **Friday (draft PR #126 / issue #125):** source/target character
  compatibility, more complete native motion/asset strategies, typed retarget
  decisions, exact post-conversion readback and its source-bound verification.
- **Shared integration:** avoid changes to the same files without coordinating.
  Preserve Friday's draft PR as an independently reviewable history. A stacked
  release PR may reference both PRs; no automatic merge or engine pass.

## Current release-candidate improvements

- Combined baseline contains Friday's typed one-character approved IK Retargeter
  strategy and existing pre-transfer OpenAI decision planner.
- Fixed `ANALYZING_PROJECTS` to count as an active transfer in the minimal UI.
- Pre-native `CANCELLED` state and local token-guarded endpoint; queued or
  running Unreal native work cannot be interrupted.
- Job-bound AI Transfer Audit separately displays selected IK strategy,
  character compatibility outcomes and independently confirmed skeleton/clip
  section readback. Synthetic/model-only receipts are not native success.
- Extended the **existing** `packages/studio/studio_release_gate.py`
  (not a competing second gate) to check provider identity, character
  retarget receipts and source-bound post-reopen temporal measurements.
- Added source-hash, wrong candidate, plan tampering, no receipt, offline and
  cancellation regression tests.
- Added the integrated software-only synthetic transfer regression
  `tests/studio/test_studio_software_e2e_synthetic.py`: validates the canonical
  Unity capture sampling grid, native Unreal target inspection, production
  OpenAI Responses schema via mocked transport, new immutable candidate and
  queue handoff, mocked native skeleton/clip readback, AI transfer audit,
  independent release gate and tampered-decision refusal. Even its synthetic
  successful native receipt is **not** a real-engine fidelity pass.
  Reviewed first green integrated CI: commit `ca1496ce`,
  [960 Python tests passed, 7 skipped, Windows bootstrap and UI/ruff green](https://github.com/Nithin0553/CutsceneAI/actions/runs/44399720465).
- Added independent **sampled camera optics** and **native camera cut timing**
  checks. Unity's Play Mode camera vertical FOV is compared at source frame
  timestamps with Unreal CineCamera filmback sensor height and focal length;
  invalid, missing or inconsistent physical camera evidence is refused.
  Source camera cut bindings and exact section bounds are recorded in the
  source sampling-plan contract and compared against independent Unreal
  Sequencer camera-cut track/binding readback, including native FrameNumber
  values. Missing, overlapping, subframe, ambiguous and changed cuts cannot
  claim exact timing parity.
- Added source-matched skeletal **joint angular-motion profiles** for
  uniquely mapped native bones. Each sampled frame compares stepwise and
  first-frame-relative angular displacement magnitudes, which do not require
  guessing an absolute cross-rig orientation basis. Missing or ambiguous bone
  correspondence stays INCOMPLETE; mismatched motion magnitudes are reported
  and tested. This is **not** calibrated joint axis/bind orientation parity.
- Post-reopen acceptance and the canonical release gate now separate actor/root,
  camera lens and authored cut timing outcomes. The release gate recomputes the
  whole behavior comparison from exact saved source and target samples and
  rejects altered metrics, foreign CSIR/capture hashes and fabricated PASS
  reports. These checks establish only **measured structural/time/lens scope**,
  not a rendered-equivalence claim. CI includes normal and adversarial camera
  fixtures; genuine UE 5.8 editor execution remains untested.
- Friday's F-003 [draft PR #130](https://github.com/Nithin0553/CutsceneAI/pull/130)
  delivered a source-bound, **one unparented translating/turning character**
  actor-world trajectory strategy using a previously approved native IK
  retarget profile, one supported FBX take and one demonstrably stable
  actor-relative skeletal root. The primary developer reconciled Friday's
  native motion receipt checks with the camera/joint-release gates in
  [draft integration PR #131](https://github.com/Nithin0553/CutsceneAI/pull/131).
  The combined software-only test run had **1,082 passed, 7 skipped**,
  with Windows setup and 14 UI contract scenarios green
  ([CI 44416807812](https://github.com/Nithin0553/CutsceneAI/actions/runs/44416807812)).
  Review scope and exact remaining blockers are in
  [PRIMARY_F003_INTEGRATION_REVIEW.md](PRIMARY_F003_INTEGRATION_REVIEW.md).
  Neither genuine Unity/Unreal execution nor full fidelity is established.
- Added bounded (60-minute) source Play Mode capture and (180-second) read-only
  Unreal character-probe waits. Expired requests report a safe terminal failure;
  they never invent samples or submit a native job.
- On a restart between durable native job submission and UI state update, Studio
  now reconciles the exact persisted candidate/job rather than queuing again.
  Ambiguous, symlinked, wrong-target or tampered job records fail closed. If
  a prepared candidate is detected after interrupted preparation, Studio
  preserves it and refuses silent duplicate preparation.
- Added checkout-based Windows bootstrap (`tools/install_studio.ps1`), isolated
  launch (`tools/start_studio.ps1`), read-only diagnostics
  (`tools/check_studio_setup.py`), Windows CI dependency preflight and
  [local setup instructions](STUDIO_LOCAL_SETUP.md). This checks localhost
  prerequisites, NOT actual Unity/Unreal companion install or native acceptance.

## Deliberately NOT completed in current release candidate

1. **Broad skeletal-root or compound motion conversion** beyond the
   new bounded actor-owned moving/turning-character action. The code refuses
   parented, layered, looping, humanoid, independently moving skeletal-root
   and simultaneous multi-character cases rather than inventing offsets.
   Historical Ch31 actor/root errors do not justify one fitted correction.
2. **General-purpose arbitrary asset conversion** (all shaders, all textures,
   audio, VFX, arbitrary avatar rigs, scripts, simulation components) and
   semantic engine behavior equivalence.
3. **Comprehensive rendered camera/projection parity + full joint pose
   orientation** across all frames and sequences. Camera FOV and authored
   cut sections now have bounded source-vs-native software comparison, but
   they do not prove rendered composition, post-process, exposure, active cut
   frame imagery, or calibrated cross-rig joint orientation. Scene-editable
   generation and native asset readback are not visual fidelity certificates.
4. **First-run distribution installer** and a truly self-contained app
   that needs no manual Unity/Unreal companion bootstrap. A source-checkout
   Windows Python bootstrap now exists, but it is not standalone distribution
   or confirmed in-editor companion installation.
5. **Full AI-driven repair loop** for all detected defects, robust across
   repeated native restart, uncertain evidence and engine versions.

These are not documentation-only open items. Either complete a bounded,
verifiable supported subset in code and test it, or explicitly exclude that
domain from the versioned release scope with clear user-visible refusal.

## Primary F-003 software-review decision

**CODE-ONLY ACCEPTED FOR THE BOUNDED ACTOR-WORLD CONVERSION ACTION.**
Friday F-003 may be included in the combined release candidate, with a
versioned action catalog, independent native structural readback, refusal
tests and a no-replay journal. The review is recorded in
[PRIMARY_F003_INTEGRATION_REVIEW.md](PRIMARY_F003_INTEGRATION_REVIEW.md).
**No `SOFTWARE_READY_FOR_ENGINE_TEST` decision yet.** Remaining software
scope and companion setup gates must be reviewed first.

## Continuous local engine bridge implementation

- The Unity `[InitializeOnLoad]` companion now retains its opt-in after C#
  script domain reload and publishes a short-lived per-project editor heartbeat
  without modifying Unity scenes. Studio checks its project, process ID,
  timestamp, source-enabled flag and editor mode.
- The Unreal Editor worker now uses one stable tick dispatcher, compiling and
  refreshing changed *trusted* worker Python while idle and synchronizing
  whitelisted native Studio adapter/planner modules after local checkout
  updates. Broken code, stale checkout, and an active or orphaned native job
  fail closed; neither bridge automatically replays a native candidate.
- Studio's minimalist dark UI reports the live Unity and Unreal bridge
  states, and the connection/recovery guidance no longer demands routine
  Unreal Editor restarts for Python-only code changes. Legacy workers may
  need a one-time Python-console upgrade without closing Unreal.
- [Live bridge continuity contract](LIVE_BRIDGE_CONTINUITY.md). Green
  [CI 44420357385](https://github.com/Nithin0553/CutsceneAI/actions/runs/44420357385)
  verified **1,107 Python tests passed, 7 skipped**, 14 UI contract
  scenarios and the Windows dependency bootstrap. **No live Unity script
  compilation, Unreal callback execution or real-engine session test occurred.**
  Engine-required binary/plugin changes can still need an actual restart.
  This feature is software-code verified, not a universal no-restart guarantee.

## When software freeze is allowed

The primary developer records a reviewed commit SHA, an associated successful
CI run, any still unsupported cases, and a code-only `SOFTWARE_READY_FOR_ENGINE_TEST`
decision in this file or a linked release record. Only then proceed to the
user's backed-up Unity 6.3 and Unreal 5.8 projects. A green CI result without
this review is **not** software freeze.
