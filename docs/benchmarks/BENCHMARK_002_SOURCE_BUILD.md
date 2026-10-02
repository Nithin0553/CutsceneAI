# Benchmark 002 — Source Build Checklist

Benchmark002 should be authored manually inside the existing Unity benchmark project so the source remains a real engine-native Timeline while Benchmark001 stays frozen and untouched.

## Isolation rule

Reuse the project, not the benchmark artifacts. Keep Benchmark002 in its own scene and asset folder (for example `Assets/CutSceneAI/Benchmark002/`). Do not modify the Benchmark001 scene, Timeline, imported source files, or frozen export.

This makes Benchmark002 a **cutscene-generalization test** under the same project/runtime configuration. A later benchmark can intentionally change engine version or project settings to test project-level generalization.

## Build order

1. Reuse the existing Unity benchmark project, but create a **new scene** named `Benchmark002` and a new Timeline/PlayableDirector for it. Do not modify, duplicate over, or reuse the frozen Benchmark001 Timeline asset.
2. Set the Timeline display rate to **24 fps** and the sequence duration to **12.0 seconds**.
3. Create two independently bound humanoid actors: `CHARACTER_A` and `CHARACTER_B`.
4. Give `CHARACTER_A` two animation clips with a real overlap around the transition. At least one clip must contain root motion.
5. Give `CHARACTER_B` a separate animation track/clip so multiple skeletal bindings are exercised.
6. Add `PROP_MOVING` with transform animation and `PROP_PARENTED` with a real authored parent relationship.
7. Add three cameras: `CAM_A_Wide`, `CAM_B_Move`, `CAM_C_Close`; cut at exactly 4.0 s and 8.0 s. Animate `CAM_B_Move` transform and `CAM_C_Close` lens/FOV.
8. Add `LIGHT_KEY` and animate intensity.
9. Add two overlapping audio clips with at least one fade-in and one fade-out.
10. Add events at 2.5 s, 6.0 s, and 9.5 s; at least one must carry a payload.
11. Run **Tools → CutsceneAI → Analyze Project** and save the Project Intelligence profile.
12. Export CSIR with the Unity extractor.
13. Run the benchmark source checker before any Unreal work.

## Source checker

```powershell
cd B:\Research\CutsceneAI\CutsceneAI

python tools\check_benchmark_source.py `
  --spec "docs\benchmarks\BENCHMARK_002_SPEC.json" `
  --csir "D:\path\to\Benchmark002.csir.json" `
  --output "D:\path\to\Benchmark002.source-readiness.json"
```

Exit codes:

- `0` = READY
- `2` = hard benchmark failure such as wrong timebase/duration
- `3` = NEEDS_EVIDENCE / required feature not observed in CSIR

Do not start target generation while source readiness is `NEEDS_EVIDENCE`. First determine whether the source was authored incorrectly or the extractor/CSIR is failing to preserve the requirement.
