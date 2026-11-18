# CutSceneAI Studio — One-click agent-first transfer and user corrections

**Scope:** simplify the default Studio interface to selecting a Unity project and an Unreal project, then pressing **Transfer**. Internal CSIR, source-census, CED planning, Unreal generation, native evidence and LangGraph diagnostics remain behind the scenes. This branch extends the opt-in Unity source bridge and learning foundations from [PR #115](https://github.com/Nithin0553/CutsceneAI/pull/115).

## What the user does

1. Start Studio and connect the source Unity project and destination Unreal project.
2. Confirm permission to transfer source assets; press **Transfer** once.
3. Studio requests a fresh Unity CSIR and source census in Edit Mode, finds the sole loaded Timeline or the explicitly selected PlayableDirector, and creates an immutable, SHA-256-bound CineTwin sampling plan automatically. The opt-in Unity companion then captures the planned source behavior in **existing Unity Play Mode**, without a file picker. If Unity is not already in Play Mode, Studio displays that dependency and waits without fabricating behavior samples.
4. After the independent source capture validates, Studio constructs the source-provenanced connection and plans the transfer. The existing Unreal worker executes into a fresh candidate/sequence and writes native readback. Post-reopen target CineTwin comparison is still an explicit native acceptance requirement, not yet a fully unattended background verification.
5. Once an editable sequence exists, the user can write an observation such as “The wall texture is missing” in the same Results view. The comment is immutable and bound to that job; the agent can use it as an **unverified observation**, compare independent native evidence, and choose from installed and permitted repair strategies.
6. The local Studio coordinator continues across page refreshes and does not rely on the browser to re-submit jobs. It must never repeat an already claimed Unreal edit or silently overwrite existing assets.

## Native setup boundary

The source bridge is **disabled by default** for privacy. On first use, open the matching Unity Editor project with the extractor package installed and enable `Tools > CutsceneAI > Studio Bridge > Enable Source Bridge`. Keep the saved cutscene scene loaded. If several eligible Timelines exist, choose the desired PlayableDirector; the bridge refuses to guess. To capture actual Timeline behavior, enter Unity Play Mode when prompted. Studio **does not silently enter Play Mode**, run user scripts or save runtime-modified Unity scenes. The bridge only uses the already running editor and a source-verified sampling plan. This is an honest prerequisite still preventing a completely unattended one-click workflow.

Open the chosen backed-up Unreal project and start the compatible Studio editor worker once. With multiple existing levels, the active Editor level is the only permitted target. If no level exists, existing guarded automatic map creation applies. The Studio user does not select a CSIR file, census export, manual mapping or AI option.

The default user-facing workflow is now simplified; the existing manual research UI is preserved for specialized review at `?manual=1`, and the existing advanced research UI at `?advanced=1`.

## Server and state

- `POST /api/autopilot/start` begins a single durable, rights-confirmed transfer.
- `GET /api/autopilot` exposes the current safe stage (`WAITING_FOR_UNITY`, `WAITING_FOR_UNITY_CAPTURE`, `CONNECTING`, `PREPARING`, `WAITING_FOR_UNREAL`, `UNREAL_RUNNING`, `GENERATED_UNVERIFIED`, `BLOCKED`).
- `POST /api/agent-feedback` accepts a bounded natural-language observation only after an AI-enabled transfer exits native generation. It writes an immutable evidence record with `execution_authorized=false`; **the user comment itself never grants native editor privileges**.
- `GET /api/agent-conversation` shows the latest job's feedback and the agent's status/reasoning.
- Requests use the existing token-protected localhost API. Source/target identities and non-overwrite rules remain enforced in existing deterministic operations.

## Real AI-correction scope

The existing LangGraph loop can diagnose missing or unsupported source elements and reason about user comments. **The only currently wired, executable AI repair remains source-backed material/albedo restoration.** A user report about pose, camera, physics, shader, VFX or an arbitrary script cannot yet be auto-fixed without a real registered engine adapter and supporting CineTwin observations. The agent must report `UNRESOLVED_NO_SAFE_STRATEGY` or another precise blocked state, not claim success or run an arbitrary script.

Draft [PR #122](https://github.com/Nithin0553/CutsceneAI/pull/122) contains static collider blocking, constant PBR material staging, approved Unreal IK retargeting and post-reopen CineTwin acceptance tooling. They are now combined with the agent stack in draft [PR #124](https://github.com/Nithin0553/CutsceneAI/pull/124), but **native conversion adapters are not automatically executable AI-correction strategies**. Independent editor verification remains mandatory before expanding corrective actions.

## Verification

From this branch:

```powershell
python -m pytest -q
node --check apps/studio-web/cinematic.js
node tests/studio/test_cinematic_ui.cjs
python -m ruff check tests
python tools/repo_check.py
```

Mock tests prove the API state machine, duplicate-job protection, simulated Unreal worker, identity checks, corrected UI workflow, and natural-language feedback recording. They **do not** compile C# in Unity or prove native Unreal behavior. Before merging into `main`, run a fresh project copy through the entire workflow, capture real Editor receipts, and independently reopen the Unreal target. Test a user-reported missing texture and an intentionally unsupported correction. Confirm truthful outcomes, no overwrites, and no repeated native repair.

## Known limitations

- Requires running local Editors with their installed companions; this code does not remotely operate closed Editors or request arbitrary tool access.
- Native CineTwin sampling requires **existing Unity Play Mode**. Until a safely isolated Play Mode service is developed and editor-verified, Studio waits for the user to enter Play Mode instead of silently executing project scripts. A queued source capture is not a native playback comparison or a release certification.
- Automatic analysis requires one unambiguous Timeline (selected when several exist).
- Source census strict gaps are recorded as unsupported under the existing labelled best-effort policy; generation cannot be called complete fidelity if a feature is missing.
- Natural-language intent cannot prove that the described defect is present or that the proposed repair was successful. Preserve source/target observations and verification results.
- The user-facing component model stays minimal; there is no extra CineTwin dashboard or manual conversion selector in the default UI.
