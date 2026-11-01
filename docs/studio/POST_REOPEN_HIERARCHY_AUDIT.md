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

## If an earlier Studio run reports two detached props

The Oct 31 Studio test found two direct Unity actor parents missing after
reopening Unreal: `MovingPropMesh` and `PROP_PARENTED`, both `PARENT_MISMATCH:
... -> None`. The source pipeline previously prepared a mapping without
`enable_cinetwin_hierarchy`, so Unreal built new actors but did not apply the
existing source-derived attachment routine.

The Studio automatic-preparation path now sets this policy on each **fresh,
copied mapping**; it does not alter the original mapping or an existing saved
Level Sequence. Source direct children with only a synthetic static world-pose
track inherit the parent. Independently animated children require verified
source CineTwin samples so the system can build parent-local animation rather
than double-transforming under a moving parent. If that proof is unavailable,
the new candidate is blocked **before editor mutation**.

To verify the fix in the real editor, create a distinct empty target level in
a backed-up Unreal staging project, reconnect that level in Studio, and
prepare a **new** candidate. Approve the import once, Save All, close and reopen
Unreal, then run the read-only hierarchy audit above. Two correctly converted
source actor links should now be observable, but **do not record PASS until
the real report proves it**. The old target must not be overwritten.

The eight unmapped source-parent relationships seen in the original report
are separately tracked under issue #68. Source intermediate helper, component,
rig and director records need complete parent-chain classification before the
system creates new proxies or attaches actors across them.
