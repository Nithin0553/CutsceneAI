# CutSceneAI coding-agent instructions

## Mandatory first step for EVERY bug, warning, transfer or fidelity task

1. Read [Issue/PR triage policy](docs/studio/ISSUE_PR_TRIAGE_POLICY.md).
2. Inspect the LIVE GitHub open issues, PRs, base/head branches and current
   relevant code **before** proposing or implementing any fix.
3. Map every reported diagnostic to existing issue(s), PR(s), source evidence,
   and actual root cause. Do not assume a PR title means its fix has shipped.
4. Determine whether the proposed code would directly resolve the observed
   behavior; distinguish source capture, native generation, native readback,
   independent CineTwin fidelity, and release certification.
5. Add source-bound tests and safety guardrails; compare results on exactly
   the same cutscene, engine projects and time base where possible.
6. Do not hide errors, change acceptance gates to report fake PASS, replace
   frozen benchmark evidence, assume visual parity from structural success,
   or execute LLM-generated arbitrary Unreal code.
7. Keep incomplete issues OPEN. Merge PRs only when their own acceptance
   evidence is complete, and close only after verified integration. Preserve
   old history and dependent branches. Never delete private files/branches
   or overwrite Unity/Unreal project assets to tidy the tracker.
8. For each result report: implemented versus verified, CI outcomes,
   real-engine evidence, still-open issues, PR disposition and next steps.

Current Studio integration PR is #102; PR #103 was merged into its integration
base after the user's November 9 source census acceptance. Issue #93 and
remaining fidelity/release issues are not thereby complete.

Use `docs/studio/ISSUE_PR_TRIAGE_POLICY.md` as the detailed process. This
instruction applies to future CutSceneAI Studio and repository work.
