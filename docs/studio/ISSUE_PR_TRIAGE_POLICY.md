# CutSceneAI — required issue/PR triage before every conversion fix

This is the standing workflow for CutSceneAI Studio development and research.
Follow it for future warnings, incomplete conversions, benchmarks and release
gaps **before changing code or closing GitHub tracking**.

1. **Capture grounded evidence.** Record the exact branch/commit, source
   CSIR and source census identity, candidate/job ID, Unreal project and
   saved level, native receipts, diagnostic codes, CineTwin reports and
   current editor process. Screenshot counts alone are not enough to prove
   a specific conversion failed; do not request or expose API keys or private
   project assets unless technically essential.
2. **Audit live GitHub issues, PRs and branch ancestry.** Check current
   open/closed issues and PRs, link every finding to an existing accepted
   task first, compare the implementation against the active Studio branch,
   and identify whether an existing PR already provides the needed code.
   Distinguish "PR includes code" from "code is integrated" and from "native
   runtime behavior is verified". Avoid duplicate issue creation.
3. **Separate root causes from absent measurement.** "Generated but
   unverified", missing Unity CineTwin capture, unknown reference poses,
   missing native readback, and missing custom shader support have
   different remedies. Do not replace missing evidence with optimistic
   status labels or treat test skips as real-engine success.
4. **Prove the proposed fix can affect the observed finding.** Trace source
   exporter → census → CSIR → CED/adapter → staging manifest → Unreal
   native generation → independent readback → source/target comparison.
   Identify the exact failing contract before making a change.
5. **Change safely and validate.** Use a new branch/PR. Add a regression
   test for the reproduced failure and a negative test for malformed source
   identity or unsafe mutation. Run Python/UI CI and keep Unity/Unreal
   validation separate. Never change frozen benchmark data, source
   assets, the user's primary Unreal project, or issue acceptance criteria
   merely to make tests green.
6. **Retain truthful fidelity levels.** A valid source census proves
   source discovery, not Unreal parity. Native actor/asset generation proves
   structure, not editability for every source feature or matched-time
   behavior. A first-pass native readback is not independent process
   restart proof. Record partial approximations and source-dependent
   limitations.
7. **Clean up only completed tracked work.** Merge a fully tested,
   independently accepted, non-conflicting PR into its intended development
   base before marking that PR complete. Close an issue only when its
   acceptance requirements and evidence are met; link commits and native
   receipts. Leave unresolved broader issues OPEN. Do not bulk-close
   stacked research PRs merely because newer code resembles them; never
   delete branches or private source files without explicit authorization.
8. **Report exact remaining work.** For each diagnostic, show whether the
   remedy is implemented, tested in CI, tested in the real editors, and
   independently verified. When missing evidence cannot be generated
   inside GitHub CI, give the precise repeatable Unity/Unreal procedure.

## Benchmark002 November 9 audit — issue/PR correspondence

| Report finding | Root cause and existing work | Correct remedy | Closure condition |
| --- | --- | --- | --- |
| 0 unresolved census, 7 partial | PR #103 corrected source-evidence classification; merged into integration branch after user-observed export and green CI | Retain partial native feature warnings until target adapters exist | PR #103 merged; Issue #94 remains open for full asset coverage |
| Native structure not verified | Generation worker only ran visual/CineTwin checks, though a strict persistence audit exists | Run independent native readback after generation, separately preserve post-reopen test | #93/#101 remain open until actual editor acceptance |
| Hierarchy audit absent | Native source/target hierarchy auditor exists but wasn't called automatically | Run post-generation native hierarchy observation; record missing parent links | #96/#98 remain open until real parity |
| Missing DirectionalLight | `studio_auto_scene` always chose `PointLight` for any Unity light | Read `entity.metadata.light.light_type`, choose the corresponding native type; block unsupported | #97 remains open until source/target verified |
| Missing SkyLight / SkyAtmosphere | Target scene lacks those Unreal actors; source sky/ambient equivalence not measured | Report environment as INCOMPLETE unless source-requirement evidence proves a failure; capture Unity sky/ambient and validate rendered frames | #97/#98 remain open |
| 19 source entities not independently bound | Manifest counts all CSIR entities not bound directly to target actors, including possible parent/auxiliary entities | Inspect their exact CED categories and identity before asserting an import failure | #94/#96 remain open |
| Model/prop/material losses | Some sources have no unique rendered mesh; URP Lit material is outside safe project Assets scope | Source-backed model/material adapters and target verification; no file guessing | #94/#95/#97 remain open |
| CineTwin evidence missing | No matching Unity source behavior capture in the active job | Export the matching Unity CineTwin capture and repeat; no synthetic parity | #98 remains open |
| Audio targets unverified | UI cannot yet establish imported SoundWave and waveform timing | Check native audio assets, then compare source/target timing | #97/#98 remain open |
| Learning/held-out unverified | No approved cross-project evidence | Execute held-out and learning experiments | #100/#101 remain open |

These states describe the inspected code and user-provided Results report.
Actual runtime results of this new repair branch are **not yet known**.
