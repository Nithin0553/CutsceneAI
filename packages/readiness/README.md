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

## Adaptive project-aware resolution

Readiness is evaluated against the resolved source/target mapping context, not against engine names alone.

Before readiness, each adapter emits a Project Intelligence Profile, source CSIR is accompanied by source semantic observations, and adaptive rules resolve every required CED element to RESOLVED or BLOCKED.

A missing capability or required observation must become an explicit readiness finding. The advisor must not invent an engine default when the project can be probed.
