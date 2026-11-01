# Studio — read-only Unity → Unreal hierarchy persistence audit

**Use after** the real Studio transfer, Save All, closing Unreal and reopening the same generated target level. The previous structural persistence audit must remain available. Do not regenerate or reimport the same candidate.

## Execute in Unreal's Python Console

```python
import sys, importlib
sys.path.insert(0, r"B:\Research\CutSceneAI\CutsceneAI\integrations\unreal")
import studio_hierarchy_audit as hierarchy
importlib.reload(hierarchy)
report = hierarchy.audit_latest()
```

Use your own repository path if different. The auditor reads the latest immutable Studio job and previously exported Unity CSIR, approved mapping, setup manifest and transfer plan. It checks the fingerprints before reading existing Unreal actor attachments. It writes a **new** `hierarchy-audit-<job-id>-<unique-id>.json` next to the prepared Studio candidate.

**No scene mutations:** it does not spawn, attach, move, import, save or delete actors or assets. It refuses a different editor project/level, changed source CSIR/mapping, conflicting actor label, unsafe mapping or output collision.

## What the statuses mean

- `PASS`: all mapped *direct* source parent-child actor links and source roots are observed in the reopened level; for direct links, component mobility and attachment socket readback are available and the socket is consistent with the supported no-socket policy. This is **structural**, not playback parity.
- `FAIL`: a known mapped actor is absent/duplicated, a direct parent link differs from source, a root is attached unexpectedly, or an unsupported socket is observed.
- `INCOMPLETE`: a source parent is only an unmapped intermediate hierarchy node, or Unreal's attachment/socket/component mobility readback is unavailable. It is not a successful transfer claim.

The output shows `direct_edges_verified/direct_edges_expected`, `root_actors_verified`, `unresolved_source_parents`, and explicit `errors` and `incomplete` details. A zero direct-edge count is **not** proof of successful attachment transfer when source parents are unresolved.

**Not verified by this test:** world-space transform/keyframe parity, time-varying attachment events, skeletal bone motion, constraint behavior, sockets with semantic mapping, visual effects, audio or camera composition. Source-target CineTwin motion sampling and independent playback are separate required evidence under #61 and #72. The historical setup receipt's absent `target_sequence` and `target_namespace` remain an independently tracked provenance limitation; do not edit prior receipts to fabricate identity.
