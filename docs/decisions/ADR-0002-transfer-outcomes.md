# ADR-0002: Explicit Transfer Outcomes

**Status:** Accepted

Every transferable Cutscene Element Dictionary (CED) element must end in exactly one outcome:

1. `EXACT`
2. `CONVERTED`
3. `RETARGETED`
4. `BAKED`
5. `RECONSTRUCTED`
6. `TARGET_MAPPED`
7. `BLOCKED`

`BLOCKED` is a handled state, not a silent failure.

Every result must retain provenance explaining why the outcome was selected.
