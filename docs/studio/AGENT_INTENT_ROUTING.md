# CutSceneAI — Evidence-gated natural-language agent decisions

This is an internal implementation behind the existing **Connect projects → Transfer → Tell AI what to correct** Studio workflow. It does not introduce a new user-facing component or manual repair interface.

## Agent decision path

1. After a native transfer, the user submits a job-bound, immutable natural-language correction through the existing Studio conversation.
2. `agent_intent_router.recognize` maps the observation to a bounded semantic domain (material, shader, camera, lighting, rigging, animation, physics, VFX, audio, events, plugins or transforms). It does **not** guess a verified actor or scene identity.
3. `agent_intent_router.route` compares the requested domain and target class against existing independent CineTwin/native observations, the generated sequence state, source-backed material evidence, and the remaining repair budget. Multi-domain, unknown or unverified requests remain *report-only*.
4. LangGraph receives the plan, a limited source-approved CED precedent summary and informational registered-adapter identifiers. It can only select a strategy inside the router's **actual executable allowlist**.
5. The existing Unreal executor independently rechecks job/candidate/source hashes, exact loaded project and level, no-overwrite and durable write-ahead claim before any native operation. On a successful repair, the native receipt and audit are compared; unchanged or worsened evidence stops the loop. The repair budget is preserved across subsequent user messages.
6. The same Results chat can show recognized domains and a human-readable explanation, without exposing file paths or asking the user to choose an adapter.

## Safety contract

- A user observation is not independently verified evidence of a defect. It cannot authorize a native command or bypass a source-provenance preflight.
- Registry entries, unknown plugin classes and natural-language descriptions are **informational** until there is a concrete, verified native action, persistence check and independent behavioral acceptance. The agent cannot install, synthesize or run arbitrary code.
- In this PR, the **only executable AI repair** remains the pre-existing, GUID-backed `restore_source_albedo` operation. All other proposed repairs are reported as requiring an implemented adapter and appropriate evidence. This PR does *not* add animation, camera, shader, physics, VFX or arbitrary third-party plugin execution.
- A character-material fallback count cannot justify changing the **floor** or **wall** texture, even if an LLM proposes the known material strategy.
- Only one semantic domain may be automatically eligible. Compound requests require separate evidence and accepted native strategies; the agent reports the ambiguity instead of applying an arbitrary subset.
- The two-repair limit is retained across independent chat messages for the same candidate. No successful source-to-target equivalence claim is made without real editor acceptance.

## Extending this when the native adapters arrive

The developer's draft adapter PRs #117–#119 provide source-captured and registered examples. Their successor work (active blocking, constant PBR, rig retargeting and post-reopen CineTwin comparison) must first be published and reviewed. The transfer agent should **not** widen its executable allowlist merely because a new `ComponentAdapter` appears.

For each new repair type, separately require all of:

- CED semantic and exact source occurrence/candidate/target binding.
- A source-to-Unreal transformation and a native Unreal action already implemented in a permitted executor.
- A fresh, relevant native readback and independent CineTwin/source-to-target observation, including unit and timing conversion.
- A bounded strategy-specific plan with safe staging, no overwrite, write-ahead claim, receipts and remeasurement.
- Real Unity compilation, Unreal save and reopen in a separate process, and a measured behavioral test on a different project.

The user-supplied `NATIVE_ADAPTER_ACCEPTANCE.md` lays out the editor acceptance sequence. Those workstation experiments remain mandatory even when Python/Node CI is fully green.

## Reproduction

```powershell
python -m pytest -q tests/studio/test_agent_intent_router.py tests/studio/test_langgraph_agent_integration.py tests/studio/test_studio_agent_feedback.py
python -m pytest -q
python -m ruff check tests
node tests/studio/test_cinematic_ui.cjs
python tools/repo_check.py
```

All tests run on mocked local jobs and evidence. No real Unity or Unreal execution is claimed by this branch.

**PR dependency:** based on PR #120 (which depends on PR #115), avoiding the developer's native adapter branches and preserving the default minimal Studio UI.
