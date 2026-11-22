# Element 3 consolidated integration — registered Unreal execution and real-engine acceptance

**Branch:** integration/element3-native-acceptance-v0.1, based on the fully stacked Studio Element 3.1–3.5 and review integration branch, PRs #136–#141.

**Base release candidate:** feature/studio-e2e-release-candidate-v0.1. The git compare found the latest Element 3 branch 70 commits ahead and 0 behind the existing release candidate. The merge-base is the release candidate head; there is no divergent-history integration conflict. This is a consolidated integration PR, not a merge into main or the existing release candidate.

## Scope and evidence

The Studio's existing immutable source-CSIR transfer plan, code-registered Unreal action handlers, native preflight and editor worker already support real native Level Sequence generation. This change **does not** give the model a generic Unreal Python execution tool, invent new native handlers or allow the agent to create a different or partially filtered transfer plan.

The new strict Element 3 *operator authorization gate* connects that existing native builder to the source-bound Element 3 review:
1. The Review page builds and shows the per-occurrence CED/schedule/investigation inventory from the same exact prepared candidate.
2. A user explicitly acknowledges unresolved source gaps. This acknowledgement is read-only and carries no native authority.
3. Independently, the user approves the complete *exact* prepared registered native action set. Approval is bound to the immutable candidate, source CED review, transfer plan byte SHA-256 and live observed Unreal capability probe.
4. For every prepared action, the inventory contains its immutable index, action SHA-256, registered kind and exact occurrence IDs **only when an explicit source_location/covered_source_locations was included by the installed source adapter**. Native actions without such provenance remain clearly classified LEGACY_ACTION_SOURCE_ATTRIBUTION_UNVERIFIED, with a separate operator consent requirement. Guessing that an entity/track name or frame timing proves a particular source occurrence is intentionally forbidden.
5. At job submission, the localhost backend revalidates the immutable source, target, current worker and both consents. An Element 3 review can no longer be bypassed by invoking /api/execute directly. Existing jobs without an opted-in Element 3 review remain compatible.
6. At Unreal job start, **before level creation, asset import, actor mutation or Sequencer construction**, the worker independently verifies the same source-bound native authorization. The original native builder then independently recomputes all native actions from the source CSIR and mapping and uses its existing registered action preflight/handlers.
7. After the native builder completes and writes its real runtime receipt, the worker emits a content-addressed per-action dispatch ledger. It records that the registered builder completed the approved plan; it **does not** falsely assert that every individual action had independent native readback or accurate cinematic playback. Existing native rig, collider, hierarchy and post-generation audits remain in force.

Partial action selection is not supported without preparing a separate source-authenticated candidate: it would otherwise bypass the immutable native transfer plan, timeline ownership guards and original source/target readback authority.

## Engine-side acceptance (requires the actual Editor)

The existing integrations/unreal/studio_native_acceptance.py is the real editor acceptance runner. From the **saved, separately reopened** generated map (different Unreal Editor process from generation), it runs:
- Post-reopen native persistence and project/level/sequence identity verification.
- CineTwin tick-synchronized readback of actor and skeletal positions/orientations, target camera optics and camera cut section timing on the exact Unity sampling grid.
- Optional approved rig rest-pose and mesh-forward calibration evidence.
- When an Element 3 review exists, a source-bound native action authorization and occurrence count are attached to comparison.json. The Studio host independently recomputes exact-source per-occurrence CineTwin attribution from the same reopened target-behavior.json, the raw Unity capture and the original candidate record when evaluating release readiness. This keeps the embedded Unreal Python runner free of the Studio host's optional JSON-schema/model dependencies.

The release audit independently reconstructs the native action grant and dispatch ledger and recomputes the exact-source per-element CineTwin attribution from raw original capture and reopened native observations before reporting measured-domain acceptance. The native worker's consent gate is intentionally **standard-library-only**, so the engine process does not require LangGraph or JSON Schema dependencies just to authorize an already prepared native job. Fake model scores, forged checksums, a missing runtime receipt, same-process reopen, mismatched source/target files or a stale prepared candidate cannot become native acceptance.

**Real Unity/Unreal acceptance was NOT performed by GitHub CI**, since CI does not host these engines or the user's backed-up projects. Its native worker tests are static/synthetic, not real editor acceptance.

## How to run real acceptance

1. On a backed-up Unity/Unreal test pair, connect both editors through the Studio companion, prepare the source CSIR/capture, mapping and target candidate.
2. Review source issues and authorize exact native actions; if the prepared plan contains legacy actions without per-occurrence provenance, explicitly accept that limitation or prepare a better source-backed adapter.
3. Confirm destination readiness and choose Generate. The worker executes the original native builder and records the runtime and per-action receipts; failures are never automatically replayed.
4. Save All, close the generation Editor process once, and reopen the generated level in another Unreal Editor process. This is necessary for a genuine persistence/reopen check, not a repeated restart loop.
5. In the reopened editor Python Console, call:
   \`\`\`python
   import sys
   sys.path.insert(0, r"<CutsceneAI repo>/integrations/unreal")
   import studio_native_acceptance
   studio_native_acceptance.start()
   \`\`\`
   This uses the active job and exact source/target captures, and schedules tick-synchronized observations. It writes an independent acceptance folder under the saved candidate; the completion callback writes comparison.json.
6. Refresh the Studio release-readiness report and inspect Element 3 native consent, builder dispatch, reopened Element 3 attribution, and the individual camera/hierarchy/actor/skinning coverage results.

## Full fidelity is still an independent release gate

CineTwin currently measures subsets of actor motion, skeletal joint motion, sampled camera optics and authored cut sections. A measured-domain pass is **not** proof of full cutscene equivalence. The release gate still explicitly marks rendered-frame comparison, full skeletal skin/pose, audio/signal side effects, generalized policy performance and held-out projects incomplete until independently verified real native evidence and associated validators exist.

Open implementation gaps before production release include real video/render sampling and perceptual image comparison, source and target audio/event capture and timing, unsupported custom shader/physics behaviors, fully calibrated skeletal retargeting on held-out projects, and real-editor acceptance results. Do not turn these red gates green with test fixtures, AI scores or a mere saved sequence.

## CI / tests

Unit and integration regressions cover registered action whitelisting, exact source-provenance linkage, invalid/unknown handlers, missing or duplicate action IDs, explicit legacy-consent requirements, stale or altered grants, current native capability checks, worker check ordering before any mutation, no native replay, runtime receipt integrity and post-reopen source-bound attribution wiring. As with earlier phases, GitHub tests validate software contracts, never actual Unity/Unreal render/audio parity.
