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


## Re-audit — November 20, 2026 (current release-candidate branch)

This is an evidence-bound cleanup inventory, **not** a record of remote
branch deletions. The live GitHub REST inventory returned **101 remote branches**
and **15 open PRs**. All open PR head and base refs, `main`,
`feature/studio-e2e-release-candidate-v0.1`, and the historical
`backup/main-before-studio-consolidation-20261109` must remain intact.

### Confirmed same-tip redundant aliases

All five refs below point to **the exact same immutable commit**:
`21881b02399752f26848cd1f57d26cd3548ec0f4`.

| Branch | Disposition |
| --- | --- |
| `foundation/v0.1-final` | **Retain** as the single historical foundation ref |
| `foundation/v0.1-ci` | Redundant name — deletion candidate |
| `foundation/v0.1-clean` | Redundant name — deletion candidate |
| `foundation/v0.1-pr` | Redundant name — deletion candidate |
| `foundation/v0.1-review` | Redundant name — deletion candidate |

None of these five branch names is an open PR head or base as of this audit.
The shared commit has **16 commits not contained in the history of `main` or
the active release candidate** (compare reports both branches as diverged);
therefore **retain `foundation/v0.1-final`**. This is not permission to
delete all historical foundation references.

Before deleting any redundant alias on a local machine, confirm that no
local worktree, external CI or deployment configuration refers to that
specific branch name, and recheck that its remote SHA still equals the
recorded value. If any name has moved, **do not delete it**.

The connected GitHub API does not expose remote branch deletion; these
candidate branches **have not been deleted**. An owner with push rights can
use the reviewed commands below after checking local consumers:

```powershell
git fetch origin
$expected = "21881b02399752f26848cd1f57d26cd3548ec0f4"
$redundant = @(
  "foundation/v0.1-ci"
  "foundation/v0.1-clean"
  "foundation/v0.1-pr"
  "foundation/v0.1-review"
)
foreach ($name in $redundant) {
  $line = @(git ls-remote --heads origin "refs/heads/$name")
  if ($LASTEXITCODE -ne 0 -or $line.Count -ne 1) {
    throw "Cannot verify remote branch $name; no deletion attempted."
  }
  $sha = ($line[0] -split "\s+")[0]
  if ($sha -ne $expected) {
    throw "Remote branch $name moved to $sha; no deletion attempted."
  }
}
# Only after the exact SHA and consumer checks above:
git push origin --delete foundation/v0.1-ci foundation/v0.1-clean foundation/v0.1-pr foundation/v0.1-review
git fetch --prune origin
```

The checkout tree at the active release-candidate head had **zero tracked
generated-artifact matches** under the repository-hygiene scan (Python
caches, `.venv`, `node_modules`, Unity/Unreal caches, temporary logs, and
generated movie/asset files). Do not delete source documents, frozen
benchmark records, contract dictionaries, adapters, or research tests
simply because they look old.

The user's `CutsceneAI-Acceptance/` test snapshot and generated Unity
`.meta` files were **untracked local files**, not GitHub history. The
root acceptance directory is now ignored to prevent accidentally committing
private evidence; neither that directory nor the `.meta` files were deleted.
Unity `.meta` files can encode GUID relationships, so they were not
globally ignored or removed without a Unity package-consumer audit.
