# Element 1 — Unity Source Intelligence audit and hardening

**Status:** Software changes and automated contract tests on
`feature/unity-source-intelligence-hardening-v0.1` (stacked on
`feature/agent-driven-ced-orchestration-v0.1`).
**Native Unity compilation and workstation acceptance: not yet performed.**

## Audit basis and findings

Inspected the actual Unity package
`integrations/unity/com.cutsceneai.extractor/` and the Studio host
`tools/studio_unity_bridge.py`, the related Python/Node tests, and the
current source CaptureForStudio implementation. This review targets
general project connection, provenance and evidence invariants, never
a particular Benchmark001/002 entity.

| Subsystem | Before | Decision |
| --- | --- | --- |
| Source bridge consent | `EditorPrefs` key was global across all Unity projects | Use a SHA-256-derived **project-scoped** EditorPrefs key; explicit opt-in must occur in the selected project |
| Connection heartbeat | `WritePresence` swallowed IO/access errors; menu still logged "enabled" and native requests could run without visible presence | Report a deduplicated Unity Console diagnostic, return success/failure, refuse request polling when presence cannot be written |
| Protocol compatibility | A new bridge implementation could report the old heartbeat version | Bump heartbeat to `unity-editor-v0.3`; reject older versions with explicit Package Manager guidance |
| Host connection diagnosis | Missing, stale, disabled, invalid or wrong-project presence was hard to distinguish in Studio UI | Emit specific `editor_status` categories and safe `next_action` hints, display them on the Projects screen |
| CineTwin evidence hashing | `hashlib.sha256(path.read_bytes())` loaded up to 128 MiB into a temporary byte buffer before JSON parsing | Validate bounded size *before reading* and hash in 1 MiB streaming chunks; keep 128 MiB CSIR/census/capture and 8 MiB plan limits |
| Source–capture identity | Verified snapshot receipt, CSIR SHA, census fingerprint, sampling plan SHA and Cinema behavior receipt already present | **Retain** exact hashes, no synthetic capture, and Play Mode consent; do not bypass these invariants |
| Unity scene mutation | Source bridge uses read-only Timeline/census export and captures in explicitly entered Play Mode | **Retain** original source scene/asset protection and non-replayed receipt processing |

### Clear responsibility boundaries

- Unity source bridge captures **actual source evidence**. It never generates
  arbitrary target conversion actions or claims full parity.
- The CSIR and source feature census remain ground truth for source structure,
  including **unknown/unsupported** features. Missing native adapters are a
  knowledge/planning issue, not a reason to invent source data.
- CineTwin sampling/capture remains a separate native Play Mode operation,
  bound to the exact source hash and independently validated on the host.
- The agent may retrieve the source evidence, but no LLM decision can override
  a rejected source identity, stale hash or unsupported native capability.
- The Studio web UI remains a connection/status view, not another coordinator.

## v0.3 lifecycle and manual engine acceptance

This is a **bridge protocol change**. The new companion intentionally does
not inherit an old global opt-in or mark an old v0.2 package as compatible.

1. Update the Git checkout to the dedicated Element 1 branch (or a reviewed
   descendant after merge).
2. In Unity Package Manager ensure the installed
   `com.cutsceneai.extractor` points to the current Git checkout's
   `integrations/unity/com.cutsceneai.extractor/package.json`, **not** an
   older duplicate/acceptance sandbox. Let scripts recompile.
3. Open the exact source project and a saved scene with a Timeline
   `PlayableDirector`. Choose **Tools > CutsceneAI > Studio Bridge >
   Enable Source Bridge**. Consent is now project-specific.
4. Inspect `<selected Unity project>/CutSceneAI/StudioBridge/unity-editor.json`.
   Expect `bridge_version: unity-editor-v0.3`,
   `source_bridge_enabled: true`, a fresh UTC heartbeat, actual project root,
   Editor PID, and `EDIT_MODE` or `PLAY_MODE`.
5. In PowerShell use the running Studio's
   `GET http://127.0.0.1:8765/api/status`. Confirm
   `unity_editor.connected: true`. For `UNSUPPORTED_UNITY_BRIDGE_VERSION`,
   `UNITY_SOURCE_BRIDGE_DISABLED`, `WRONG_UNITY_PROJECT`,
   `UNITY_COMPANION_RELOADING_OR_OFFLINE`, or
   `INVALID_UNITY_BRIDGE_HEARTBEAT`, follow `next_action` before retrying.
6. Request a **fresh** transfer and inspect the immutable snapshot CSIR,
   census, sampling plan, capture and receipts. Enter Play Mode only when
   prompted. Do not restart Unity/Unreal merely to reload Python backend
   code. C# compiled package changes may require Unity compilation/reload.
7. Run one new, non-benchmark cutscene including scene hierarchy, camera
   motion/FOV, source materials, and a character or unsupported custom
   component. Verify source identities, unknown feature disclosures and
   observed Play Mode behavior separately. Do not infer target parity from
   successful source extraction.

## Software regression coverage

- `tests/studio/test_unity_editor_presence.py`: live, stale, future,
  disabled, incompatible version, wrong-project, malformed, symlink and
  unavailable marker; static proof of per-project opt-in and fail-closed
  heartbeat writes.
- `tests/studio/test_studio_unity_bridge.py`: source/census fingerprint,
  request/receipt SHA, capture plan provenance, tamper/symlink refusal,
  streaming SHA and >128 MiB sparse capture size guard.
- `tests/studio/test_cinematic_ui.cjs`: visible project-specific Unity
  connection diagnostic after choosing a source folder.
- Existing CineTwin, source scanner and Timeline extractor contracts still
  run in the complete CI suite.

**Limitations:** Automated tests do **not** compile the Unity C# scripts,
install the package in Unity 6.3, validate real Editor filesystem permissions,
measure previously unseen native Timeline behavior, prove complete extraction
of arbitrary third-party components, or certify Unreal parity. Native
acceptance and held-out cross-engine fidelity remain required. Unsupported
source features must be reported, not silently omitted or labeled converted.
