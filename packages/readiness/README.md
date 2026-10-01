# Transfer Readiness

The readiness subsystem compares source-cutscene requirements against target-project capabilities before generation.

Each finding must include:

- issue ID
- affected CED element(s)
- severity: `CRITICAL | RECOMMENDED | OPTIONAL`
- evidence
- transfer risk
- recommended target-project change
- expected benefit
- target engine/version
- step-by-step resolution guide
- verification steps
- whether a safe automatic fix exists
- re-analysis check

The readiness advisor must never modify the source project.
