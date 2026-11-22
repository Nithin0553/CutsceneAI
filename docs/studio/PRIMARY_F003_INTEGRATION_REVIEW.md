# Primary integration review — Friday F-003 + Studio release candidate

**Review target:** `feature/studio-e2e-release-candidate-v0.1` (draft #128).  
**Friday source:** draft #130, commit `8d8bddbbce0e35da78d4afbd0759cf4c4b507c76`.  
**Previously reviewed Studio RC:** `51472b4394cf8513baf9de11f2835700d2005488`.  
**Combined review merge:** `fcc2db37890f43eb4ce415b8d9555b80260ea55b` (two parents, preserves both histories).  
**Combined verification:** [GitHub CI 44416807812](https://github.com/Nithin0553/CutsceneAI/actions/runs/44416807812), **1,082 Python tests passed, 7 skipped**; 14 UI contract scenarios and Windows Studio dependency bootstrap passed.

## Primary code review outcome

**F-003 software integration: REVIEWED / CODE-ONLY ACCEPTED IN A BOUNDED SCOPE.**  
**Studio software freeze: NOT DECLARED.**  
**Real-engine fidelity or genuine OpenAI acceptance: NOT TESTED.**

The reviewed moving action is `bake_verified_actor_world_trajectory`. It is not a generic character conversion feature. Eligibility requires one source-proven, unparented, unit-scale, non-humanoid character whose skeletal root remains stable relative to its translating/turning actor, one approved IK profile, and one supported FBX clip with an exact source frame grid. The native plan must contain one actor-owned trajectory and must refuse competing root correction, mutable source or target packages, unsupported APIs or ambiguous actor/rig bindings.

Audited code paths: `character_compatibility` → `animation_conversion_policy` → `studio_transfer_ai` → `transfer_backend` → native editor worker/preflight/one-shot attempt → imported raw-root sample guard → builder transform keys/hold behavior → independent native skeleton, clip and transform readback → CineTwin behavior comparison → reopened native acceptance → canonical `studio_release_gate`. Supporting positive, negative and recovery cases are in `tests/studio/test_moving_character_conversion.py` and existing Studio suites.

### Integration decisions

- Keep both the current release candidate and Friday's original branch independently traceable via a two-parent merge. No commits to `main`.
- Combine the overlapping release-gate changes, **preserving independent recomputation of source-bound camera optics, cut timing, actor/root and joint observations** while enforcing Friday's motion-specific native receipt. Reopened character action identity must agree with the AI-selected action.
- Do not reapply the old `tests/studio/test_reopened_camera_gate.py` Path-import correction over the newer primary developer file, which already includes it and more source/capture identity tests.
- Review includes native one-shot attempt journal, refusal and no-replay recovery, nonoverwriting candidate policy, explicit partial-import preservation and copy-on-prepare mapping.
- Real Unreal Engine 5.8 API compatibility still requires later in-editor smoke acceptance; API existence checks and synthetic doubles cannot establish real engine behavior. Editor/runtime root track sampling may refuse if a native API or package shape differs.

## Still required for the global Studio software freeze

1. Finish first-run Unity + Unreal companion setup/diagnostics, installation guidance and failure/recovery UX; existing Windows Python bootstrap is not a native companion installer.
2. Explicitly document and enforce support/refusal scope for full asset, material, clip and camera domains; do not claim arbitrary shaders, event execution, VFX, facial animation or simulation.
3. Complete final whole-Studio security review, integrated synthetic smoke with F-003, freeze checklist and reproducible status report. Calibrated joint orientation/bind-axis and rendered camera/projected frame parity are not established by angular displacement or FOV equality.
4. Keep genuine provider calls, Unity 6.3 compilation, Unreal 5.8 editor generation/save/reopen, independent CineTwin camera/motion playback and held-out source projects in the **later workstation acceptance gate**. They are expressly not part of the current CI result.

**Decision:** F-003 can be included in the software release-candidate branch for further development, but cannot by itself authorize `SOFTWARE_READY_FOR_ENGINE_TEST` or a full fidelity claim. The software checklist #127 and engine acceptance remain open.
