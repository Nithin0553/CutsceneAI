# CutSceneAI — cinematic elements, conversion routes, and evidence requirements

## Why a capability matrix instead of an “everything supported” switch?

Game cutscenes are extensible. Unity Timeline accepts custom Playables; Unreal
Sequencer accepts custom tracks; projects embed gameplay scripts, middleware,
and proprietary file formats. There is no finite complete list of *all* cutscene
assets. We can inventory the major families and add plug-in adapters; the
system must show any genuinely unsupported source semantics instead of marking
an approximation as a successful translation.

## Research-backed inventory

| Family | Elements included | Planned conversion route | Verification gate |
|---|---|---|---|
| Timeline | clip duration, timebase, frame rate, sub-sequences, blending, looping, markers | CSIR clock, section model, bake unsupported extrapolation | exact start/end and target sampling |
| Camera | camera cuts, blends, sensor and FOV, focal distance/DOF, camera shake, stereo | CineCameraActor + Sequencer tracks, sample unsupported lens behavior | matching-time camera projection and images |
| Spatial | actors, parenting, hierarchies, world/local transforms, constraints, splines | coordinate math, transform keyframes, preserved attachments | world-space transforms and attachment readback |
| Geometry | static/skinned meshes, LOD, morphs, normals, topology, instance meshes, geometry caches | FBX/glTF/USD/Alembic import and content-addressed associations | topology/material/mesh render checks |
| Skeletal | bones, rigs, retargeting, IK, additive, root motion, layers | transfer compatible clips; otherwise retarget or bake sampled bone motion | per-bone observed positions and blend timing |
| Facial | morph targets, visemes, eye gaze, lip sync | morph channels or skeletal bone curve bake | facial landmark/morph evaluation |
| Materials | shaders, PBR, custom surface graphs, decals, translucency, texture animations | translate supported PBR parameters; bake opaque custom shaders to textures | material properties and image similarity |
| Lights | lights, color, intensity, shadows, temperature, volumetrics | camera/lighting track adapters | photometric and rendered-frame comparison |
| Environment | terrain, sky, foliage, probes, weather, global illumination | project-level adapters, USD scene data, visually validated fallback | frame/camera render inspection |
| VFX | particles, smoke, Niagara/VFX Graph, trails, fluids, GPU effects | semantic remake or baked particle/geometry/video caches | time-synchronized rendered comparisons |
| Audio | music, speech, ambience, SFX, spatial effects, envelopes, fades | verified transcode, SoundWave and Sequencer audio | waveform/timing/loudness/audibility |
| Narrative | signals, quests, branches, events, triggers, dialogue state | explicit event and gameplay contracts, never blind code conversion | event execution logs and state assertions |
| UI | subtitles, captions, typography, accessibility prompts, HUD | timed text/UMG widgets | screen and timing measurements |
| Simulation | cloth, rigid body, soft body, destruction, collision | deterministic cache bake or target runtime equivalent | state/mesh sample comparison |
| Properties | enabled/visibility, arbitrary scalar/color curves, animation state | generic typed property channels | per-channel property readback |
| Media | movies, image sequences, compositing, media textures | Unreal Media Framework with verified codecs | frame decode and synchronization |
| Custom | game scripts, custom Playables, engine extensions, middleware | per-plugin signed adaptor contract or explicit unresolved | project-specific tests and approvals |
| Delivery | resolution, color space, HDR, rendering/captures, anti-aliasing | renderer/profile configuration and controlled capture | image/audio/performance comparison |

**Implemented now (limited scope):** CSIR-derived Sequencer action types already
present in the UE builder; automatic FBX skeletal/animation imports, WAV/MP3
staging, textures, and (when exactly resolved) static prop FBX import. Stable
character provenance can be resolved from Unity asset GUID/path; content-identical
copy duplicates may share one source identity. This is **not** a claim of
functional parity, retargeting, visual/material conversion, or complete game
feature coverage.

**Next major adapters**: verified Unity exporter GUID/path preservation for
renderer meshes and clips; real static material assignment and PBR translation;
Rig/Control Rig retargeting; blendshape and bone-curve export; native Unity
`.anim` FBX conversion; runtime events; VFX/cloth baking; source-vs-target
camera render comparisons. These are engineering milestones, **not** completed
features.

## Verified, degraded, and blocked

- `NATIVE_VERIFIED`: specific target data and independent behavior verified.
- `STRUCTURAL_ONLY`: target assets and tracks created, readback pending.
- `BAKED_PARTIAL`: time-sampled approximation whose deviation must be measured.
- `NEEDS_ADAPTER`: custom engine semantics require a new translator.
- `BLOCKED`: source bytes/identity unavailable or unsafe to invent.

No UI may claim *complete conversion* if the inventory contains unverified or
omitted features. Clear error explanations are an accountability mechanism,
not a substitute for adapting and testing more element types.

## References

- Unity Timeline track families: https://learn.unity.com/course/cutscenes-and-trailers-with-timeline-and-cinemachine/tutorial/introduction-to-timeline-2019-3
- Unreal Engine 5.8 Sequencer track list: https://dev.epicgames.com/documentation/unreal-engine/sequencer-track-list-in-unreal-engine
- Epic's Unity-to-Unreal asset migration guide: https://dev.epicgames.com/documentation/en-us/unreal-engine/migrating-assets-from-unity-to-unreal-engine
- Unreal Interchange import: https://dev.epicgames.com/documentation/en-us/unreal-engine/importing-assets-using-interchange-in-unreal-engine
- USD in Unreal: https://dev.epicgames.com/documentation/en-us/unreal-engine/universal-scene-description-in-unreal-engine
- Khronos glTF 2.0: https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html
