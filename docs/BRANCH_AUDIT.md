# GitHub Branch Audit

**Audit snapshot:** 2026-11-17 · **Repository:** `Nithin0553/CutsceneAI`

This document records review and safe cleanup decisions. It is **not** authorization to delete arbitrary branches or experiment artifacts.

## Live inventory at review

- `main`: consolidated Studio baseline at `5ea7a20401cc7cf6f7ae674973ea7811ffde2909` (merged [PR #112](https://github.com/Nithin0553/CutsceneAI/pull/112)).
- **88 remote branch refs** were visible to the GitHub connector at the snapshot. No remote branches were deleted in this cleanup.
- **4 open PRs after triage:** [#6](https://github.com/Nithin0553/CutsceneAI/pull/6), [#90](https://github.com/Nithin0553/CutsceneAI/pull/90), [#113](https://github.com/Nithin0553/CutsceneAI/pull/113), [#114](https://github.com/Nithin0553/CutsceneAI/pull/114).
- **8 open substantive issues:** #94–#101; all still require independent acceptance evidence.

## PR cleanup performed on November 17

The exact heads of **25 historical open draft PRs** were verified as ancestors of the final PR #112 integration head `b0d1e522ce31f3ec7635a3d096cbccf1a8277b54`. These were closed as **superseded, not individually merged**:

`#49–#52, #75–#79, #81–#83, #87–#89, #91–#92, #104–#111`.

Their PR comments explain the disposition. Their branches, commits and discussion history remain accessible; incomplete scientific scope is still tracked in #94–#101.

## Refs to retain pending explicit audit

- `main` — canonical code; never delete.
- `backup/main-before-studio-consolidation-20261109` — retained rollback reference for the large squash integration.
- `fix/studio-unbound-scene-renderers-v0.1` — active draft PR #113, pending Unity/Unreal acceptance.
- `feature/source-component-capability-contract-v0.1` — active draft PR #114, stacked on #113; contains source-capture changes not yet native adapters.
- `feature/unreal-benchmark001-import-v0.1` — open legacy PR #6; its exact head has divergent commits from integration and must be evaluated individually.
- `fix/studio-source-census-and-mapping` — open legacy PR #90; its exact head also has diverged commits that need individual review.

Do not delete other remote refs just because their related draft PR was administratively closed. Confirm that source experiments, local worktrees and any unpublished code do not depend on them. The previously recorded five foundation aliases need SHA and consumer re-verification before removal.

## Remote branch deletion gate

The connected GitHub actions support branch inspection and PR closure but **do not expose remote-ref deletion**. No direct branch deletion was attempted. Before later pruning candidates, record exact tip SHAs, verify needed commits are retained, inspect active worktrees and dependencies, preserve research rollback refs, and delete only the explicitly approved redundant remote names. Avoid `git push origin --delete` against all branches indiscriminately.

When approved remote deletions have been completed in GitHub, local clones can run `git fetch --prune` to discard stale remote-tracking references.
