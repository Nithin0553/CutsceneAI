# Element 8 — Static CineCamera world-position repair (v0.1)

**Status:** software adapter and synthetic tests only. Not a real Unity/Unreal acceptance. Stacked on integration PR #149. Do not merge the older stacked PRs again.

## Narrow supported behavior

The new `restore_static_camera_position` adapter can correct one constant world-space placement offset of one **newly staged, source-mapped, unparented CineCamera** only when:

- the original Unity CSIR, source CineTwin capture, source-to-target mapping, compiled plan and reopened Unreal sample artifacts validate through Elements 7 and 8;
- every original Unity and native Unreal sampled camera position remains static within 0.1 cm, the source-minus-target offset is constant across frames, and the offset is over 2 cm but no larger than 500 cm;
- camera rotation agrees within 0.5 degrees at each sample, camera scale matches, the physical lens domain passed, and camera-cut timing is either PASS or NOT_APPLICABLE;
- Element 8 attributes **only** `WORLD_POSITION_OUTSIDE_TOLERANCE` to this exact source-camera occurrence, with no remeasurement regression/budget stop;
- a current user asks **only** to fix camera position/placement; mixing a lens, cut, animation, rotation, moving-camera or character request blocks repair;
- native Unreal rechecks the single newly staged camera receipt, exact generated Sequence, all binding and root tracks, unparented actor with no attached children, and live actor base position against the saved source-bound baseline.

The evidence layer converts canonical XYZ displacement to Unreal centimeters using the established inverse basis `(-Z, X, Y)`. Neither the model nor user feedback supplies native coordinates. The guarded editor setter checks its immediate actor-base readback and restores its old location when a write, verification or save fails. As elsewhere in Element 8, the request requires the durable no-replay claim and consumes the existing two-receipt budget.

## What this does **not** do

This is not a camera-animation retimer, arbitrary transform executor, rotation/facing fixer, skeletal retargeter, parented camera rig editor or visual-framing equivalence proof. No general automatic Unreal retries are added. Even a successful native placement save returns `CAMERA_STATIC_POSITION_SAVED_REOPENED_CINETWIN_PENDING`, with **persistence-after-restart, full-grid CineTwin, rendered composition and full cinematic fidelity marked false**.

## Acceptance before release

Run the source and target in real Unity/Unreal editors later; confirm that editor APIs exist, observe source/target captures from independent processes, execute one user-approved edit in a disposable staged level, test failed setter/save rollback, save and reopen in another Unreal Editor process, then verify camera position at every source time and compare rendered framing. Keep PR draft and results unverified until this is complete.

## Synthetic software coverage

`tests/studio/test_static_camera_position_repair.py` exercises independent camera evidence, intent restrictions, AI request redaction, once-only native proposal routing, stale evidence and native transform ownership denials, native property readback and rollback fixtures. The existing Elements 1–9 software CI continues to gate all other system contracts.
