# CutSceneAI — generalizable cinematic transfer

## Goal

Support arbitrary discoverable source cutscenes *when portable semantic equivalents
and assets exist*. Never silently omit an authored track, clip, event, asset or
constraint. A converter cannot guarantee perfect fidelity for arbitrary engine
scripts, shaders, physics or mismatched skeletons.

The research goal is **coverage-aware, evidence-verifiable, cross-engine
cinematic transfer**, not making individual benchmarks look correct.

## Proposed processing stages

1. SOURCE INSPECTION — enumerate Timeline tracks, clips, properties, bindings,
   assets, parenting, events, cameras, lights, audio and timebase.
2. CANONICALIZATION — export CED/CSIR with provenance and preserve original
   source values and sections. Separately measure evaluated Unity poses.
3. COVERAGE GATE — account for every active source feature; identify missing
   target mappings, unsupported properties and limited event/audio behavior.
4. TARGET CAPABILITY PROBE — inspect loaded level/actors/assets and actual
   engine scripting APIs before changing any level state.
5. TRANSFER PLAN — build a deterministic, source-driven plan without a
   benchmark-name branch or manual Unreal corrections.
6. REALIZATION — create isolated target Level Sequence using native semantics
   where possible; otherwise an explicitly selected evaluated-motion bake.
7. INDEPENDENT READBACK — inspect saved target bindings, section metadata,
   actor positions, camera optics, skeletal pose and supported effects.
8. BEHAVIOR VALIDATION — compare source/target at matching sample timestamps,
   including source transitions and the target playback exclusive endpoint.
9. ACCEPT or REJECT — publish measured fidelity and retained limitations.

## Feature mapping policy

| Source feature | Preferred native translation | Fallback | Remaining limitations |
|---|---|---|---|
| Transform, props, hierarchy | Actor tracks and attachments | Bake evaluated world-space keys | Dynamic constraints, physics |
| Character and root motion | Skeletal sections plus explicit bone retarget maps | Bake measured joint poses on compatible skeleton | Different rigs and skinning |
| Timeline overlap | Source section trims/weights/easing | Bake final evaluated pose per frame | Subframe continuity |
| Cameras | Target camera component, cuts and optics | Bake pose/lens samples | Exposure and renderer differences |
| Lighting | Light component properties | Bake evaluated light channels | Render pipeline differences |
| Audio | Target sound assets and volume curves | Source PCM/stem export | Spatial mixing differences |
| Events | Equivalent target event endpoint and payload | Explicit marker-only mode | Marker does not execute an event |
| Scripts, custom shaders, physics | Explicit replacement implementation | Preview or render fallback | Can lose editability/interactivity |

OpenUSD/UsdSkel may help transport compatible skeletons/assets, but UsdSkel
does not recreate arbitrary runtime rigging or engine script behavior.

## Safety, auditability and acceptance

- No source feature can disappear from the coverage ledger.
- No animation section can disappear merely because an asset mapping is absent.
- Muted source tracks must not produce target sections.
- Source timebase, keys and animated property meaning are preserved or
  explicitly flagged as unsupported.
- The generator must not modify the level until source coverage, target
  capability checks and mapping checks succeed.
- Generate into an isolated target sequence; roll back touched actor transforms
  when generation fails and verify level persistence separately.
- A passing Python test suite means code contracts passed, NOT full
  Unity-versus-Unreal playback parity.
- Success is always conditional on a declared fidelity scope and bounded
  spatial, skeletal, camera, audio, event and render error metrics.

## Tools added to pull request #49

Source-only audit (no engine imports):

    python tools/transfer_readiness.py "<source.csir.json>" "<mapping.json>" --output "<readiness.json>"

Exit 2 means BLOCKED; READY_FOR_ENGINE_PREFLIGHT still requires real Unreal
capability probes. PARTIAL entries disclose incomplete behavior, not acceptance.

Real Unreal diagnostics (read-only): import diagnose_transfer from
integrations/unreal/ inside Unreal Python and call run(...). The diagnostic
records the exact failing stage, Python exception and traceback into JSON.
It does not generate a sequence.

## Immediate next decision

First obtain the precise failure stage from the current CineTwin_Test Unreal
project. Fix the generic source/adapter/capability defect and add a regression
test. Only resume staged generation after this passes. Do not rework source
cutscenes manually to bypass a transfer algorithm failure.

## Technical references

- https://dev.epicgames.com/documentation/unreal-engine/python-scripting-in-sequencer-in-unreal-engine
- https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/MovieSceneSectionEasingExtensions
- https://docs.unity.com/en-us/engine/6000.3/manual/animation-section/animation-mecanim/playables/class-playable-director
- https://openusd.org/dev/api/_usd_skel__intro.html
