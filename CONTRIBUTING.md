# Contributing to CutSceneAI

CutSceneAI is research software with frozen experimental evidence and a currently unmerged transfer-backend feature stack. Contributions must preserve reproducibility.

## Before changing code

1. Read [Repository Guide](docs/REPOSITORY_GUIDE.md), [Issues and Milestones](docs/ISSUES_AND_MILESTONES.md), and the relevant module README.
2. Select the **correct base branch**. `main` is stable but does not yet contain draft PRs #49–#52. For changes depending on transfer-backend code, branch from `feature/transfer-backend-best-effort-v0.1`; never duplicate an earlier branch's changes in a new PR against `main`.
3. Use a new `feature/`, `fix/`, or `chore/` branch, scoped to one concern.
4. Before code changes, identify the corresponding tests and affected engine boundary.

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
