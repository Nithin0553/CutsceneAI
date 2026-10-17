# CineTwin Phase 1 — Source Behavior Capture (experimental)

## Objective

Replace assumptions about how a source engine executes a cinematic with measured evidence.
Do not replace the authored CSIR: CSIR preserves original intent; a CineTwin behavior
capture records evaluated state at requested instants. The original Unity scene and
Benchmark001 freeze remain authoritative and unchanged.

This milestone **does not** implement an Unreal CineTwin player, skeletal pose capture,
runtime event equivalence, captured sound, or pixel-perfect visual matching.

## Source-derived measurement plan

CLI:

```powershell
python tools/cinetwin.py plan "<frozen CSIR path>" "<output sampling-plan.json>"
```

The generic planner reads CSIR display rate, playback range, source entity IDs,
section boundaries, event timestamps, and Timeline native blend-in/out intervals.
It emits every source frame, precise boundaries, and four additional positions
along each authored transition (edge plus quarter samples) without changing CSIR.
Rational arithmetic prevents frame-rate drift for e.g. 24000/1001 fps.
Both the sampling plan and its source-byte SHA-256 are recorded separately.

Contracts:

- `packages/contracts/cinetwin/sampling-plan-v0.1.schema.json`
- `packages/contracts/cinetwin/behavior-capture-v0.1.schema.json`

## Unity prototype

The Unity package now contains an independent CineTwin editor assembly at
`integrations/unity/com.cutsceneai.extractor/CineTwin/Editor/`.
This assembly does **not** alter the existing read-only structural extractor.
The prototype uses `PlayableDirector.time` and `PlayableDirector.Evaluate()`
to observe live source runtime state. The prototype is restricted to **Play Mode**
because evaluation changes scene objects in memory. It does not write source
scene assets, call `SaveScene`, or modify the original CSIR.

Current observations:

- all requested source entity world positions, rotations, scales in canonical CSIR axes;
- native Unity camera **vertical FOV** for source camera entities;
- native Unity light **intensity** for source light entities;
- capture provenance and source snapshot identity.

**Important limitations:** Evaluating a Timeline can trigger Signals or script-side effects
at some timestamps. Play Mode guards against saving ordinary scene-state edits;
it does not sandbox arbitrary game scripts or external I/O. For important source
projects, use a working project copy or disable external side effects.

Unity's API documents that `PlayableDirector.Evaluate()` evaluates the
PlayableGraph at the explicitly chosen `director.time`:
https://docs.unity.com/en-us/engine/6000.3/script-reference/unityengine/playables/playabledirector/evaluate

## Local trial — Benchmark002

1. Pull latest `main` after the PR is merged.
2. In the VS Code PowerShell terminal, generate the sampling plan from the **existing
   frozen CSIR**, to the source project's export directory. Do not re-export CSIR.
3. Open the existing Benchmark002 scene in Unity. Select the GameObject with its
   Timeline `PlayableDirector`. Enter **Play Mode**.
4. Choose **Tools > CutsceneAI > CineTwin > Capture Selected Timeline Behavior (Play Mode)**.
   Select the sampling plan produced in step 2.
5. The capture appears under `<Unity project root>/CutsceneAI/Exports/`
   with suffix `.cinetwin.behavior.json`.
6. Exit Play Mode. **Do not save the original scene.**
7. Run:
   
   ```powershell
   python tools/cinetwin.py verify "<sampling-plan.json>" "<capture.cinetwin.behavior.json>"
   ```

An artifact may pass all implemented measurements while overall coverage remains
`INCOMPLETE`: skeletal pose, audio waveform, event execution, visual frames, and physics
are not captured yet. That is deliberate. Never present this Phase 1 capture as
the proof of a complete cross-engine transfer.

## Architecture and planned next iterations

```text
Frozen CSIR ──> Sampling plan ───────┐
                                     ↓
Original Unity project ───> Play Mode behavior capture
                                     ↓
                         Contract/completeness verification
                                     ↓
                        [Future] Unreal CineTwin player
                                     ↓
                        [Future] evaluated target readback
                                     ↓
                        [Future] automated semantic comparison
```

Next: capture evaluated character skeleton/bone poses and final blend outputs, then
create an independent Unreal behavior evaluator for the same timeline instants.
Only then add bounded, evidence-driven automatic correction.

## Repository cleanup result

The repository audit did not find obvious committed caches, disposable scene exports,
checkpoints, or datasets. Existing Benchmark001/002 documentation and frozen records
are research evidence, not clutter. None are deleted. Generated CineTwin artifacts
belong under ignored local paths or should be explicitly reviewed before committing.
