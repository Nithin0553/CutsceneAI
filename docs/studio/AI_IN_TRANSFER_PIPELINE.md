# CutSceneAI AI-first Transfer Architecture — Implementation Status

**Branch:** `integration/agent-native-adapters-v0.1` (draft PR #124)  
**Goal:** AI analyzes both a Unity cutscene and an Unreal destination, chooses
registered conversion strategies, assists conversion and evaluates native
results. No model may invent engine commands or certify parity without evidence.

## 1. Newly integrated: AI before candidate preparation

One-click Studio now uses:

1. **Unity native companion** — exports source CSIR, scoped feature census and
   Play Mode CineTwin capture. Source identity and scope are checked by the
   existing `studio_ui_features.validate_options` gate.
2. **Unreal companion** — reports the real loaded project, map and a read-only
   bounded actor-class census. The Studio checks the matching target identity.
3. **AI project analysis** — `tools/studio_transfer_ai.py` reads those
   specific verified inputs and the selected `.uproject` metadata and creates
   a *redacted* count/feature/capability summary. Only this summary, not raw
   scene files, project paths, scripts, FBX content or API secrets, reaches
   the configured OpenAI model.
4. **Bounded conversion decision** — the LLM returns one strategy from the
   installed catalog: `native_source`, `source_materials`, or
   `visual_activation_partial`.
5. **Verified planning** — `native_source` uses existing source-backed
   handlers. `source_materials` requests the installed embedded-FBX material
   importer. `visual_activation_partial` is permitted *only when every
   applicable source ActivationTrack can be checked using the installed
   `visual_activation.build_action` adapter*; it emits a **visual-only,
   lossy** Unreal visibility approximation. It does **not** preserve source
   script callbacks, GameObject active state, physics or collisions.
   The source material reference count enforces an independent minimum
   material-import policy regardless of the model's preference.
6. **Immutable handoff** — the chosen strategy, bounded explanation and
   SHA-256 fingerprints of the CSIR, capture, original mapping, census and
   target `.uproject` are saved as
   `ai-conversion-decision.json` in the candidate. Source and target hashes
   are rechecked before candidate preparation. The queued Unreal job binds
   the exact decision file SHA and corresponding generated mapping options.
7. **Native Unreal gate** — before creating a map, importing a file, or
   spawning any actor, the editor worker rejects a missing, altered, or
   nonmatching AI decision/mapping. Installed deterministic adapters remain
   responsible for actual FBX, native animation, actor, Sequencer and
   material conversion. AI cannot bypass engine capability checks or
   overwrite existing target sequences.
8. **After generation** — existing CineTwin / native visual diagnostics
   compare the result. The separate post-transfer LangGraph agent can explain
   gaps and request only registered, independently verified repairs.

An AI API key is required for the **one-click AI Transfer**. If it is absent,
or the model call fails, the transfer stops **before** creating a candidate
rather than silently claiming AI reasoning occurred. The original
non-agent preparation path remains a distinct deterministic workflow.

## 2. What is not yet implemented

This phase is a real AI-directed **planning choice**, not a general-purpose
AI conversion engine. The LLM cannot yet:

- inspect every Unity GameObject, shader graph, bone, animation curve, or raw
  Unreal `.uasset` semantic directly;
- choose arbitrary target assets by visual similarity;
- synthesize native skeletal animation or retarget skeletons autonomously;
- correct changing root-motion trajectories or facing rotations on its own;
- guarantee matching lighting, cameras, rendered frames, audio, VFX or runtime
  behaviors.

Those require new **typed, tested adapters with source provenance and native
readbacks**. Exposing them as unrestricted model commands would risk project
corruption and false success claims.

## 3. Next implementation milestones

### A. Full semantic source/target analyzers
Extend the Unity capture with per-frame actor/camera/root-bone transforms,
component hierarchy, script/activation semantics, material and animation
references, lighting and event metadata. Expand the Unreal read-only analyzer
to inspect target asset capabilities, skeleton compatibility, scene hierarchy,
sequencer tracks and render/coordinate settings. Use stable identities and
redacted typed summaries; no giant raw-file prompt dumps.

### B. AI conversion planner with typed action proposals
Provide registered operation schemas such as
`match_source_guid_asset`, `choose_ik_retarget_profile`,
`bake_world_motion`, `reconstruct_camera_cut`,
`normalize_root_motion`, `stage_material`,
and `report_unrepresentable_feature`. The model proposes strategies; the
existing backend verifies identity, target compatibility and capability
before accepting any action. Each action keeps provenance and a defined
verification test.

### C. Closed-loop native acceptance
After building a unique candidate, evaluate source/target positions,
rotations, skeletal roots, cameras, timings and supported property values
at matching frames. If a registered repair is proven safe, make an isolated
change, save and remeasure; otherwise report the mismatch and require
additional work. Never auto-replay a partially failed native candidate.

### D. Project-specific learning
Store only human-reviewed successful mapping cases and verified before/after
measurements. Use those as evidence-backed examples for model evaluation or
later fine-tuning. A successful *generation* alone is not a successful
training label, and model weights are **not** updated automatically.

## 4. User validation

Do **not** run on the only copy of a Unity or Unreal project. Use the existing
backed-up staging projects. Pull this branch, fully restart Unreal to load the
new native worker (Python modules cached across pulls remain stale), then
launch Studio in a PowerShell session with `OPENAI_API_KEY` available.
Start a **new** one-click AI Transfer: the browser should pass through
`ANALYZING_PROJECTS` before `PREPARING`. The generated result screen
displays `ai_conversion_strategy`. Inspect the candidate-scoped
`ai-conversion-decision.json` and its `conversion_options`.

Real Unity 6.3 / Unreal 5.8 behavioral acceptance of this new planning stage
is still required. CI and mocks are not proof of cinematic parity.
