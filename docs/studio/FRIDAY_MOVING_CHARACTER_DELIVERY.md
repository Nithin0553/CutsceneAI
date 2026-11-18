# Friday F-003 — moving-character delivery

Tracked by [#129](https://github.com/Nithin0553/CutsceneAI/issues/129), within
the [software completion tracker #127](https://github.com/Nithin0553/CutsceneAI/issues/127).
Branch: `agent/friday-moving-character-motion-v0.1`.
Draft PR target: `feature/studio-e2e-release-candidate-v0.1`.
Reviewed starting RC: `ee807fbc210b84e783d2609729bf0a8c17a8465e`.
The designated branch initially pointed to `8ace5828286b9cfa669fd2f6fa646feb7fbffba7`;
it was fast-forwarded to the latest RC before implementation. Neither the RC,
the old integration branch nor `main` was modified.

Before handoff, the dedicated branch also incorporated the primary developer's
RC `44e7c1ce9aa17869bcd6696744a43dd07f7fd84f`, followed by
`56d46616d83c9ffdbe053dffd716a1f15c775ee5`, without conflicts. The primary
developer's camera optics, cut timing and stricter reopened evidence gates are
preserved. Friday added one missing `Path` import in their new reopened-camera
test so that the combined suite can collect; no camera acceptance gate was relaxed.

## Delivery scope and evidence levels

This delivery implements `bake_verified_actor_world_trajectory`, version 1,
through the existing Studio AI planner, immutable candidate, automatic asset
staging, Unreal worker, Sequencer writer, native readback and release checks.
The new supported case is one unparented moving character with an approved
IK Retargeter and a skeletal root that remains rigid in actor space. Actor
translation and rotation come exclusively from the authenticated Unity capture.
Rotation-only movement is supported. The preceding in-place strategy is retained.

`COMPLETE` below means production code, integration and applicable code-only
automated verification are complete. It never means live-engine acceptance.
Unity compilation, a genuine OpenAI invocation, Unreal native import/save/reopen,
Benchmark002 playback and held-out rigs remain **BLOCKED by the user's explicit
instruction to wait for reviewed software freeze**. No engine was launched, no
workstation project was changed and no real-engine measurement is claimed.

Implementation commit, draft PR and CI links are recorded in the review record
at the end of this document.

## Issue #129 checklist

| Requirement | Classification | Repository verification and limit |
| --- | --- | --- |
| 1 — actor/root translation, rotation and ownership | COMPLETE | All source samples, including boundaries, contribute to actor/root excursion and actor-relative root translation/orientation drift. Turning with a rigid nonzero root offset is a positive fixture. A stationary world root under a turning actor is correctly compound. |
| 1 — complete source frames, identities, unique root and unit scale | COMPLETE | CSIR/capture hashes and complete sampling-plan validation; unique acyclic source rig; exact GUID/subasset identity; export-bound FBX and `.meta` hashes for both model and clip; unit actor/root scales and no parent. Old moving-character exports require regeneration. |
| 1 — unsupported hierarchy/compound refusal before mutation | COMPLETE | No moving action is offered for missing/ambiguous frames, root-only, mixed motion, parents, scales or unsupported assets. AI cannot silently select `keep_native` and drop measured moving motion. |
| 2 — registered consequential typed strategy | COMPLETE | Local versioned action catalog and discriminated JSON schema; model chooses an opaque character ID. The decision changes fresh mapping, clip hold policy and actual native transform keys. No model coordinates or code are accepted. |
| 2 — source, target, profile, actor, sequence and worker binding | COMPLETE | Report/evidence hashes bind the original source mapping, target packages, source capture and actual native PID/project/map. An additional immutable candidate binding identifies the new sequence and exact trajectory. Rechecks run at mapping, preparation, queue and native preflight. |
| 3 — isolated native candidate, frames and basis | COMPLETE | Existing native import/IK adapters and source coordinate converters; measured key at every display frame plus the observed end boundary; native linear keys and unit scale defaults; sequence playback length stays unchanged. Correct display-frame to native-tick conversion for clip trim and final-pose hold. |
| 3 — native track/key ownership and generated animation readback | COMPLETE | The real skeletal-section and transform writers are tested with a synthetic Unreal API. Independent reader validates owning actor binding, one transform track/section, all six channels, exact key frames/values/interpolation, scale defaults, display rate, section ranges, clip skeleton/duration/speed/trim and boundary hold. |
| 3 — prevent root/actor double transforms | COMPLETE | Legacy root-curve corrections and world-lock strategies refuse composition. Raw staged clip roots are sampled across the source clip and used Timeline times before sequence creation; translation, rotation and non-unit scale refuse. Native parent/scale/physics ownership also refuses. The source manifest is revalidated after import to detect concurrent source changes. |
| 3 — independent actor/root trajectories at matched frames | COMPLETE | Existing CineTwin comparison and separate post-reopen acceptance path are retained. Synthetic paired observations verify position/rotation and root errors, missing samples and mismatches. Native readback PASS remains separate from behavioral fidelity. |
| 3 — partial import, disconnect, missing API, stale evidence and recovery | COMPLETE | Native preflight checks available APIs and empty destinations. Durable exclusive one-shot attempt is written before level creation/import. Root inspection and readback failures preserve receipts/assets and prohibit replay. Real worker `_tick`/`_execute` tests include simulated abrupt process loss, partial import and failed readback. |
| 4 — precise clip/asset support and refusals | COMPLETE | Scoped table below; unsupported formats, humanoid/custom takes, loops and overlapping/layered clips cannot obtain this action. Positive tests include source clip trim/speed and 24/30/60/30000:1001 rates. |
| 5 — positive/negative/regression fixtures and anonymized example | COMPLETE | `tests/studio/test_moving_character_conversion.py` and existing in-place/native/AI/regression suites; synthetic example linked below. Exact final counts and CI appear in the review record. |
| 6 — algorithms, changed paths, recovery and acceptance handoff | COMPLETE | This report, versioned schema, synthetic example, draft PR and final CI record. #127 remains open; no merge or freeze declaration. |
| Live Unity/Unreal/provider acceptance | BLOCKED | Deliberately deferred by the user until the primary developer reviews the combined RC and authorizes engine testing. Mock PASS is never recorded as engine acceptance. |

## Algorithm and immutable evidence

1. Validate the complete Unity CineTwin grid against the exact source CSIR.
   Resolve the source character, renderer FBX, clip GUID/local-file ID and
   original actor binding. Rehash bounded files inside the selected Assets
   scope, including importer metadata. The Unity extractor now exports model
   and model-importer hashes alongside its existing clip hashes.
2. For each source sample compute actor and root world excursions. Compute
   `inverse(actor rotation) * (root position - actor position)` and
   `inverse(actor rotation) * root rotation`. Both actor-relative quantities
   must remain within 0.1 cm / 0.1 degrees; both world scales must be unit.
   The tolerance classifies stationarity; it never supplies a correction.
3. Build exact keys from authenticated source display-frame timestamps,
   including the measured playback-end boundary. Reuse the existing canonical
   position/quaternion conversion, convert meters to centimeters and unwrap
   successive Euler representations. No constant offset, fit to a target,
   benchmark-specific identity or guessed trajectory is introduced.
4. Read the existing local approved profile catalog and probe the actual saved
   source/target mesh, skeleton, IK Rig and Retargeter packages. Check class,
   saved hashes, dirty state, source import identity, rig hierarchy, API
   capabilities and destination availability. Host verification also rehashes
   the exact probed package files, so cached probe evidence cannot conceal a
   changed saved package. Unsaved editor state is freshly rechecked inside
   native preflight on the editor thread.
5. Offer only eligible opaque choices to OpenAI's existing strict Responses
   schema. The model receives bounded motion summaries and action IDs, never
   private project paths, source names, asset code or numeric trajectory keys.
   It cannot bypass a refusal by selecting the legacy native default for a
   measured moving character. Version 1 can select one moving character;
   multiple independent moving owners require a future registered strategy.
6. Copy the mapping into a fresh candidate. Bind source evidence, approved
   retargeting profile, native worker and actor to that candidate's new
   sequence. Recompute the immutable native plan with one actor transform
   owner. Reject any legacy root-motion correction; keep the native skeletal
   clip for the joint poses. Frame rates come from evidence and must agree
   with the native plan. Integer and fractional rates are covered by tests.
7. Before any engine mutation repeat source/target/profile/package checks,
   verify the job/sequence/manifest and reject occupied asset namespaces,
   scratch/final clips or actor labels. Create the exclusive durable attempt
   receipt, then use the existing fresh-import and native IK adapter. Its
   existing fresh source reference-pose comparison remains mandatory.
8. Revalidate the source manifest after staging. Read the raw native root at
   clip-frame timestamps, clip boundaries and the actual trimmed/speed-scaled
   Timeline sample times. Refuse root movement or native parent/physics/scale
   ownership before allocating a Level Sequence. This validation requires
   newly imported native data: a refusal here preserves the partial staging
   rather than claiming that no import occurred.
9. Write translation and rotation using native linear transform channels and
   explicit unit scale defaults. Channels are resolved by native type and
   semantic name; Unreal's optional float manual-weight channel must remain
   constant at one, and constraint/override channels refuse. The section is
   active and uses an absolute blend. The transform section includes the measured
   end boundary, while sequence playback remains `[0, duration)`. A skeletal
   post-roll covers that boundary; its source display-frame duration is
   converted to native ticks using actual tick resolution. Read back these
   saved structures and stop on mismatch.
10. Keep CineTwin tick-synchronized observation, matched-time actor/root/joint
    comparison and distinct-editor persistence as separate acceptance gates.
    The canonical release gate requires the selected action's motion proof;
    a skeleton-only receipt cannot pass moving-character conversion.

## Supported and refused scenarios

| Source/destination scenario | Classification | Product behavior |
| --- | --- | --- |
| In-place, non-humanoid default single FBX take with approved target IK profile | COMPLETE | Existing `use_approved_ik_retarget_profile` behavior retained and regression tested. |
| Moving or turning unparented actor; static actor-relative root; one clip covering playback; approved target profile | COMPLETE | New actor-world trajectory action, source-based IK staging and native readback. Actual fidelity still requires engine acceptance. |
| Same native skeleton in an approved source/target profile with actor-owned motion | COMPLETE | Motion action remains eligible; it retains the existing approved native retarget path rather than guessing asset reuse. |
| Trimmed or speed-scaled eligible single take | COMPLETE | Preserve source offset/speed and verify native duration and tick-based trim. |
| 24, 30, 60 fps or 30000/1001 with integral playback frame count | COMPLETE | Exact source frame keys; fractional-rate and tick-conversion tests. Other positive rates up to 240 follow the same bounded contract. |
| Skeletal-root-only locomotion or independent actor/root motion | NOT_IMPLEMENTED | Classified and refused before mutation; no root stripping or guessed offset. |
| Parented/local-space character, non-unit actor/root scale or target physics ownership | NOT_IMPLEMENTED | Explicit refusal; no hierarchy or simulation approximation. |
| Humanoid/Mecanim avatar, `.anim`, unsupported model format, split/custom/multiple FBX takes, looping clip | NOT_IMPLEMENTED | No eligible moving action; report records exact format/clip refusal. |
| Multiple/layered/crossfaded moving clips or multiple AI-selected moving characters | NOT_IMPLEMENTED | Requires one unblended clip and one selected motion owner; fail closed. |
| Nonzero playback start, nonintegral duration/frame grid, mismatched source/display rate, over-budget evidence | NOT_IMPLEMENTED | Precise frame-grid/scope refusal, without rounding measured time into a guessed frame. |
| Automatic rig/IK-chain generation, bind-basis inference or arbitrary asset reuse | NOT_IMPLEMENTED | Require a saved locally approved profile and exact source asset identity. |
| Full pose orientation, facial/morph animation, rendering, shader, physics or audio parity | NOT_IMPLEMENTED | Outside this registered adapter; independent release domains stay incomplete. |

Bounds: at most 4,000 captured timestamps; fewer than 4,000 playback frames;
native clip-frame budget below 3,999, plus matched Timeline times; bounded
32-character inventory and 12 opaque selectable rows. Inventory truncation
refuses the AI motion workflow. No complete cross-engine behavior claim follows
from fitting within these bounds.

## Native receipts and recovery

| Artifact | Meaning |
| --- | --- |
| `character-compatibility.json` | Exact source, target, approved profile and motion evidence. |
| `ai-conversion-decision.json` | Existing AI provider provenance and registered animation choice. |
| Candidate mapping / `transfer-plan.json` | Exact trajectory and source/target/worker/candidate binding. |
| `automatic-setup.json` / existing automatic setup receipt | Original staged import identities, native operations and partial import state. |
| `character-native-attempt.json` | Exclusive, flushed one-shot claim before the first engine write; `STARTED_NO_REPLAY`, `FAILED_NO_REPLAY` or readback outcome. |
| `character-staged-motion.json` | Raw native root inspection or its exact failure, preserved before sequence generation. |
| `character-native-execution.json` | Native skeleton, clip sections and actor-track/key readback. PASS is structural API evidence only. |
| Separate native acceptance folder | Fresh-process persistence, reopened character readback, target observations and independent comparison; intentionally not produced by this delivery. |

There is no destructive package rollback. A preflight refusal has no native
side effects. After staging begins, the existing setup receipt and the new
attempt journal retain partial changes. The builder preserves its unsaved
partial sequence and attempts to restore actor poses/attachments on failure.
No code deletes imported packages while Sequencer can reference them. A failed
or interrupted candidate is never automatically replayed; a recovered RUNNING
job remains inspection-required. Inspect the saved receipts and backed-up
staging project, restart the editor when appropriate, then create a **new**
candidate/namespace/sequence. Never clear the attempt file to retry in place.

## Changed paths and primary-developer coordination

- `packages/studio/character_motion.py`: source trajectory, actor-relative
  root math, candidate binding and motion receipt contract.
- `character_compatibility.py` / `animation_conversion_policy.py`: exact source
  model/export evidence, native package revalidation, typed action eligibility,
  refusal and immutable plan checks.
- `packages/contracts/studio/ai-animation-conversion-decision-v1.schema.json`:
  mutually exclusive in-place and moving action/capability/ownership tuples.
- `packages/studio/transfer_backend.py`: small final plan hook using existing
  native transform and animation actions.
- `integrations/unreal/studio_character_motion.py`: staged raw-root guard and
  independent native channel/owning-track readback.
- `studio_character_probe.py`, `studio_character_execution.py`,
  `studio_planner_sync.py`: capabilities, fresh evidence, attempts and receipts.
- `build_level_sequence.py`: native preflight, measured boundary-inclusive
  transform section, unit scale and correct native post-roll tick conversion.
- `studio_local_editor_worker.py`: small begin/staged-check/failure-record hooks
  in its existing execution flow; no competing worker/state machine.
- Unity `CsirModels.cs` / `ExtractorUtilities.cs`: export model and importer
  hashes; no Unity project asset writes.
- `tools/studio_transfer_ai.py`: registered-choice instructions, strict native
  worker identity, moving-default refusal and evidence revalidation.
- `tools/studio_ai_transfer_audit.py` and the existing
  `packages/studio/studio_release_gate.py`: recognize the additional action
  and require its motion proof; retain all behavioral and release gates.
- New moving-character tests, one corrected legacy rotation-ownership
  regression expectation, this report and the synthetic example. One import
  in `tests/studio/test_reopened_camera_gate.py` repairs an incoming RC
  collection/lint error; the primary developer was notified on PR #128.

Shared-file coordination was posted on
[PR #128](https://github.com/Nithin0553/CutsceneAI/pull/128#issuecomment-6992775441)
before changing the canonical release gate. Its changes are confined to
animation action recognition, required motion proof and reopened action
identity. `studio_autopilot.py`, `studio_local_bridge.py`, the UI and CI workflow
remain untouched. The existing feature-target PR CI trigger covers this draft.

## Verification and later workstation handoff

Run the following from the checkout with Python 3.11 and Node:

```bash
python -m pytest -q
python -m pytest -q tests/studio/test_moving_character_conversion.py tests/studio/test_character_animation_policy.py
python -m compileall -q packages tools integrations/unreal
python -m ruff check tests
node --check apps/studio-web/app.js
node --check apps/studio-web/cinematic.js
node tests/studio/test_cinematic_ui.cjs
python tools/repo_check.py
git diff --check
```

The [anonymized synthetic example](examples/friday-moving-character.synthetic.json)
contains compatibility, a typed decision and mocked native readback. Its
origin and lack of real provider/engine invocation are explicit.

Final combined local checks: **1,072 passed, 7 skipped**, including **79 F-003 tests**
and the existing **31 in-place policy regressions**. Python syntax, Ruff,
JavaScript syntax, 14 cinematic UI scenarios, repository hygiene and whitespace
checks passed. Both changed Unity C# files passed tree-sitter syntax parsing;
this is not Unity compilation. The seven existing skips are retained and are
not counted as engine acceptance. The F-003 implementation alone passed
1,039 tests before incorporating the primary developer's optics, camera-cut
and reopened-camera gate tests.

API details were checked against Epic's documentation for
[native root-track inspection](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/AnimationLibrary),
[typed scripting channels](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/MovieSceneSectionExtensions),
[double-key interpolation readback](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/MovieSceneScriptingDoubleKey)
and [MovieScene tick-resolution storage](https://dev.epicgames.com/documentation/en-us/unreal-engine/sequencer-time-refactor-technical-notes).
Runtime capability checks still decide eligibility; documentation is not native
acceptance evidence.

After the primary developer reviews/integrates this draft into the RC and
records software freeze, the next executable acceptance step is to pull the
reviewed commit into **backed-up** Unity/Unreal test checkouts, install the updated
extractor, compile it and export fresh model/clip/importer evidence. Do not use
old moving-character exports missing the model hashes. Use a saved approved
IK profile as documented in the preceding assignment delivery, start the
updated worker in Unreal 5.8 and run a new one-click candidate. Preserve all
artifacts above. A real source-owned moving/turning actor must pass native
root/track readback; separately reopen the staging map in another editor
process and run `studio_native_acceptance.start()` for the exact job. Retain
all source/target frames and any mismatches. Then run Benchmark002 and held-out
rigs as measured regression/refusal cases. **Do not execute those steps before
the user's freeze gate.**

Remaining work in F-003 is primary-developer review and these deliberately
gated engine/provider acceptance runs. The unsupported categories above are
product refusals, not hidden promised functionality. The broader #127 release
work remains owned by its respective developers; this delivery declares
neither a global software freeze nor cinematic fidelity.

## Review record

- [Draft PR #130](https://github.com/Nithin0553/CutsceneAI/pull/130), targeting
  `feature/studio-e2e-release-candidate-v0.1`; retained as draft for primary review.
- F-003 implementation commit:
  [`5d07b4a6b29db442e03f6721e037ac562a0926b7`](https://github.com/Nithin0553/CutsceneAI/commit/5d07b4a6b29db442e03f6721e037ac562a0926b7).
- Latest synchronized RC: `56d46616d83c9ffdbe053dffd716a1f15c775ee5`.
- Earlier reviewed combined implementation:
  [`1898fda2be2a4cd2622a1c5b86586c7256fc624c`](https://github.com/Nithin0553/CutsceneAI/commit/1898fda2be2a4cd2622a1c5b86586c7256fc624c).
- [Combined implementation CI 44413605334 — SUCCESS](https://github.com/Nithin0553/CutsceneAI/actions/runs/44413605334)
  used PR head `1898fda2` merged with the then-current RC `6f9501f3`.
  Both the Python/source/UI/Ruff/hygiene job and Windows dependency-bootstrap
  job passed; **1,067 passed, 7 skipped**. GitHub PR CI tests the merge ref,
  which can include newer primary-developer changes than the branch baseline.
- [CI 44413087577 — SUCCESS](https://github.com/Nithin0553/CutsceneAI/actions/runs/44413087577)
  checked implementation head `5d07b4a6` against RC `44e7c1ce`: **1,054 passed,
  7 skipped**, Python/JS syntax, 14 UI scenarios, Ruff, repository checks and
  Windows dependency bootstrap all green. This is code-only evidence.
- CI `44414034220` subsequently caught the older reopen fixture expecting PASS
  without sampled camera evidence as stricter primary gates landed. The final
  synchronization includes primary fix `ad4d272` and the missing test import;
  the combined local suite passes with the stronger gate retained. Final-head
  CI is verified again before handoff.
- [Final-head CI and exact current review SHA](https://github.com/Nithin0553/CutsceneAI/pull/130/checks)
  remain attached to the draft. The final handoff records the exact published
  head and confirms its CI completed. Documentation updates do not manufacture
  engine evidence.
- Issues #129 and #127 remain open. Primary review and the subsequent authorized
  live-engine/provider matrix are the next steps; no merge was performed.
