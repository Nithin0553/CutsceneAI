# Benchmark002 — Studio UI regression protocol for CED v0.2

This test uses the **existing Unity Benchmark002 cutscene as source**. It does not
overwrite the frozen Benchmark001 or any existing Benchmark002 Unreal sequences.
Native Unreal save/reopen and source-to-target behavior remain separate evidence.

## 1. Open the latest Studio

On the developer Windows machine, save your local Unity and Unreal work, then
from a terminal:

```powershell
cd "B:\Research\CutSceneAI\CutsceneAI"
git switch feature/studio-ui-connected-v0.3
git pull origin feature/studio-ui-connected-v0.3
python tools/studio_local_bridge.py
```

Open **http://127.0.0.1:8765** in the browser (if the companion is already
running, restart it first so it loads updated Python modules). This UI can
connect local project folders; it cannot drive another person's editor from GitHub.

## 2. Choose the source and safe destination

- In Unity, open the existing project with Benchmark002. Ensure its CSIR export
  and source assets still exist. Do not rewrite a frozen benchmark.
- Optional strict source census: choose Unity menu
  **Tools → CutsceneAI → Discover Installed Feature Surface**. This writes
  `<Unity project>/CutSceneAI/Exports/feature-surface-unity-*.json`; the Studio
  Review screen discovers and compares the census to the selected CSIR.
  If the old CSIR lacks a matching source project fingerprint or has scripts
  that aren't yet extracted, Studio must report the gap. It must not invent a
  strict PASS. Keep the census unselected for a clearly labeled legacy
  source-only regression, or export updated **new** source evidence.
- In Unreal, back up the staging project and create/save a **new empty level**,
  for example `/Game/Testing/L_Benchmark002_CED02`. Never select a previously
  generated level full of target actors for this repeat experiment.
- In Studio Projects, Browse the Unity project root and Unreal project root.
  Select the existing **Benchmark002** CSIR and the *new saved empty Unreal
  level*. Confirm permission to import the source assets, then connect.

## 3. Review CED and preparation

- Review now displays **CED & feature discovery** with 39 feature families,
  735 semantic IDs and actual native action kinds. These are catalog counts,
  not conversion percentages.
- If a matching Unity census exists, select it and leave **Require matching
  complete source census** checked. If it flags unextracted scripts or project
  identity mismatch, investigate before relying on strict conversion.
- Keep the **ActivationTrack visual-only approximation OFF** for the baseline
  Benchmark002 test. It changes behavior semantics and should be tested as a
  separate opt-in candidate, if the source actually has an ActivationTrack.
- Click **Prepare transfer plan**. Studio creates a **new candidate ID**, a
  unique new target Level Sequence asset name, immutable plan, source CED
  inventory, coverage report and the automatic import setup. It does not
  modify Unreal merely by preparing.
- Check the Review panel: actual planned actions, source occurrence accounting,
  source-census state, missing adapter occurrences, and any review flags.
  Do not interpret an unverified feature route as a successful conversion.

## 4. Generate once in Unreal

- Open the **same new empty level** in Unreal Editor.
- In the Studio Transfer page, copy and run its **Editor companion** Python
  command in Unreal's Python Console.
- Confirm correct Unreal project/level and automatic setup readiness.
  Press **Import Unity assets & generate sequence** once; inspect any
  mapping, native import, or hierarchy warnings rather than hiding them.
- Do not retry the same candidate if native assets/actors were already staged
  and generation fails. Investigate the actual job receipt. Every new
  attempt must use a new candidate and a safe, backed-up target namespace.

## 5. Native readback and hierarchy

- After a generated sequence is actually saved, Save All in Unreal,
  close Unreal Editor completely, then reopen that project and new level.
- Open Studio **Results**. Copy its displayed **Native audit command** into
  Unreal Python Console (only if that audit has not already run for this job).
- Return to Studio Results and click **Refresh evidence**. This reads the
  actual report JSON from the active job's candidate folder; it does not
  manufacture a result or execute any Unreal code itself.
- Reference baseline from the prior real Editor trial:
  18/18 imported assets, 10/10 mapped actors, 2/2 direct prop parent links.
  Verify these **again** on this fresh candidate. Eight missing source
  grouping/ancestor relationships (#68/#85) remain open unless independently
  reconstructed by a separate source-aware algorithm.

## 6. CineTwin and advanced game-ready test gate

Only after the new Benchmark002 run is stable, compare matching frames from
the actual Unity source and Unreal target: camera cuts, actor transforms,
skeletal joint poses, root motion, audio, lights, events, attachments,
rendering, and source hierarchy effects. Record thresholds and measured
failures rather than a manually chosen success score.

The next test should be a **separate original game-ready cutscene** with
more complex animation, camera rigs, materials, VFX, audio/dialogue, events,
skeletal attachments and source hierarchy, ideally outside the Benchmark002
assets. Its source feature census must be captured; unsupported plugin
components must be tracked per family and must not be called converted.

Current completion status is **UI/automatic-plan integration implemented and
CI-tested**; this exact fresh Benchmark002 run must be executed and evidenced
inside the user's Unity/Unreal Editors before marking engine acceptance.

## Evidence references

- `packages/contracts/dictionary/cutscene-elements-v0.2.json`
- `packages/studio/feature_dispatch.py`
- `tools/studio_ui_features.py`
- `docs/studio/CED_INDUSTRY_COVERAGE_V02.md`
- GitHub issues #80, #62, #68, #72, #85 and #86.
