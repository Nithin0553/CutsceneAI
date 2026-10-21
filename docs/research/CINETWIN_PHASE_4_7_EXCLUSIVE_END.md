# CineTwin Phase 4.7 — Explicit Unreal exclusive-end boundary diagnosis

## Observed evidence in Benchmark002

The staged Unreal hierarchy reconstruction was re-evaluated at all 298 source
sampling timestamps. The parented prop remained attached to the correct
parent, with a measured **maximum local offset error of 0 cm**.

The first verifier reported a **101.2033 cm** world-position discrepancy.
The user inspected every per-timestamp measurement:

- the only meaningful error was exactly **t = 12.0 seconds**;
- all observed times before 12 s differed by at most about **0.0001 cm**;
- the original key times at 0, 1, 4, 7, and 8 seconds all matched;
- parent and child had the same world error at t=12, while the
  parent-relative offset remained zero.

This is inconsistent with the earlier speculation that Unreal's interpolation
between keys was incorrect.

## Engine semantics

Epic's official UE5.8 documentation explicitly states that **Sequencer
playback start is inclusive and playback end is exclusive**:

https://dev.epicgames.com/documentation/en-us/unreal-engine/cinematic-workflow-tips-for-sequencer-in-unreal-engine

The 12-second source sampling plan includes the exact playback endpoint, but
a 12-second Unreal Sequencer sequence should be evaluated *only before*
12 seconds. Seeking to t=12 may return preanimated/editor-restored values.
That is a strong hypothesis for the exact-boundary discrepancy; we have not
proven which internal engine action produced the terminal target value.

## Boundary-aware validation policy

The pure-Python CineTwin hierarchy verifier now:

1. Uses source plan `timing.playback_end_seconds` and an explicit
   `target.engine=unreal` declaration to recognize the exclusive endpoint.
2. Preserves **all** raw per-timestamp measurements, including the apparent
   101.2033 cm error at t=12.
3. Reports active-range and endpoint metrics separately.
4. Returns `EXCLUSIVE_END_BOUNDARY_UNVERIFIED` when the active range matches
   but the excluded endpoint differs. This is **not a PASS** and the CLI uses a
   nonzero status, while no interior discrepancy is invented.
5. Continues to report `MISMATCH_DETECTED` if **any valid interior** sample
   exceeds tolerance, even if the endpoint also differs.
6. Does not apply special treatment to non-Unreal target engines or to
   observations without explicit playback timing.

For Benchmark002, the expected diagnostic from the user's current evidence is
297 active evaluated sample times, one excluded boundary observation at 12.0
seconds, and approximately zero active-range world/relative offset error.
The values must still come from the verifier output, not this prediction.

The hierarchy behavior has not been proven at the unreachable endpoint, nor
has the entire cinematic been proven equivalent. A future adapter must define
terminal-pose policy explicitly (freeze last active pose, include terminal
state outside playback, change playback duration, etc.) and verify it on a
staged target rather than silently extending the original sequence.

## Safe next run

After merging/pulling main, run the same read-only
`python tools/cinetwin.py hierarchy-verify` command with:

- source sampling plan,
- source Unity behavior capture,
- 298-sample Unreal tick-synchronized hierarchy capture,
- source hierarchy plan,
- a **new** output report filename.

This needs no Unreal rebuild, no saved level changes, and no source updates.
The verifier prints maximum raw errors, active-range errors, and endpoint
classification separately.
