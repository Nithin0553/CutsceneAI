# Element 5 — Source-Bound Conversion Plan (v0.1)

**Canonical architecture:** Unity source evidence + Unreal capability evidence → CED retrieval → LangGraph AI planning → Element 4 validated strategy / bounded alternative reasoning → **Element 5 source-bound conversion plan** → guarded Unreal execution → native readback/CineTwin → bounded repair/re-measure.

**Implementation branch:** `feature/element5-source-bound-conversion-plan-v0.1`, stacked on draft PR #143 (Element 4). This phase is software-only; running a real Unity or Unreal editor remains deliberately deferred.

## Design principle

The repository already has a mature deterministic CSIR-to-Unreal compiler in `packages/studio/transfer_backend.py` and `integrations/unreal/csir_plan.py`, plus the source-authenticated immutable handoff (`prepared_transfer.py`). Element 5 **does not replace that compiler** or ask a model to synthesize executable Unreal Python. It produces a separate, read-only, cryptographically bound **reconciliation plan** over the exact compiled action list, source occurrences, mapping and Element 4 planning evidence. Original action payloads and their order remain untouched.

This separation matters: a native action that exists in a prepared plan is not necessarily attributable to a particular Unity source track/section, and a source/CED concept that is inventoried is not necessarily converted. Existing legacy builder actions often lack exact `source_location` metadata. Matching an actor's name, track name, approximate time or semantic category is **not sufficient to prove provenance**. Therefore, the Element 5 report labels legacy actions as *UNATTRIBUTED*, even when the overall deterministic compiler may still legitimately create an editable Sequencer track after separate user approval.

## Implementation

`packages/studio/studio_element5_plan.py` is a dependency-light, source-bound contract with `build()` and `verify()`. It checks:

- Original Unity CSIR canonical SHA-256 and every independently enumerated asset, entity, Timeline track, section, animation curve and relationship, with unique `E00000` structural source IDs.
- Exact prepared native action array, registered native kind, immutable payload SHA-256 and **original builder action order**; unknown actions, foreign/duplicated source links and unsupported source/action mappings fail closed or appear as authorization-blocking native eligibility gaps.
- Exact target mapping/sequence identity and `overwrite_sequence=false`. A declared target mapping is labeled *UNVERIFIED* until real editor inspection and native persistence.
- Element 3 source inventory, dependency schedule, source-bound CED comparison and independently validated Element 4 **baseline**. The baseline is read-only and report-only; it does **not** claim a model validated a transfer or that the existing compiler carried out the model's suggested per-occurrence choices.
- Per-source anonymous conversion-plan outcomes (explicit native source link; unknown semantic; unresolved source dependencies; target reference missing; no explicit action provenance), and source-to-builder action membership only when the installed compiled action provides exact explicit provenance.
- A source/target/action/strategy/Element 4 bound SHA-256 record, per-element and per-action counts and explicit `native_execution_authorized=false`, `target_readback_verified=false`, `full_cutscene_fidelity_verified=false`.

`tools/studio_element_workflow.py` creates this complete Element 5 plan for the active prepared candidate, stores it inside the immutable candidate-local workflow evidence and independently reconstructs it every time the active review is read or an approval is checked. Candidate changes to the Unity source, mapping, prepared native actions, CED strategy or capability evidence invalidate the previous review and its consent.

`integrations/unreal/studio_element_native_gate.py` separately **rebuilds Element 5 inside the actual Unreal worker before any scene mutation**, without importing a model or expanding the native action registry. The previous exact-action operator consent, origin/session checks, destination readiness, independently recompiled native plan and Unreal preflight remain authoritative.

The Studio Review screen shows Element 5 source coverage, native action counts, exact source attribution versus legacy unattributed actions, blocked operations and paginated per-occurrence source-to-action status. It does not show proprietary source names, private asset paths or target actor labels from the original cutscene.

## Element 4 to Element 5 relationship

The Element 4 *baseline* is independently source-verified and, by default, records all not-yet-model-reviewed occurrences as `report_only`. It cannot grant the deterministic compiler new actions. Where an explicitly opt-in model decision exists, the Studio's separate Element 4 source-bound model-evidence verifier continues to show whether that decision has actually been independently validated. That model decision is advisory and cannot silently replace the deterministic compiler's real action payloads. Full per-action model-selected execution awaits separately implemented, validated adapter-specific semantics; it is not claimed by this phase.

## Software acceptance and limitations

1. No omitted or duplicated source occurrences, even for unknown/unregistered CED extensions.
2. Every immutable compiled action is accounted for exactly once, in original order, with the installed native handler kind and SHA-256 fingerprint.
3. Explicit per-source references must correspond to exact supported source occurrences; legacy unlinked actions are visible instead of being silently assigned provenance.
4. No unregistered Unreal Python, unsafe or foreign source refs, tampered/rehashed ledgers, changed mapping or stale Element 4 validation can pass the reconstructed plan.
5. No native engine writes, AI tool permission, claimed target readback, full-cutscene fidelity, or engine restart as part of this planning stage.
6. The existing native worker independently rechecks this artifact before mutation, and the Studio review requires explicit operator approval of any unavoidable legacy unattributed native actions.

**Deferred acceptance:** actual Unity and Unreal engine compilation, generated playable Sequencer persistence, real actor/rig/camera/audio/event measurement, held-out project coverage and full cinematic fidelity. Software test passes are not a substitute for these.
