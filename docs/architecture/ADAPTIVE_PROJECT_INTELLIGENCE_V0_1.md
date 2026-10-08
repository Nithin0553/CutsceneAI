# Adaptive Project Intelligence and Mapping (v0.1)

**CutSceneAI | Benchmark 001: Unity → Unreal**

## 1. What is the purpose?

CutSceneAI transfers an **existing cutscene** from one game engine to another. The goal is to preserve the original camera work, character movement, timing, audio, and other cinematic details.

However, Unity and Unreal do not always store or interpret information in the same way. Their behavior can also change with engine versions, plugins, and project settings.

**Adaptive Project Intelligence checks these differences before the transfer. Adaptive Mapping decides how to handle them.**

Put simply: **understand both projects first, then transfer the cutscene correctly.**

## 2. Why is this important?

Imagine copying a camera's rotation from Unity into Unreal. Even if the numbers are correct, Unreal might interpret them differently, making the camera point in the wrong direction.

Similar differences can occur with frame rates, animation settings, camera lenses, and character movement. This means **copying data is not always the same as preserving the cutscene**.

The system must check how both projects actually work instead of assuming that every Unity or Unreal project behaves identically.

## 3. How does the system work?

```text
Analyze the Unity project       Analyze the Unreal project
            \                          /
             \                        /
              Compare project settings
                         |
                         v
             Read the original cutscene
                         |
                         v
              Choose mapping rules
                         |
                         v
             Build the Unreal cutscene
                         |
                         v
          Read it back and check accuracy
```

There are four important concepts:

| Term | Simple explanation |
| --- | --- |
| **CED (Cutscene Element Dictionary)** | Defines what a camera, animation, event, etc. means, regardless of the game engine. |
| **CSIR (CutSceneAI Interchange Representation)** | Stores the original cutscene's information in a common format. It is the source of truth. |
| **Project Intelligence Profiles** | Record relevant facts about both projects, including engine capabilities, settings, and how they handle cameras, animation, and timing. |
| **Resolved Mapping Dictionary** | Records the chosen method for transferring each element to this particular target project, with supporting evidence. |

**Important:** CED and the original CSIR do not change when the destination changes. Only the mapping decisions need to be recalculated. Extra observations about the source, such as camera-axis details or root motion, can be saved separately without changing the original data.

## 4. A real example from Benchmark 001

Benchmark 001 transfers a manually created **Unity Timeline** into an **Unreal Level Sequence**.

During this work, a camera-rotation problem demonstrated the need for adaptive mapping:

1. The camera rotation was correct in CutSceneAI's shared representation.
2. Unreal's Python interface exposed positional rotation values as **roll, pitch, yaw**, while commonly used Unreal C++ constructor documentation describes **pitch, yaw, roll**.
3. Passing the numbers in the wrong order made an intended **pitch** value become **roll**.
4. The Unreal compatibility layer was therefore changed to set **named rotation fields** instead of relying on their position. The mapping rule also checks the target's `rotator.semantic_fields` capability.

**What we learned:** Engine names or versions alone are not enough. CutSceneAI must check the actual behavior of the destination project.

## 5. What if an element cannot be transferred directly?

The system checks each element and chooses a supported approach:

- **Preserve:** Transfer it directly when the target supports the same meaning.
- **Convert:** Change the format or values using a reliable conversion.
- **Retarget or reconstruct:** Adapt or recreate the behavior when direct transfer is not possible.
- **Block:** Clearly report the issue if a reliable transfer cannot be established.

Every decision should have an explanation and evidence. **Unsupported elements must never be silently ignored or guessed.** Conflicting mapping rules are reported as errors.

## 6. How do we check whether it worked?

A generated Unreal cutscene is not automatically considered correct. CutSceneAI must **read the result back from Unreal** and compare it with the original Unity cutscene.

For Benchmark 001, the checks include timing, character and prop positions, camera movement and cuts, animation playback, audio, and events. Any mismatch helps identify a rule or adapter that needs to be corrected and tested again.

**The goal is measurable accuracy, not just visual similarity.**

## 7. What does v0.1 cover?

Version 0.1 establishes the basic project-profile format, adaptive mapping rules, recorded mapping decisions, and initial Unreal project-analysis support.

Benchmark 001 is still a **controlled Unity-to-Unreal experiment** using known assets and deterministic methods. It does **not** claim to automatically handle every engine version, character rig, visual effect, or project configuration, and it does not require generative AI for the basic transfer.

Future versions can extend the same approach to additional engine projects without hard-coding every possible engine-version combination.

## Conclusion

> **Project Intelligence identifies differences between the projects. Adaptive Mapping chooses how to transfer each element. Validation checks whether the resulting cutscene matches the original.**

### Technical reference (optional)

The supporting contracts and implementation are in:

- `packages/contracts/project/project-profile-v0.1.schema.json`
- `packages/contracts/csir/csir-adaptive-context-v0.1.schema.json`
- `packages/contracts/dictionary/adaptive-mapping-rules-v0.1.schema.json`
- `packages/contracts/dictionary/resolved-dictionary-v0.1.schema.json`
- `packages/contracts/dictionary/adaptive-rules-v0.1.json`
- `packages/readiness/adaptive_mapping.py`
- `integrations/unreal/project_intelligence.py`

See also `docs/benchmarks/BENCHMARK_001.md` and `docs/architecture/FOUNDATION_V0_1.md`.
