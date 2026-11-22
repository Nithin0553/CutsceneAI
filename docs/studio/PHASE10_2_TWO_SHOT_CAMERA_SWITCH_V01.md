# Phase 10.2 — Guarded Two-Shot Camera Switch Repair (v0.1)

**Software implementation only.** Source/target evidence and Unreal APIs are exercised by synthetic fixtures. There has been **no actual Unity/Unreal Editor execution, save/reopen or rendered shot parity test**.

## Supported cinematic shape

Exactly two original source-authored, **frame-aligned** camera-cut sections,
bound to two **different** uniquely mapped cameras and two non-muted source
`camera.cut` tracks, must form a **single shared switch frame**. The saved
Unreal sequence must already contain the same two camera bindings, in the
same order, with the same outer start and end frames. Only the switch boundary
may differ, by **1–8 whole display-rate frames**. One or more gaps, overlaps,
subframe cuts, multiple camera-cut master tracks, extra shots, nested shots,
rewired bindings, unknown time-warp owners and ambiguous source track
ownership all stop without a native edit.

This is an intentionally narrow expansion of the earlier
`restore_single_camera_cut_timing` adapter. It cannot insert/delete/reorder
shots, repair arbitrary timelines, blend cameras, retarget a camera, repair
animated lenses or transform channels, or assert that the image rendered
before/after the switch is visually equivalent.

## Source and provenance gate

`packages/studio/studio_two_shot_cut_evidence.py` rebuilds the candidate from:

- the original prepared CSIR, mapping, transfer plan and immutable candidate
  identity; the independently reproduced Element 7 readback, original source
  capture and actual **separately reopened** Unreal target observation;
- bounded Element 8 evidence, with no exhausted remeasurement budget or
  measured-regression/no-progress stop; completed native builder and separately
  reopened editor observation;
- exact `sampling-plan.json.camera_cuts` source section IDs, camera entity IDs,
  integer frame alignment, two source track IDs, source camera names and
  exact target mapped labels;
- `target-behavior.json.camera_cut_sections` with native Sequencer camera
  binding provenance `NATIVE_SEQUENCE_CAMERA_BINDING_ID`; native lens must
  separately pass and the camera-cut timing comparison must fail;
- all four outer and shared edges from source/native readbacks; source
  sections must be `[start, switch), [switch, end)` and native sections must be
  `[start, wrong_switch), [wrong_switch, end)`;
- no model-provided camera ID, section ID, frame number or transform.

The resulting `two_shot_cut_repair_sha256` binds the exact report,
source-to-target camera labels, source section IDs, native/expected boundary
pairs and Element 7/8 proof digests. **This hash is a source-bound candidate,
not native mutation permission.**

The agent's deterministic intent router requires an explicit nonnegated user
request for camera cut/switch timing, the exact proof, a generated target and
remaining repair budget. Requests mentioning lenses, camera animation,
rotation, blending, inserting/removing shots, retargeting, multiple/all scenes,
nested sequences or three shots are not eligible. The LLM can only select the
registered `restore_two_shot_camera_switch` strategy and return a reason.
It never supplies cut values. The agent writes one durable request with
current feedback ID and the report SHA, then the existing native executor
uses a **write-ahead claim** before invoking the native writer; interrupted
claims cannot be replayed automatically.

## Native mutation and rollback

`integrations/unreal/studio_two_shot_cut_repair.py` independently rechecks:

1. Exact current Studio job, native sequence and project/level via shared
   executor, explicit current feedback and the **recomputed** proof digest.
2. Both original camera actors are **newly spawned and exact native objects**.
   Automatic scene staging now records each camera's native UObject path
   in the actor creation receipt when supported. A missing path blocks
   this optional repair but not ordinary scene staging. Changed/reused
   actor labels alone cannot substitute for matching the original path.
3. One native camera-cut master track, two section UObject instances, bounded
   master/bound Sequencer track inventory, no nested shot/subsequence/time
   dilation/warp control. No track creation/removal or camera binding setter.
4. **Each native section camera-binding GUID resolves to the exact newly
   staged CineCamera UObject path**, not merely an actor with the same label.
   The active world, binding ID, label, object path and native class must all
   match the original source-created actor; missing API denies the repair.
5. Native section ranges and actual camera-binding IDs re-read through
   `cinetwin_camera_cuts.inspect` must match the original exact observation.

For a switch moving **earlier**, the first shot is shortened before the
second starts earlier. For a switch moving **later**, the second starts later
before the first is extended. This creates at most a brief in-memory gap,
not an overlapping cut. Both sections are then re-read with their **original
camera bindings**, and the source-aligned boundary must match exactly.

Only then does Unreal `EditorAssetLibrary.save_loaded_asset(sequence)` run.
If any setter, native observation or save fails, the original two ranges
are restored and reobserved; an incomplete rollback explicitly requires
manual editor inspection. A failed or interrupted disk write is **not**
proof of persisted rollback across an editor restart.

Successful receipt status:
`TWO_SHOT_SWITCH_SAVED_REOPENED_CINETWIN_PENDING`.

The receipt expressly keeps `persistence_after_editor_restart_verified`,
`cinetwin_reopened_time_grid_verified_after_repair`,
`rendered_camera_switching_verified` and
`full_cutscene_fidelity_verified` **false**. Native section readback does
not establish independently rendered cinematic continuity.

## Synthetic acceptance

The software-only suite exercises source/native independent evidence, two
camera ID/track ID/section ID attribution, wrong bind labels, altered outer
edge, gap/overlap/subframe, drift exceeding eight frames, invalid source
tracks, wrong target camera, stale user feedback and stale hashed proof,
unexpected changed actor object path, type, duplicated actor labels, changed
native binding/section, native nested/subsequence/time-warp owners, forward
and backward switch correction order, setter mutation then exception,
second setter failure, bad post-edit readback and save refusal/interruption.
The LangGraph path is checked to send **proof SHA only**, never an
agent-authored frame value.

All existing one-shot repair behavior remains unchanged.

## Remaining Phase 10.2 work

General multi-cut continuity, overlapping/weighted sections, camera
blend/ease, animated lens and camera transforms, per-shot rendered fidelity
and related audio/event synchronization remain **unsupported or unverified**.
They require separate source/target contracts and real engine acceptance
after the Studio software phase.

See [Phase 10.2 static character yaw](PHASE10_2_GUARDED_STATIC_CHARACTER_YAW_V01.md)
and [Studio release acceptance](RELEASE_ACCEPTANCE.md).
