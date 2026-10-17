# CineTwin Phase 4.3 — Source-aware attachment planning

## Motivation

Benchmark002 motion-layer observations show the moving prop is animated through its Unreal actor while the parented prop does not move. More importantly, the parented prop reports `ACTOR_ATTACHMENT_DIFFERS_FROM_SOURCE`: a directly mapped source parent exists in the target mapping, but the Unreal child actor is not attached to that parent.

We should not fake child movement by writing duplicate world-space animation keys. The proper transferable concept is the **parent–child hierarchy**, followed by evaluated world-space verification.

Epic documents Unreal actor root-component attachment and the `KEEP_WORLD` attachment rule, which maintains the initial world transform when an attachment is formed:

- https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/Actor
- https://dev.epicgames.com/documentation/en-us/unreal-engine/API/Runtime/Engine/EAttachmentRule
- https://dev.epicgames.com/documentation/en-us/unreal-engine/components-in-unreal-engine

## Implemented in this phase

A pure-Python **attachment planner** computes which source parent–child links can be represented as target actor attachments without modifying any source or Unreal assets.

It uses CSIR `entity_id` and `parent_entity_id` as authoritative identities and looks up target actors using the existing mapping. It reports:

- `planned_actor_attachments`: mapped direct parent/child actor pairs;
- `unresolved_source_parents`: source parents that are not independently mapped as target actors;
- `mapped_source_roots`: mapped source objects without a parent;
- `KEEP_WORLD` as an intended attachment policy (preserves starting world transform).

It refuses invalid and cyclic hierarchies, missing parents, repeated source IDs, ambiguous mapped names or shared target actor labels. The planner does **not** bypass an unmapped intermediate parent: different game engines might model such a parent as a component or transform proxy, which must be resolved separately.

## Next local inspection

After CI passes and the branch is merged, run from VS Code PowerShell:

```powershell
cd B:\Research\CutsceneAI\CutsceneAI
git switch main
git pull origin main

python tools\cinetwin.py hierarchy `
"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002_Timeline-e6518af4.csir.json" `
"B:\Research\CutsceneAI\CutsceneAI\integrations\unreal\benchmark002_mapping.json" `
"D:\CutSceneAI - Studio\CutsceneAI_Benchmark001_Unity\CutSceneAI\Exports\Benchmark002_CineTwin_HierarchyPlan.json"
```

This will print a list of intended attachments without opening Unreal. No actor, map, animation, original Unity source, or existing sequence is changed.

## After verifying the dry run

Integrate generic hierarchy realization into the transfer builder, using `Actor.attach_to_actor(..., KEEP_WORLD, ..., weld_simulated_bodies=False)` and independent readback validation. Test it against a separate generated target / recoverable project copy before modifying the working benchmark level.

Animation root motion needs a separate correspondence and effective-world-motion evaluator. Motion-layer figures collected during a five-time probe do not establish pose parity or a valid root-motion correction.

Remaining coverage gaps include dynamic attachment events, socket parenting, unmapped transform proxies, component-only child objects, animated parents and explicit detach/reparent events.
