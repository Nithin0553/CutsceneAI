# GitHub Branch Audit

**Audit snapshot:** 2026-10-27. This is a **review list**, not authorization to delete active work. Git branch cleanup is independent of code-file cleanup: deleting an already-merged branch removes its remote name, not the commits incorporated into `main`.

## Inventory

| Category | Count | Treatment |
| --- | ---: | --- |
| Default branch `main` | 1 | **Protect / keep** |
| Merged historical PR head branches | 47 | **Candidates for deletion after owner/reliance check** |
| Open and unmerged PR heads | 5 | **Keep** until resolved |
| Older foundation aliases with no PR as their head | 5 | **Review** identical commits and any consumers before deletion |
| This isolated cleanup branch | 1 | Keep until review and merge |
| **Total remote branches at audit** | **59** | No remote branch deleted during this audit |

The five open unmerged heads are:

- [#6](https://github.com/Nithin0553/CutsceneAI/pull/6) — `feature/unreal-benchmark001-import-v0.1` (legacy PR; decide whether superseded, never silently close).
- [#49](https://github.com/Nithin0553/CutsceneAI/pull/49) — `feature/benchmark002-parity-corrections-v0.1`.
- [#50](https://github.com/Nithin0553/CutsceneAI/pull/50) — `feature/continual-mapping-learning-v0.1` (base: #49 branch).
- [#51](https://github.com/Nithin0553/CutsceneAI/pull/51) — `feature/studio-dataset-framework-v0.1` (base: #50 branch).
- [#52](https://github.com/Nithin0553/CutsceneAI/pull/52) — `feature/transfer-backend-best-effort-v0.1` (base: #51 branch).

## Foundation aliases for manual review

`foundation/v0.1-ci`, `foundation/v0.1-clean`, `foundation/v0.1-final`, `foundation/v0.1-pr`, and `foundation/v0.1-review` pointed to the **same commit** (`21881b02` prefix) when audited. Their distinct names can matter to local worktrees or automation; none is deleted automatically.

## Proposed safe remote cleanup

1. Merge and validate this documentation PR into its feature base **only after review**.
2. Review PR #6 and decide whether its content is present on `main` or superseded; close only with a written explanation.
3. Review and merge draft PRs **#49 → #50 → #51 → #52** in dependency order after accepted editor experiments and branch CI.
4. On GitHub's **Branches** page, filter to *merged* branches, inspect references, and delete only historical merged heads with no external dependencies.
5. Check local worktrees: `git worktree list`; keep an archive tag or immutable SHA where an experiment depends on a branch tip.
6. Run `git fetch --prune` in local clones after approved remote deletions.

Do **not** run `git push origin --delete` on every branch except `main`; that would destroy navigation to unmerged research and ongoing experiment work. Automated deletion is deliberately excluded from this hygiene PR. The GitHub connector for this session does not expose a safe remote-ref deletion operation.
