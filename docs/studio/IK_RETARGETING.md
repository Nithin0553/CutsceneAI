# Approved Unreal IK retargeting

Studio can import a Unity skeletal FBX and the exact FBX animation clips
identified by the source Timeline. An approved Unreal IK Retargeter can bake
those clips onto an existing target skeletal mesh. The generated Level Sequence
uses the resulting editable AnimSequences at the original mapped paths.

Author and review the source and target IK Rigs, chain mappings and poses in
Unreal first. Configure both preview meshes on the Retargeter. Retain the
original target mesh's materials. A fresh source FBX import must have the same
native bones, parents and local reference transforms as the approved source
preview mesh. Use a new destination and immutable Studio candidate for each run.

## Mapping

Add the following top-level fields to a copy of the Studio mapping. Connect
Studio using that mapping. Use the immutable Unity entity ID from the CSIR and
the exact source bone IDs from the CineTwin capture. The four fields in the
retarget profile are required. Use package paths without an object suffix.

```json
{
  "skeletal_retarget_profiles": {
    "<csir-character-entity-id>": {
      "source_fbx_sha256": "<lowercase-sha256-of-the-exported-renderer-fbx>",
      "source_mesh_path": "/Game/Rigs/UnitySourcePreview",
      "target_mesh_path": "/Game/Rigs/TargetCharacter",
      "retargeter_path": "/Game/Rigs/RTG_UnityToTarget"
    }
  },
  "skeletal_bone_maps": {
    "<csir-character-entity-id>": {
      "<unity-source-bone-id>": "pelvis",
      "<another-unity-source-bone-id>": "spine_01"
    }
  }
}
```

Include every captured source bone once in the comparison map. The comparator
uses exact, unique native names if no explicit map is supplied. Missing,
ambiguous or inconsistent parent relationships keep the joint comparison
incomplete. Each mapped joint has a peak world-position error and timestamp.
Different character proportions can produce a real world-position difference.
This metric leaves bone orientations, skin deformation and facial curves
unverified.

The native staging receipt records the newly imported source clips, the
retargeted clip paths and their exact target skeleton. A fresh process checks
the saved clip/mesh packages, the assigned mesh and the animation section
references on that actor's native Sequencer binding. The
retargeter, approved meshes and unrelated assets are inputs; new assets go to
their planned empty paths. Rejected source reference poses leave a staging
receipt for the partial candidate.

Run the [native acceptance procedure](NATIVE_ADAPTER_ACCEPTANCE.md) for
each rig. Include walking, stopping, turning, waving, overlapping clips, a
held-out rig, and a mismatched reference pose. Verify root motion, facing,
timing and joint errors in the saved result. Remaining research tasks include
automatic chain calibration, arbitrary constraints, layers/blending semantics,
and motion baking from unsupported Unity rigs.

[Unreal IK Retargeter Python guide](https://dev.epicgames.com/documentation/en-us/unreal-engine/using-python-to-create-and-edit-ik-retargeter-assets-in-unreal-engine)
