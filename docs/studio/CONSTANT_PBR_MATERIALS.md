# Constant PBR material transfer

The extractor captures the authored metallic workflow of untextured Unity
Standard and URP Lit materials in linear-color projects. The automatic
manifest checks the shader asset identity, Unity material GUID, file hash,
renderer identity, and slot index before staging. Native Unreal materials
carry editable base color, metallic, roughness, emission, double-sided state,
and opaque or constant alpha-mask settings. The planner maps Unity
smoothness to `1 - smoothness` for Unreal roughness.

Matching existing texture imports continue through the albedo path. Texture
maps and modulation, translucency, material animation, and arbitrary shader
graphs require distinct adapters. The manifest reports unresolved shader and
material features for review.

## Real-editor acceptance

1. Create a scene in a backed-up Unity project with a Standard or URP Lit
   renderer using a unique material slot. Pick an untextured opaque material
   with distinct base color, metallic and smoothness values. Add a second
   untextured material with alpha clipping. Save and export the selected
   Timeline and census.
2. Prepare a Studio transfer in a disposable Unreal target and inspect
   `source_pbr_actor_candidates` for both source IDs and expected values.
   Generate and save, then close and reopen the exact Unreal level in a new
   Editor process.
3. Run the persistence audit and check `material_parameters` for the saved
   package, exact slot and parameter defaults. Render the same matched
   frames in both engines under a controlled camera, exposure and lighting
   setup. Record rendered-image differences separately.
4. Repeat with a custom shader or a stale material snapshot and verify that
   the manifest identifies the unsupported or changed input.

Unity documents the source shader properties and color conversion.
[Unity URP Lit properties](https://docs.unity.com/en-us/engine/6000.7/manual/materials-and-shaders/built-in/shaders-in-universalrp/reference/lit-shader)
· [Unity shader color values](https://docs.unity.com/en-us/engine/6000.6/manual/materials-and-shaders/shaders/writing-custom/shader-writing/writing-shader-change-properties/sl-properties-in-programs)
