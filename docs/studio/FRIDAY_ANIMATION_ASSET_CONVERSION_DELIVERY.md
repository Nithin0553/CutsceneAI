# Assignment 002 delivery

This review implements an evidence-bound AI choice of an already approved
Unreal IK Retargeter for one in-place character per transfer. The assignment
is tracked by [issue #125](https://github.com/Nithin0553/CutsceneAI/issues/125).
The feature branch is `agent/friday-animation-rootmotion-assets-v0.1` and the
PR targets `integration/agent-native-adapters-v0.1`.

The implementation was tested after incorporating integration commit
`a8f40ed56a7a817f7d5154d8af49817a5fda7765` into the dedicated branch. The
primary developer's new AI execution audit and UI are preserved. Review and
subsequent integration belong to the primary developer.

The implementation commit is
[`23ea88a1f187e8d924b8a43a92a31443d58302f6`](https://github.com/Nithin0553/CutsceneAI/commit/23ea88a1f187e8d924b8a43a92a31443d58302f6).
The review is [draft PR #126](https://github.com/Nithin0553/CutsceneAI/pull/126).

## Changed files

| File | Purpose |
| --- | --- |
| `packages/studio/character_compatibility.py` | Exact local asset resolution, capture verification and motion ownership |
| `packages/studio/animation_conversion_policy.py` | Versioned typed choice, redaction, mapping and plan checks |
| `packages/contracts/studio/ai-animation-conversion-decision-v1.schema.json` | Inspectable action schema |
| `tools/studio_transfer_ai.py` | Native probe handshake, redacted model choice and evidence revalidation |
| `tools/studio_autopilot.py` | Wait for native evidence, record selection and prepare the chosen strategy |
| `tools/studio_candidate.py` | Apply the approved profile to the fresh mapping copy |
| `tools/studio_local_bridge.py` | Bind the report and decision when preparing and queuing a candidate |
| `packages/studio/transfer_backend.py` | Carry the decision in the recomputed immutable plan |
| `integrations/unreal/studio_character_probe.py` | Read-only named native rig, package and clip inspection |
| `integrations/unreal/studio_character_execution.py` | Native preflight and actual skeleton/section readback |
| `integrations/unreal/studio_local_editor_worker.py` | Editor-thread probe and execution hooks |
| `integrations/unreal/studio_planner_sync.py` | Refresh canonical character modules inside the long-lived editor |
| `integrations/unreal/studio_ik_retarget.py` | Retain native source and target rig identities for the probe |
| `integrations/unity/com.cutsceneai.extractor/Editor/CsirModels.cs` | Clip identity and timing metadata |
| `integrations/unity/com.cutsceneai.extractor/Editor/ExtractorUtilities.cs` | Bounded file hashing |
| `integrations/unity/com.cutsceneai.extractor/Editor/UnityTimelineExtractor.cs` | Capture hashes, source timing and default-take eligibility |
| `packages/cinetwin/behavior_compare.py` | Distinct measured skeletal-root metrics |
| `integrations/unreal/cinetwin_tick_evaluator.py` | Bind target playback to the exact Unreal project |
| `integrations/unreal/studio_native_acceptance.py` | Reopened readback and optional paired before/after evidence |
| `tests/studio/test_character_animation_policy.py` | Positive, stale, ambiguous, unsupported and orchestration regressions |
| `tests/cinetwin/test_behavior_compare.py` | Root correspondence and measurement regressions |
| `docs/studio/examples/friday-animation-conversion.synthetic.json` | Redacted synthetic contract examples |
| `docs/studio/FRIDAY_ANIMATION_ASSET_CONVERSION_DELIVERY.md` | Delivery state, acceptance protocol and developer handoff |
| `.github/workflows/ci.yml` | Run the existing CI checks on the assigned branch and PRs into the integration branch |

## Delivery state

| Area | IMPLEMENTED | TESTED_IN_MOCKS | TESTED_IN_REAL_UNREAL |
| --- | --- | --- | --- |
| Exact Unity model and clip identity, GUIDs, FBX/meta hashes, single-take and timing eligibility | Yes | Yes | NOT_TESTED |
| Native Unreal approved mesh, skeleton, rig, Retargeter and package probe | Yes | Yes | NOT_TESTED |
| Separate source actor and skeletal-root translation and rotation ownership analysis | Yes | Yes | NOT_TESTED |
| Typed model choice that adds an approved retarget profile to the immutable native plan | Yes | Yes, through a mocked OpenAI Responses transport | NOT_TESTED |
| One-click native probe, model analysis, preparation and queued-job provenance | Yes | Yes | NOT_TESTED |
| Revalidation inside Unreal before map creation, imports and actors | Yes | Yes | NOT_TESTED |
| Exact output skeleton, clip duration, section range, speed and trim readback | Yes | Yes | NOT_TESTED |
| Independent post-reopen actor, root and joint comparison with optional baseline | Yes | Core comparison and wiring tested | NOT_TESTED |

Unity compilation is NOT_TESTED. Three changed Unity C# files passed
tree-sitter syntax parsing. This environment has neither Unity nor Unreal
Editor or the workstation projects. `OPENAI_API_KEY` is unset in the Studio
process here, so a genuine external model-invoked decision is NOT_TESTED.
The transport tests exercise the production OpenAI request and validation
functions with a test response. The remaining live-model acceptance gate in
issue #125 is open.

## Algorithm and supported scope

1. Resolve source characters and used Timeline sections by exact IDs. Require
   one source renderer FBX and verify its Unity path and `.meta` GUID within
   the selected source scope. Read bounded files and hash their contents.
2. Validate the Unity Play Mode capture against the original CSIR and complete
   sampling grid. Measure actor/root translation and rotation separately.
   Report root motion, actor motion, compound motion and missing evidence.
3. Read approved profiles from `Config/CutSceneAI/AnimationProfiles.json` in
   the selected Unreal project. Match its Unity project fingerprint, character
   ID and source FBX SHA-256. This local file provides the reviewed target
   references available to the new AI planning action.
4. Ask the existing editor-thread worker to inspect those exact native assets.
   Check class, source and target IK Rigs, preview meshes, skeletons, saved
   package hashes, dirty state, source import path and bone hierarchy. Record
   local reference-pose hashes and the current project, map, version and PID.
5. Offer the model only a bounded redacted summary and opaque choice IDs. The
   registered action `use_approved_ik_retarget_profile` is available for a
   different target skeleton with eligible in-place motion. The model chooses
   the action or retains the existing native policy. Paths and code come from
   local validated evidence.
6. Recompute eligibility before preparation and submission. Apply the selected
   profile to a new mapping copy, preserve the original mapping, bind the
   decision to the report and immutable transfer plan, and verify the resulting
   source asset manifest.
7. Before Unreal creates anything, recompute source hashes, probe the current
   native assets again, verify the choice and reject occupied package paths,
   namespaces, actors and competing motion owners. Use the installed native
   import and IK Retargeter adapter.
8. Inspect the generated actor mesh and animation skeletons. Read the owning
   Sequencer binding and actual clip ranges, duration, speed and source trim.
   Stop and preserve the partial candidate if that readback fails.
9. After reopening, run the existing tick-synchronized acceptance command.
   Record actor position/facing error, paired joint positions, skeletal-root
   position and per-engine root rotation excursions. A separately captured
   baseline can provide source-bound before/after metrics.

The action currently requires a complete capture of at most 4,000 timestamps,
one uniquely identified root, unit actor scale, no source parent, and actor
and root excursions within 0.1 cm and 0.1 degrees. It handles non-humanoid,
nonlooping, default single-take FBX clips whose used ranges fit their captured
duration. It preserves existing clip speed, trim and section-range planning.
The source clip must be the take named by the Unity importer. A source with
several FBX takes or custom Unity clip splitting receives a precise refusal.

The source capture has no bind/reference-pose snapshot. That fact remains in
the report. The existing native adapter additionally compares the freshly
imported source reference hierarchy and poses with the approved preview
before retargeting. A mismatch at that stage leaves a partial import receipt
for inspection. Compatibility here describes eligibility for the approved
adapter. Playback and image fidelity still need measured acceptance.

## NOT_IMPLEMENTED

- Automatic creation or inference of IK chains, rigs, Retargeter assets or
  source-to-target bind orientation calibrations.
- A new AI-executable moving-character root correction, mixed actor/root
  motion composition, parent-local root correction, or source-world motion
  bake action. The existing guarded post-transfer translation repair and
  experimental root lock keep their own eligibility rules.
- Automatic reuse of existing skeleton/clip assets or name-only matching.
  A shared skeleton has a distinct `COMPATIBLE` report outcome and retains
  the existing native policy.
- Humanoid body retargeting, custom/split takes, arbitrary animation layers,
  constraints, morphs, facial curves, or multiple AI-selected characters in
  one transfer.
- Absolute cross-rig root/joint orientation parity, rendered appearance,
  material equivalence, audio, simulation or universal transfer certification.

The historical Benchmark002 actor/root errors around 295.5 cm and 379.7 cm
remain diagnostic observations. A synthetic regression uses those distinct
displacements to demonstrate the compound-motion refusal. It provides no
new Benchmark002 correction or engine measurement.

## Automated checks

Run these from this checkout with Python 3.11 and Node.

```bash
python -m pytest -q
python -m pytest -q tests/studio/test_character_animation_policy.py
python -m compileall -q packages tools integrations/unreal
python -m ruff check tests
node --check apps/studio-web/app.js
node --check apps/studio-web/cinematic.js
node tests/studio/test_cinematic_ui.cjs
python tools/repo_check.py
git diff --check
```

The complete suite passed with **937 passed, 7 skipped** on the combined
feature and integration code. The dedicated assignment module passed
**31 tests**. Ruff, Python syntax, Studio JavaScript checks, 13 cinematic UI
scenarios and repository hygiene checks passed. Tests include a mocked
model-selected action changing the prepared retargeting manifest, candidate
submission, native preflight, mismatched GUIDs, changed FBX/meta/package hashes,
unknown/missing rigs, unsupported APIs, ambiguous profiles, source scope and
symlinks, missing samples, parented or competing motion, and output timing
mismatches. The seven skips remain part of the existing repository suite.

The previous CI branch filters excluded both the assigned `agent/` branch and
the integration PR target. This PR adds those two event filters so the
repository's existing checks run for this review.

GitHub CI passed on review commit
`b553daa17e4554ce0aceaebffd4667f1e80d6253`, including the test suite, Python
syntax, Studio JavaScript, Ruff and repository hygiene.
[Completed CI run](https://github.com/Nithin0553/CutsceneAI/actions/runs/44366783166)

## Workstation acceptance

1. Pull the dedicated branch into the acceptance checkout and install its
   Unity extractor. Record Unity compilation and editor versions. Use backed-up
   Unity and Unreal projects with a fresh target map and sequence.
2. Author and save a source/target IK Rig and Retargeter using the existing
   Unreal guide. Set both preview meshes. Preserve their source FBX identity.
   Create the following local catalog using the source fingerprint and entity
   ID from the new CSIR and the exact source FBX SHA-256.

```json
{
  "kind": "cutsceneai.studio.approved_animation_profiles",
  "schema_version": "1",
  "profiles": [{
    "unity_project_fingerprint": "<exact-source-project-fingerprint>",
    "source_entity_id": "<exact-source-character-id>",
    "source_fbx_sha256": "<64-lowercase-hex-digits>",
    "source_mesh_path": "/Game/Approved/UnitySource",
    "target_mesh_path": "/Game/Approved/Target",
    "retargeter_path": "/Game/Approved/Retarget"
  }]
}
```

3. Restart Unreal after pulling, start its Studio worker and launch Studio
   using its already configured model environment. Connect the project copies
   and start a new one-click transfer. Enter Unity Play Mode when requested.
   During `ANALYZING_PROJECTS`, the worker inspects approved assets. Check that
   the decision names an eligible opaque character ID and records a genuine
   provider response ID, then confirm the generated mapping and plan carry
   the selected `ai_character_animation` decision.
4. Preserve `character-compatibility.json`, `ai-conversion-decision.json`,
   `automatic-setup.json`, `transfer-plan.json`, the setup and builder receipts,
   and `character-native-execution.json` from that candidate. Check that the
   source clips, target skeleton and exact section ranges agree.
5. Capture a separate baseline using the native CineTwin sampler before
   applying a conversion when before/after measurements are needed. Save all
   staging assets, close Unreal, open the same map in a fresh process and run
   the following commands in its Python console.

```python
import sys
sys.path.insert(0, r"D:/CutsceneAI/integrations/unreal")
import studio_native_acceptance
studio_native_acceptance.start()
# With an independently captured baseline from a distinct sequence in this project
# studio_native_acceptance.start(baseline_target=r"D:/Evidence/baseline-target-behavior.json")
```

6. Keep Unreal ticking until the full source sampling grid is captured.
   Inspect the new acceptance folder's `character-reopened.json`,
   `target-behavior.json`, `persistence.json` and `comparison.json`.
   `character_conversion.before` stays null when no compatible baseline was
   supplied. Root orientation excursions are reported per engine, and the
   absolute cross-rig root rotation error stays unavailable.
7. Repeat with a second held-out in-place rig. Test moving or parented actors,
   mismatched GUIDs, a changed native package, an unavailable IK plugin,
   missing frames and occupied target paths. These cases must refuse the new
   action before mutation. Repeat the known Benchmark002 regression as a
   measurement case and retain any refusal.

No live before/after measurements were captured in this environment. The
[anonymized JSON example](examples/friday-animation-conversion.synthetic.json)
is explicitly synthetic and contains compatibility, typed decision and
unexecuted readback examples. Its action follows the
[versioned schema](../../packages/contracts/studio/ai-animation-conversion-decision-v1.schema.json).

## Primary developer handoff

Review the feature PR against the integration branch. The implementation
includes source export metadata, standalone compatibility/policy/probe/readback
modules, targeted orchestration hooks and regression tests. Shared-file hooks
are additive and concentrated in `studio_transfer_ai`, `studio_autopilot`,
`studio_candidate`, `studio_local_bridge`, `studio_local_editor_worker`,
`studio_planner_sync` and a two-line plan annotation in `transfer_backend`.
The parent branch's read-only AI audit is preserved.

Use the feature PR for review integration after coordinating any subsequent
changes to those seams. To cherry-pick, apply only the commits introduced by
this feature, in order. The PR base already contains the earlier native and
AI-first stacks. Keep issue #125 open while the live-model and engine gates
remain pending. Record a genuine model invocation, source/target editor
versions, per-domain measurements and reopened-package results before
claiming engine acceptance.

[Unreal IK Retargeter scripting](https://dev.epicgames.com/documentation/en-us/unreal-engine/using-python-to-create-and-edit-ik-retargeter-assets-in-unreal-engine)
· [Unity default clip takes](https://docs.unity3d.com/6000.0/Documentation/ScriptReference/ModelImporter-defaultClipAnimations.html)
