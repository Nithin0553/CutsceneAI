# Studio transfer handoff: safe CLI-first vertical slice

This command **reuses** the existing best-effort planner and CED preflight. It does not invoke Unity or Unreal and does not claim successful conversion, automatically import assets or promote case memory. It is the reproducible handoff between authored source cutscene data and the existing audited Unreal editor generator.

Run from repository root:

```powershell
python tools/studio_transfer.py prepare --csir "C:\path\scene.csir.json" --mapping "C:\path\target_mapping.json" --out "C:\path\new_session_v1"
python tools/studio_transfer.py verify --out "C:\path\new_session_v1"
```

Optional `--capture SOURCE_CINETWIN.json` accepts only a source capture independently verified by the existing planner; `--target-project` binds the declared target path; `--case-store` adds held-out-project verified mapping **proposals only**, without modifying the transfer plan. Use `--strict-ced` to fail closed when CED preflight contains partial or unresolved elements.

The new directory contains `session.json`, `transfer-plan.json`, `coverage-report.json`, `evidence.json` and `suggestions.json`. The session records source and artifact SHA-256 hashes, CED status, per-track coverage, explicitly unexecuted engine flags and no learning promotion. Existing directories are never overwritten. `verify` rechecks source bytes and recomputes the existing signed plan using the same CED/transfer backend, before any editor invocation.

For engine execution, **use the current audited Unreal `build_prepared_files()` workflow**, after editor-side target-project/asset/actor preflight; these artifacts are intended for that workflow. This CLI does not yet run the editor or create assets. A new sequence asset path is mandatory. A passing CLI verification means *plan authenticity only*, not editable generation or CineTwin behavioral fidelity.

Research boundary: verified mapping case retrieval is not learned-strategy application and is not model training. Automatic supported-format import, independently verified target results, strategy promotion, and held-out measurements remain open under #80.
