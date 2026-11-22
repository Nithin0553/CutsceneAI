# Element 3.5 — CineTwin per-element attribution and bounded recovery review

**Stack:** This phase is on feature/element3-cinetwin-element-recovery-v0.1, based on draft PR #139 (Element 3.4), which depends on PRs #138, #137 and #136.

**This is a software readback analysis milestone.** No Unity/Unreal editor or native engine acceptance was performed solely by the unit tests. No native editor modification, automatic repair, automatic loop retry, persistent asset save or whole-cutscene fidelity approval is granted by these reports.

## Source evidence and scope

New module: packages/studio/studio_element_cinetwin.py.

The analyzer accepts:
1. The exact source CSIR and source-bound Element 3.1 per-occurrence plan.
2. A CineTwin sampling plan rebuilt and compared to the exact CSIR.
3. Raw Unity source behavior capture.
4. Independently captured Unreal target behavior observations.

It runs the existing packages/cinetwin/behavior_compare.py comparator itself, rather than trusting an AI-provided comparison report. The comparator verifies source/capture identity, complete native target time grid, entity coverage and consistent observed actor bindings, measured world position/orientation, joint/bone motion, native CineCamera optics, and available Sequencer camera-cut section timing.

The new source-bound attribution report accounts for every asset, entity, track, section, curve and relationship. Anonymous occurrence IDs are linked using the exact original source path and entity bindings. Directly measured entity discrepancies distinguish mapped pose differences, target-unmapped entities, incomplete domain capture and no currently flagged measured difference. Tracks/sections/curves can be **associated with** a measured entity, but **are not falsely declared to be the causal origin** of an actor or rig difference. Camera-cut mismatch is global timing context, not proof of a specific cut-section implementation fault.

Reported data are bounded domain flags, scalar error metrics, anonymous IDs, evidence identity SHA-256s and read-only conclusions. Raw private source IDs, object/asset names, target actor labels and private folder paths are not exported in the attribution.

The comparison explicitly retains unverified domains such as audio, events, rendered image, physical scene, full skeletal skin and projection parity. A clean measured actor transform is not a converted cutscene, and calibrated rig/mesh-forward approval is not inferred from a first-frame rotation.

## Registered recovery policy

Phase 3.5 does not invent or dispatch engine repair actions. For an actor whose independently observed character trajectory is consistent with a constant initial placement offset, it may show the diagnostic next step:

INSPECT_EXISTING_USER_AUTHORIZED_CHARACTER_OFFSET_POLICY

This points to packages/studio/agent_transform_evidence.py and the existing integrations/unreal/studio_transform_repair.py. That existing narrowly scoped repair independently remeasures actor and skeletal root motion, demands explicit user feedback, one newly created unparented staged actor, exact project/sequence/native track binding, no attached children and post-repair 2 cm actor/root readback before saving, with rollback on failed post-check. **This Phase 3.5 advisory hint does not satisfy or bypass any of those conditions.** Every other issue remains DIAGNOSTIC_REVIEW_ONLY.

## Bounded independent remeasurement

The read-only remeasure routine receives a baseline and up to **two** subsequent target behavior captures, always against the **same** source CSIR, Element plan, source capture and CineTwin sampling plan. It independently calls the full comparator for *every* capture. Repeated identical captures are refused; a different claimed native target project/sequence is refused when project/sequence provenance is present. Missing target project/sequence identity is preserved as explicitly unverified.

The resulting record compares direct entity discrepancy flags and actor-position metrics and distinguishes:
- No original measured difference or a newly introduced regression.
- Repeated failed/no-progress remeasurement: stop recommending further attempts.
- Partially reduced but unresolved measured discrepancies.
- No remaining currently flagged **measured** discrepancy: requires separately established target identity/native persistence and still never establishes full-cutscene fidelity.
- Non-entity occurrences: not directly attestable, even if their bound entity improved.

All paths set native_repair_authorized=false, further_automatic_repair_or_retry_authorized=false, and full_cutscene_fidelity_verified=false. The output includes complete per-occurrence source-bound records and independent remeasurement input digests. Validation reconstructs reports from original input files rather than trusting recomputed checksums.

These reviews are not a native repair runner. The maximum is two remeasurement cycles, not two automatic Unity/Unreal writes; engine mutations remain exclusively under existing native policy and authorization.

## CLI and validation

The existing tools/cinetwin.py exposes two read-only commands. Run after independently collecting exact-source and current-target captures.

\`\`\`bash
python tools/cinetwin.py element-verify \\
  source.csir.json element-plan.json cinetwin-plan.json \\
  unity.capture.json unreal.target.json element-report.json

python tools/cinetwin.py element-remeasure \\
  source.csir.json element-plan.json cinetwin-plan.json unity.capture.json \\
  unreal.before.json unreal.after.json --output element-remeasurement.json
\`\`\`

Both refuse to overwrite an input file. Outputs are created as **new** files; they are not editor modifications. The required element-plan.json is the exact Element 3.1 source-bound plan, and the raw source/target captures must be from the existing CineTwin capture/observation pipeline, not an asserted LLM response.

Tests cover direct actor vs indirect Timeline attribution, source and native observation identity, private source identifier redaction, missing/partial actor/rig/camera measurements, initial-offset discrepancy hints, source/capture tampering, duplicate capture replay, two-attempt bounds, no-progress stop, measured improvement without whole-cutscene fidelity, and target project/sequence change refusal.

## Still required for engine-grade acceptance

A successful software test does **not** establish:
- Real Unity/Unreal capture exporter and plugin compatibility on user projects.
- Native readback after fresh Unreal editor process/reopen to independently verify saved assets.
- Target actor/rig retargeting, blended tracks, camera cut rendered output, motion ownership or full frame/audio/events equivalence.
- Persistently authorized native correction via user feedback and the existing repair action.
- An autonomous multi-domain engine recovery loop.

These remain separate, necessary engine-side acceptance requirements before declaring a full cinematic transferred or recovered.
