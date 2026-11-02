# Cinematic Studio v0.1 — connected one-click transfer

## Scope and safety

The default local UI is now the approved black/green cinematic workflow. Open
http://127.0.0.1:8765/ after starting the existing local Python server. The
original fully featured CED/CSIR/CineTwin Studio console remains available at
http://127.0.0.1:8765/?advanced=1; **its endpoints and controls were not
removed or replaced with mock UI**.

The normal user path is:

1. Start Transfer → select validated Unity and Unreal project folders.
2. Choose the discovered exported Unity timeline and target saved Unreal level.
   Approve source asset-copy permission. Optionally allow *explicitly labeled*
   best-effort transfer if the source census reports unsupported components.
3. Connect Projects → Start Transfer, one time.
4. The browser requests the existing source surface analysis, prepares the
   immutable candidate with embedded FBX materials on, records source/target
   approval and waits for the correct Unreal Editor companion. Once its
   real-time readiness and asset-import checks pass, it queues the same guarded
   native builder automatically. A browser refresh can recover that approval
   for the same candidate. No simultaneous or repeat submission is allowed.
5. Unreal imports/creates only the supported source-backed assets/actors,
   generates an editable sequence, saves the staged level, captures CineTwin
   actor/root-bone pose diagnostics if source capture exists, and collects
   read-only actual target material, lighting and native track evidence.
6. If fresh, source-provenanced Unity material/texture and *exact imported mesh
   slot* matches exist, a bounded recovery pass can reassign a lost base-color
   material to a fallback material slot. This is limited to newly staged
   actors; original user materials remain untouched. The worker repeats
   native audit after a change and stops on no progress, a safety failure,
   or a two-iteration cap. It does **not** claim to repair arbitrary shader,
   camera, skeleton, script or visual differences.
7. The Studio Results page reports actual generated sequence identity, native
   imported counts and binding counts when the Unreal API exposes them, plus
   clearly labeled incomplete evidence and source-verified feedback categories.
   The detailed advanced research console still supports manual native
   persistence/hierarchy audits after save/reopen.

### Requirements before you click Start Transfer

- A Unity project with a previously exported CSIR cutscene and, for CineTwin
  motion diagnosis, a source behavior capture. Studio does not fabricate an
  export from a .unity scene. Re-export the Unity source census with
  **Tools → CutsceneAI → Discover Installed Feature Surface** if needed.
- A backed-up Unreal project with its intended, saved staging level loaded.
  Never use your only copy or overwrite a verified historical sequence.
- The current **Unreal Editor Python companion**, started once in the intended
  Editor's Python Console. Studio provides a copyable exact command when
  necessary. The browser cannot run an editor Python script or start a project
  on the user's workstation by itself.
- A source-specific rights acknowledgement. This is not an entitlement to
  redistribute someone else's commercial or restricted game assets.

### Truthful progress and failure state

While the backend is running, the UI shows an **indeterminate** progress
indicator: no fabricated 72%, 100%, or timer-driven success. A green Sequence
Generated result means that Unreal produced an editable sequence, **not**
that the entire original cutscene has been perfectly reproduced. Native
source-target image frames, full joint rotations, light environment fidelity,
signal callback side effects, audio timing and post-restart package integrity
need independent evidence. A blocked stage, failed import or post-generation
repair cannot be silently retried against the same candidate.

### Verification and test coverage

- Python CI: full suite including one-click approval and source-aware
  closed-loop classifier; real engine APIs remain mocked in unit tests.
- Node CI: JavaScript syntax plus a simulated live backend one-click
  connect/prepare/approve/execute/results path, and a disconnected Unreal
  guard that must not send /api/execute.
- Unreal runtime validation still required for exact material slot matching,
  re-audit, import receipt counts, persistence, CineTwin metrics, and the
  source environment. Unity UI extraction and full visual comparison are not
  validated by GitHub Actions.

## Why no unlimited "until perfect" loop

The source-to-target converter cannot reliably map proprietary Unity shaders,
renderer features, SignalReceiver callbacks, every skeletal rig, and all
arbitrary game content without data and engine-specific adapters. Repeating
an unverified transformation risks double transforms, overwriting content,
unsafe re-imports and infinite loops. The runtime now automatically measures
available native/CineTwin domains and attempts a *bounded, source-backed
material repair*, but stops at unverified/unsupported domains. To extend this
safely, each additional CED strategy needs source extraction, native
construction, independent matching-time verification, an isolated retry
target, and an explicit regression gate. Do not mark master Issue #80 complete
based solely on generated UI/sequence or a green CI run.
