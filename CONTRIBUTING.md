# Contributing to CutSceneAI

CutSceneAI is research software with frozen experimental evidence and a currently unmerged transfer-backend feature stack. Contributions must preserve reproducibility.

## Before changing code

1. Read [Repository Guide](docs/REPOSITORY_GUIDE.md), [Issues and Milestones](docs/ISSUES_AND_MILESTONES.md), and the relevant module README.
2. **Audit the live issues, open PRs and branch ancestry before every fix.** For Studio development, select the current integrated development base (as of Nov 9, 2026, PR #102 on `integrate/studio-issue-93`), not the older `main` or experimental transfer-backend branch. Do not overwrite newer CED/engine code by copying older PR files. Read the [mandatory Studio triage policy](docs/studio/ISSUE_PR_TRIAGE_POLICY.md) and verify the live GitHub state each time.
3. Use a new `feature/`, `fix/`, or `chore/` branch, scoped to one concern.
4. Before code changes, identify the corresponding tests, affected engine boundary, existing issue/PR and the evidence that the proposed correction will address the reported problem.

## Local checks

```powershell
python -m pip install pytest ruff jsonschema
python -m pytest -q
python -m ruff check tests
python tools/repo_check.py
```

CI performs Python tests, Ruff on tests, and repo-hygiene checks. Python mocks/static Unity tests **do not** prove a C# project compiles or a real Unreal sequence is correct.

## Pull-request checklist

- [ ] Change follows `packages/` vs `integrations/` boundaries.
- [ ] New functionality has relevant regression tests with generic scene names.
- [ ] Source CSIR, benchmark freezes, original Unity assets and existing Unreal targets remain untouched.
- [ ] No local `B:\`, `D:\` or other absolute private test paths are committed in **code or example configs** unless intentionally documented as an illustrative path.
- [ ] Generated captures, runtime receipts, target outputs, exported media or environment secrets are not committed.
- [ ] Engine mutation uses a backup, explicit target path, preflight and failure report.
- [ ] PR clearly distinguishes Python-only evidence from real Unity/Unreal runtime results.
- [ ] New docs are linked from [Documentation Index](docs/INDEX.md).
- [ ] No destructive branch or evidence removal without provenance review.

## Branch hygiene

- **Never delete** `main`, an active draft PR head/base, or `feature/unreal-benchmark001-import-v0.1` until PR #6 is resolved.
- Historical merged branch names may be deleted after verifying they were merged and no dependent branches/active worktrees use them; their commits remain in the main history.
- GitHub currently contains several historical `foundation/*` refs at identical commits; handle only after owner confirms no external automation depends on those refs.
- Review [Branch Audit](docs/BRANCH_AUDIT.md) rather than bulk-delete every non-main branch.

## Research policy

Failures, incomplete measurements and unsupported behaviors are valid findings. Never fabricate PASS results, assert arbitrary-cutscene support from synthetic tests, or silently replace source data to improve reported parity.

## Issue and pull-request completion

Before closing any issue or PR, verify its exact acceptance criteria and the
required Python/UI **and real-editor** evidence. Merge only completed,
nonconflicting PRs into their intended base; leave broader fidelity and
release issues open until independently measured acceptance. Keep historical
findings and linked receipts. Do not bulk-close active stacked PRs or delete
branches just to reduce the issue count.
