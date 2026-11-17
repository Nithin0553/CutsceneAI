# CutSceneAI Studio — One-click agent-first transfer and user corrections

**Scope:** simplify the default Studio interface to selecting a Unity project and an Unreal project, then pressing **Transfer**. Internal CSIR, source-census, CED planning, Unreal generation, native evidence and LangGraph diagnostics remain behind the scenes. This branch extends the opt-in Unity source bridge and learning foundations from [PR #115](https://github.com/Nithin0553/CutsceneAI/pull/115).

## What the user does

1. Start Studio and connect the source Unity project and destination Unreal project.
2. Confirm permission to transfer source assets; press **Transfer** once.
3. Studio requests a new immutable Unity CSIR + source census via the installed Unity Editor source bridge, selects the sole loaded Timeline or the explicitly selected PlayableDirector, creates a source-provenanced connection and plans the transfer.
4. The existing Unreal worker executes the immutable, source-aware conversion into a fresh candidate/sequence and writes readback and CineTwin evidence. The agent is enabled for guarded, post-generation diagnosis.
5. Once an editable sequence exists, the user can write an observation such as “The wall texture is missing” in the same Results view. The comment is immutable and bound to that job; the agent can use it as an **unverified observation**, compare independent native evidence, and choose from installed and permitted repair strategies.
6. The local Studio coordinator continues across page refreshes and does not rely on the browser to re-submit jobs. It must never repeat an already claimed Unreal edit or silently overwrite existing assets.

## Native setup boundary

The source bridge is **disabled by default** for privacy. On first use, open the matching Unity Editor project with the extractor package installed and enable `Tools > CutsceneAI > Studio Bridge > Enable Source Bridge`. Keep the saved cutscene scene loaded. If several eligible Timelines exist, choose the desired PlayableDirector; the bridge refuses to guess.

Open the chosen backed-up Unreal project and start the compatible Studio editor worker once. With multiple existing levels, the active Editor level is the only permitted target. If no level exists, existing guarded automatic map creation applies. The Studio user does not select a CSIR file, census export, manual mapping or AI option.

The default user-facing workflow is now simplified; the existing manual research UI is preserved for specialized review at `?manual=1`, and the existing advanced research UI at `?advanced=1`.

## Server and state

- `POST /api/autopilot/start` begins a single durable, rights-confirmed transfer.
- `GET /api/autopilot` exposes the current safe stage (`WAITING_FOR_UNITY`, `CONNECTING`, `PREPARING`, `WAITING_FOR_UNREAL`, `UNREAL_RUNNING`, `GENERATED_UNVERIFIED`, `BLOCKED`).
- `POST /api/agent-feedback` accepts a bounded natural-language observation only after an AI-enabled transfer exits native generation. It writes an immutable evidence record with `execution_authorized=false`; **the user comment itself never grants native editor privileges**.
- `GET /api/agent-conversation` shows the latest job's feedback and the agent's status/reasoning.
- Requests use the existing token-protected localhost API. Source/target identities and non-overwrite rules remain enforced in existing deterministic operations.

## Real AI-correction scope

The existing LangGraph loop can diagnose missing or unsupported source elements and reason about user comments. **The only currently wired, executable AI repair remains source-backed material/albedo restoration.** A user report about pose, camera, physics, shader, VFX or an arbitrary script cannot yet be auto-fixed without a real registered engine adapter and supporting CineTwin observations. The agent must report `UNRESOLVED_NO_SAFE_STRATEGY` or another precise blocked state, not claim success or run an arbitrary script.

Newly developed adapter families in draft [PRs #117](https://github.com/Nithin0553/CutsceneAI/pull/117), [#118](https://github.com/Nithin0553/CutsceneAI/pull/118) and [#119](https://github.com/Nithin0553/CutsceneAI/pull/119) require independent native engine verification and separate integration before expanding corrective actions.

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
- Automatic analysis requires one unambiguous Timeline (selected when several exist).
- Source census strict gaps are recorded as unsupported under the existing labelled best-effort policy; generation cannot be called complete fidelity if a feature is missing.
- Natural-language intent cannot prove that the described defect is present or that the proposed repair was successful. Preserve source/target observations and verification results.
- The user-facing component model stays minimal; there is no extra CineTwin dashboard or manual conversion selector in the default UI.
