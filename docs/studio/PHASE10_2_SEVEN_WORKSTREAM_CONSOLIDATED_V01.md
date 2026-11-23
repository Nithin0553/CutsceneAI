# Phase 10.2 — Consolidated Seven-Workstream Software Contract (v0.1)

**Scope:** One integration branch covering all seven original Phase 10.2 work
areas, based on the eleven guarded native repair adapters through PR #160.
This consolidation adds a bounded multi-key yaw adapter and hardens
source-domain contracts; it does **not** claim universal Unity→Unreal
semantic conversion, a completed engine benchmark, or fully accepted
Phase 10.2. The original seven workstreams remain separate acceptance gates.

**Source of truth:** Original CSIR and Unity source CineTwin observations;
immutable prepared source mapping, transfer actions, Element 3–6 stage
identity and independently reopened Element 7/8/9 measurements. An adapter
catalog, LLM suggestion, synthetic test or generated asset is **never** a
substitute for runtime measurements.

## Workstream-by-workstream implementation and outstanding acceptance

| # | Work area | This consolidated implementation | Remaining hard acceptance |
|---|---|---|---|
| 1 | Autonomous animated-camera curve repair | Existing single position, dual position, single yaw adapters plus new 2–8 **nonadjacent, interior, source-measured yaw** key repair. Full native nine-channel inventory, original existing source key ownership, exact counted feedback, readback, save and compensating rollback. | Multi-axis pitch/roll, arbitrary camera paths/tangents, wrapped/gimbal or blended camera rigs, postrepair independent opened editor and image trajectory comparisons |
| 2 | Complex Timeline blending and multi-camera transitions | New `timeline_blend_policy.analyze_complex_timeline` source-complete read-only census of camera cuts, overlapping cut owners, easing, nested shots, retimed/timewarp metadata and unmapped track bindings. Existing exact two-shot switch adapter retained. | Real native nested sequence, blending/mixer, >2 shot and camera transition implementation; source-vs-native frame/section and rendered continuity checks |
| 3 | Moving-character positioning/facing/root motion | Measured actor-world trajectory and static-root adapter retained. Tightened actor/root quaternion and position validation; malformed, nonfinite, duplicate, out-of-range or incomplete sampled actor motion cannot become native key instructions. | General moving skeletal-root compensation, imported mesh forward-axis ownership, competing actor/root corrections, actual native pose/actor parity |
| 4 | Advanced skeletal retargeting/bone calibration | Existing approved source/target reference-bound per-bone pose bake retained. Added source bone-parent ancestry/cycle validation and hemisphere-continuous source-derived native rotation key output. | Real independently approved native rest skeleton ancestry, IKRig/IKRetargeter authoring and calibration, target vertex/skin deformation parity, rig blending and real engine |
| 5 | Multi-character coordination/animated hierarchy | New deterministic `multi_character_sync` checks 1–32 original mapped characters against one complete source display-frame grid, detects duplicate source IDs/poses, missing frame, cycle/unresolved parent, foreign target labels, actor-world spatial/facing drift and pairwise separation. | Executable coordinated multi-character animator/retarget/root ownership, interactions, attachment persistence, contacts and synchronized rendered playback |
| 6 | Lighting/shaders/audio/VFX/events/physics | New `phase10_2_effects_coverage` groups every encountered canonical source occurrence by six explicit domains; reconciles actual compiled native action candidates through the original CED dispatcher. Marks lossy audio/event marker mappings explicitly non-equivalent, unknown shaders/VFX/physics report adapter gaps. | Native adapters, recorded waveform/photometric/particle/physics/event side-effect comparison and custom plugin semantics, all individually proven |
| 7 | Production-contract audit, matrix and regression | New `phase10_2_consolidated_audit`, exact recomputation/forgery refusal, immutable once-only candidate CLI, release-gate integration, synthetic domain regressions and documented capability matrix. | Real Unity and Unreal compilation, native save/reopen, CineTwin image/skeleton/effect parity, independently measured held-out project compatibility and release decision |

The matrix is intentionally explicit about **what remains unimplemented**.
It is incorrect to describe these seven areas as accepted simply because
their source diagnostics and test contracts are in place.

## Camera bounded yaw-curve authority

- `restore_bounded_animated_camera_yaw_keys` permits **2–8** original
  interior, nonadjacent, source-world-measured yaw-only key discrepancies
  of **3°–30°**, exclusively on one newly staged unparented CineCamera.
- The user must explicitly request the same number of animated camera
  yaw keyframes (two through eight). "All", "multiple", pitch/roll,
  position, rig, shot and broad curve language never authorizes execution.
- Every source display-frame original quaternion, exact native unwrapped
  Unreal yaw representation, same-frame native observed quaternion and
  physical orientation discrepancy must agree. Uncertain pitch poles,
  ±Euler alias, non-unit camera scale, competing position/pitch/roll,
  different native key interpolation/frame times, lens/cut mismatches,
  extra owner tracks/attachments, source plan mutation and prior
  remeasurements refuse the operation.
- The native executor checks **all nine Sequencer transform channels**
  against the source-authenticated original frame grid **before any
  write**, edits only the specified existing yaw keys, rechecks **all
  original keys and scale defaults**, and saves only the generated Level
  Sequence. A write, immediate readback or save failure attempts to
  restore **every changed original value**, including after a setter
  mutates then raises; a failed save may still require manual asset
  inspection, not a blind retry.
- Native receipt
  `BOUNDED_ANIMATED_CAMERA_YAW_KEYS_SAVED_REOPENED_CINETWIN_PENDING`
  only confirms immediate software/Sequencer path expectations. No
  post-repair independent CineTwin or rendered fidelity is inferred.

## Source/source-target auditing

Pure, recomputable `phase10_2_consolidated_audit.audit` uses the
actual `feature_dispatch.audit`, `timeline_blend_policy`, effect
capability ledger and measured multi-character source frame checks.
All original CED source occurrences remain in the report, including
unknown plugin tracks. Every work area has explicit `remaining_gates`
and engine verification booleans defaulting to **false**.

For a genuine existing Studio job (no engine is started by this command):

```shell
python tools/phase10_2_audit.py --workspace /path/to/studio-runs --job-id 0123456789abcdef0123456789abcdef --write
python tools/phase10_2_audit.py --workspace /path/to/studio-runs --job-id 0123456789abcdef0123456789abcdef --verify
```

The command recomputes the exact original job/candidate source CSIR,
target mapping and compiled plan through the existing Element 9
provenance verifier; refuses malformed IDs, symlinked/replayed or
existing output; hashes canonical source/action data; and writes only
`phase10_2-consolidated-audit.json` under that original candidate
using exclusive creation. The release gate compares a saved receipt to
a **freshly recomputed** result. An exact software-audit PASS does not
override independent rendered/engine blockers or authorize new writes.

## Software validation

- Python source-ownership, timing, moving/root, skeletal and camera
  regression fixtures, including two changed yaw-key setter/rollback.
- Exact seven-area manifest cross-check against **actual LangGraph
  allowlist and native executor dispatch**; no documentation-only
  adapter is counted as executable.
- Source event/audio/etc lossy adapter tests never claim executed
  gameplay signals or audio/video parity.
- CI must pass Python tests, syntax, Ruff, 19 Studio UI scenarios,
  repository hygiene/navigation, CED policy training/integrity and
  Windows dependency bootstrap for the **exact feature head**.
- Repeat on the merged **integration commit** before handoff.

**Deferred real engines by project decision:** No actual Unity/Unreal
editor executable, imported target rig asset, reopened native project,
CineTwin postrepair run, rendered frame comparison or physical collision/
audio/event replay is run in this software-only phase.

## Acceptance status

As of this software increment, all **seven work areas have explicit
remaining acceptance requirements**. Broad "Phase 10.2 complete" and
"perfect Unity→Unreal transfer" are **not supported**. Phase 10.3/10.4/10.5
and real engine test remain distinct, with no silent scope downgrade.
