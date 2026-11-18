# CutSceneAI Agentic Studio — iterative, evidence-led implementation

**Stage:** opt-in native source bridge + existing guarded transfer foundations. **Not** universal conversion or trained-model certification.

## Target workflow

1. In Studio, choose the real Unity and Unreal projects. In Unity Editor, select the saved scene's PlayableDirector/Timeline and enable **Tools > CutsceneAI > Studio Bridge > Enable Source Bridge**. The bridge is disabled by default.
2. Studio's **Analyze selected Timeline in Unity** action queues one immutable, locally stored request under `CutSceneAI/StudioBridge/requests/`. The running Unity Editor (not a Python script parsing native Unity scenes) exports and augments CSIR and generates a feature census. It saves an immutable request-identified CSIR copy and a receipt with SHA-256 digests.
3. Studio checks the receipt and exported byte hashes, then refreshes its CSIR picker. The user selects the exact CSIR and matching source census, confirms rights and prepares a unique, non-overwriting transfer candidate.
4. The deterministic CSIR/CED adapter stack analyzes source capabilities, maps source-backed assets and plans supported Unreal objects/tracks. The Unreal worker performs guarded native imports and sequence creation.
5. Native saved readback and CineTwin observations evaluate what was built. An **opt-in** LangGraph agent can diagnose incomplete results and select only existing source-bound executable repair strategies. The model does not issue arbitrary editor scripts, call unknown plugins or certify its own output.
6. Persist every trial's inputs, decisions and diagnostics. The existing `packages/learning/case_memory.py` accepts **only independently validated and explicitly approved** mapping examples for future retrieval and optional training-dataset export. Running an export is not model weight fine-tuning; weights only change through a separate evaluated training operation.

## Extensible component contract

Use **D (discovered) → S (source captured) → P (planned) → N (native persisted) → B (behavior compared) → R (release eligible)** per source component. CED is the versioned semantic guidebook, not a guarantee of target support. Unknown components and plugins must remain discoverable and explain why an adapter is missing. Adding a new capability requires source capture, target action, readback, behavior test, declared compatibility and safe execution permissions. Do not silently translate Unity C#/URP/physics behavior into arbitrary Unreal code.

## What this change implements

- A *real* Unity Editor opt-in request handler for CSIR + source census, including byte-integrity receipts. It does not alter the selected Unity scene, launch Unity or export all cutscenes without selection.
- A local-only, token-protected Studio HTTP API for requesting and verifying native source evidence.
- A button and status workflow in Studio's Projects screen. It does not bypass the existing source census/asset transfer gates.
- Negative tests for malformed tickets, source identity, stale receipts, tampered snapshots, and symlink-based redirection.

## Requirements and limits

- Unity Editor and the CutSceneAI Unity extractor package from the **same checkout** must be installed and running. The appropriate PlayableDirector must be selected in a saved loaded scene. This bridge does not scrape or execute all Unity editor menu commands.
- The Unreal editor companion remains necessary for actual sequence creation. Its engine actions remain allowlisted and source/target scoped; unrestricted engine access is deliberately not delegated to a model.
- The user-requested *continuously improving* capability is a long-term validated learning lifecycle, not automatic per-run rewriting of model parameters. Failed/incomplete examples can inform diagnostics, but cannot become positive training labels. Use held-out project tests to establish improvement.
- Full fidelity for every arbitrary asset, custom script, shader, rig, middleware/plugin, effect and physics behavior is not technically established. Unsupported source semantics are retained as evidence and reported, not invented.
- GitHub Python/JS tests do **not** compile C# in Unity or prove an Unreal run. Native editor compilation and save/reopen acceptance are needed before this branch is merged or described as fully functional.

## Validation

From the repo root:
```powershell
python -m pytest -q tests/studio/test_studio_unity_bridge.py
python -m pytest -q
node tests/studio/test_cinematic_ui.cjs
python -m ruff check tests
```

Run the new source bridge on a **backed-up test Unity project** first. Confirm it creates one matching CSIR snapshot and census, and that Studio refuses changed evidence or an invalid/missing selected Timeline. Then perform a fresh guarded Unreal transfer in an unused destination. Preserve exact receipts and compare CineTwin source and target before making fidelity claims.
