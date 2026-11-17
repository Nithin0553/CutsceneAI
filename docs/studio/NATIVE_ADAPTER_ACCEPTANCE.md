# Unity and Unreal native adapter acceptance

Run each case on a workstation with the matching Unity Editor and Unreal 5.8
installed. Use a backed-up Unity project and disposable Unreal staging level.
Keep the scene, editor versions, Git commit, Unity compiler log and evidence
paths with each result.

1. Install `integrations/unity/com.cutsceneai.extractor` from this checkout
   through Unity Package Manager. Wait for compilation and record the Unity
   Editor log and any errors from the Console. Export the selected Timeline
   and its source feature census using **Tools → CutsceneAI**.
2. Generate the CineTwin sampling plan using
   `python tools/cinetwin.py plan SOURCE.csir.json SOURCE.cinetwin.sampling-plan.json`.
   In the Unity test copy, enter Play Mode and use **Tools → CutsceneAI → CineTwin →
   Capture Selected Timeline Behavior (Play Mode)**. Validate the saved capture
   with `python tools/cinetwin.py verify SOURCE.cinetwin.sampling-plan.json SOURCE.cinetwin.behavior.json`.
3. Connect Studio with that CSIR, census and capture. Start an automatic transfer
   into a new staging map with a companion loaded from the same checkout. Save
   the generated map, sequence and assets. Record the candidate and job ID.
4. Close Unreal and open the same project and saved map in a fresh Unreal Editor.
   Run the commands below in its Python console. Keep the reopened level and
   sequence stable while CineTwin samples each source timestamp over real editor
   ticks. The console prints the output path when capture completes.

```python
import sys
sys.path.insert(0, r"D:/CutsceneAI/integrations/unreal")
import studio_native_acceptance
print(studio_native_acceptance.start())
```

Replace the path with this checkout's location. The command uses the active
Studio job. Use `start(job_id="<32-character-job-id>")` for an earlier candidate.
`persistence.json` records the observed saved packages and native properties.
`target-behavior.json` and `comparison.json` preserve the independent Unreal
samples, measured joint/actor differences and exact source and report hashes.
The command verifies the prepared candidate and requires another Unreal process.

| Scope | Evidence to review |
| --- | --- |
| Skeletal motion | Bone correspondence, per-joint peak position error and timestamp, actor root trajectory and facing. Include overlapping clips and a held-out rig. [Retargeting setup](IK_RETARGETING.md) |
| Static primitive collision | Native hit/miss and distance on Box, Sphere and Capsule, reported separately from geometry. Include a trigger and filtered collision as unsupported behavior cases. [Collider cases](NATIVE_COLLIDER_GEOMETRY.md) |
| Constant PBR | Saved material asset, parameter defaults and slot assignment. Compare controlled rendered frames separately. [Material cases](CONSTANT_PBR_MATERIALS.md) |
| Registered package | Installed package/version and source identity, native binding and channel, and measured behavior for the package. Run a second unknown package and preserve its diagnostic. [Adapter registration](../architecture/CED_ADAPTER_EXECUTION.md) |

Include an isolated case, a combined cutscene, a held-out source project and a
deliberate unsupported case. `STRUCTURE_AND_MEASURED_MOTION_WITHIN_TOLERANCE`
covers the saved structure and observed motion in one candidate. Audio output,
rendered fidelity, arbitrary procedural VFX, dynamic physics and middleware
runtime behavior have separate release requirements. See
[release acceptance](RELEASE_ACCEPTANCE.md).
