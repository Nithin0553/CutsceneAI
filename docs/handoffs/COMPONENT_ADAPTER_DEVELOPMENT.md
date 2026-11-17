# CutSceneAI Studio component adapter handoff

The local changes start at PR #114 head `8fb62333fccc4e8913984c0156227f04927c1bbc`.
That branch supplies MeshCollider and LOD source capture and includes PR #113's
static FBX scenery mapping. PR #115 supplies a separate Unity intake bridge
and approved-case learning. The adapter changes build on the existing planner,
engine worker and release evidence checks. Review the stacks in dependency order.

| Local branch | Changes | Relevant issues |
| --- | --- | --- |
| `feature/studio-native-component-adapters-v0.1` | Source identity and engine version gates, installed component registry, light shadow action, structural channel readback | [#94](https://github.com/Nithin0553/CutsceneAI/issues/94), [#95](https://github.com/Nithin0553/CutsceneAI/issues/95), [#97](https://github.com/Nithin0553/CutsceneAI/issues/97) |
| `feature/studio-static-collider-adapters-v0.1` | Box, sphere and capsule extraction, native volume staging and independent geometry comparison | [#95](https://github.com/Nithin0553/CutsceneAI/issues/95), [#98](https://github.com/Nithin0553/CutsceneAI/issues/98) |
| `feature/studio-custom-component-evidence-v0.1` | Custom serialized snapshots, package version constraints, registered test adapter, bounded LangGraph diagnostics | [#94](https://github.com/Nithin0553/CutsceneAI/issues/94), [#95](https://github.com/Nithin0553/CutsceneAI/issues/95), [#99](https://github.com/Nithin0553/CutsceneAI/issues/99) |

## Verification and outstanding work

| Adapter family | Result on this stack | Outstanding acceptance |
| --- | --- | --- |
| Skeletal rigs and animation | Existing routes are the baseline | Compatible-rig import validation, retargeting, layer / root-motion ownership, Benchmark002 regressions and held-out pose measurements. [#96](https://github.com/Nithin0553/CutsceneAI/issues/96) |
| Physics | Box, sphere, and capsule geometry can enter automatic native staging. The generated volumes use disabled collision. | Real-editor save and reopen, MeshCollider cooking, active collision, rigidbodies, triggers, constraints, and simulation baking |
| Materials and rendering | Native Boolean shadow-enable track and structural track checks | Evaluated shadow and image measurements, PBR and shader adapters, animation and transparency |
| Procedural effects | Pending | Particle and cache extraction, Niagara mapping, time-matched VFX observations |
| Custom components and packages | Read-only typed authoring capture, package inventory and synthetic registration test | Compile and transfer from a real test package, add supported Playable semantics and target middleware adapters |
| Other native behaviors | Existing camera, light, audio, hierarchy and event paths are the baseline | Complex cameras and environment, native LOD, events and timed UI |
| Agent feedback | Installed adapter summaries are available for diagnosis | Verified corrective strategies for all new domains, wider rerun and held-out learning assessment |

The Python tests check planning, malformed or ambiguous source rejection, native
API mocks and rollback. Unity compilation, a real Unreal Level Sequence and
paired time-aligned CineTwin playback captures remain pending. Issues #94–#99
need their respective editor evidence.

## Run the checks

To review the bundle in an existing CutsceneAI clone, put it next to that
clone and run these commands from the repository root.

```bash
git fetch origin feature/source-component-capability-contract-v0.1
git bundle verify ../CutSceneAI-Adapter-Phases.bundle
git fetch ../CutSceneAI-Adapter-Phases.bundle 'refs/heads/feature/studio-*:refs/remotes/adapter-review/feature/studio-*'
git switch -c review-component-adapters adapter-review/feature/studio-custom-component-evidence-v0.1
```

Run from the repository root with Python 3.11 and Node available.

```text
python -m pip install pytest ruff jsonschema "langgraph>=1.0,<2"
python -m compileall -q packages tools integrations/unreal
python -m pytest -q
python -m ruff check tests
node --check apps/studio-web/app.js
node --check apps/studio-web/cinematic.js
node tests/studio/test_cinematic_ui.cjs
python tools/repo_check.py
```

On the Windows test machine, start Studio with
`powershell -ExecutionPolicy Bypass -File .\tools\start_studio.ps1`.
Install the matching Unity extractor and reload the Unreal worker from the
same checkout. Use separate backed-up target maps and freshly prepared
candidates. Follow [the collider acceptance procedure](../studio/NATIVE_COLLIDER_GEOMETRY.md)
and [the release checks](../studio/RELEASE_ACCEPTANCE.md) to collect independent
save/reopen and behavior evidence. Extension instructions are in
[Executable CED adapters](../architecture/CED_ADAPTER_EXECUTION.md).

## Research observations

The primitive adapter shares conversion and observation code across source
shape classes. Matching dimensions and orientation provides a reproducible
geometry check. Collision channels, callbacks, and motion require separate
behavioral data. Package version and typed source evidence make a deterministic
decision possible for a registered scalar adapter. The fixture verifies the
planning contract. Cross-project and cross-version generalization still need
independent editor examples.
