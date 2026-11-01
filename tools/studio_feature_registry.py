"""Extensible inventory and honest coverage model for cross-engine cinematics.

This is a capability taxonomy, NOT an implementation of all these features.
Native conversion is claimed only for features exercised by the verified
prepared transfer plan. Unknown CED types remain visible and unverified.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

# Keys are feature families, values are examples of engine-independent semantics
# and the most credible *potential* conversion route. New plugin types are
# preserved as unknowns, never silently dropped or declared compatible.
FAMILIES = {
    'timeline': ('timebase, frame rate, playback range, clips, sections, blending, easing, looping, time warp, sub-sequences, markers', 'canonicalize_time_and_sections'),
    'camera': ('static and animated cameras, cuts, blends, lens FOV, focal length, aperture, depth of field, focus pull, motion blur, camera shake, orthographic, stereo/VR', 'sequencer_camera_and_lens'),
    'spatial': ('local/world transforms, parent/child attachment, scale, pivots, constraints, path motion, splines, interpolation, orientation', 'transform_math_and_parenting'),
    'geometry': ('static/skinned meshes, topology, LOD, UVs, normals, tangents, vertex colors, instancing, morph targets, procedural meshes, Alembic geometry cache', 'fbx_gltf_usd_or_geometry_cache'),
    'skeletal': ('bones, hierarchy, bind pose, animation clips, root motion, additive poses, retargeting, IK, FK, Control Rig, ragdoll, layered animations', 'rig_mapping_and_motion_bake'),
    'facial': ('blendshapes, visemes, lipsync, facial joints, eyes, gaze, expressions, facial capture, head tracking', 'morph_and_bone_curve_retarget'),
    'materials': ('PBR surfaces, normal maps, texture samplers, shader graphs, UV animation, transparency, decals, emissive, clearcoat, refraction, tessellation', 'pbr_translation_or_texture_bake'),
    'lighting': ('directional, point, spot, area, volumetric lights, intensity, temperature, color, shadows, light linking, baked probes', 'sequencer_light_and_render_settings'),
    'environment': ('skyboxes, HDRI, exposure, fog, weather, atmosphere, day-night cycle, terrain, foliage, reflections, global illumination', 'environment_adapter_or_render_bake'),
    'fx': ('particles, Niagara/VFX Graph, trails, ribbons, smoke, fire, water, destruction, cloth, hair, fur, fluids, custom GPU simulation', 'fx_recreate_or_geometry_video_bake'),
    'audio': ('dialogue, ambience, music, effects, fades, envelopes, mixer routing, spatialization, attenuation, streaming, subtitles sync', 'audio_transcode_and_timeline'),
    'narrative': ('events, signals, branching, choices, quests, gameplay triggers, dialog state, cinematics-to-gameplay handoff, cutscene skipping', 'semantic_event_adapter'),
    'ui': ('HUD, subtitles, captions, titles, fonts, layouts, localization, accessibility overlays, interaction prompts', 'widgets_and_timed_text'),
    'simulation': ('rigid bodies, soft bodies, collision, physics triggers, destruction caches, cloth simulation, particles with runtime forces', 'cache_bake_or_runtime_equivalent'),
    'animation_other': ('material parameter animation, property tracks, activation and visibility, camera/actor constraints, object state, custom animated components', 'property_keyframe_adapter'),
    'media': ('video textures, image sequences, media players, compositing, chroma key, render layers, transitions', 'media_framework_adapter'),
    'custom': ('engine scripts, plugins, custom Playables, shaders/HLSL, Blueprints, proprietary assets, third-party middleware', 'plugin_contract_or_manual_semantic_mapping'),
    'delivery': ('render resolution, aspect ratio, color management, HDR, frame sampling, determinism, playback and persisted-readback verification', 'engine_profile_and_validation'),
}

# Only these *action names* are implemented by the current UE Sequence builder.
# Their presence does not mean playback equivalence, retargeting quality, etc.
CURRENT_BUILDER_ACTIONS = frozenset({
    'camera_setup', 'camera_cut', 'camera_fov', 'transform', 'skeletal_animation',
    'light_intensity', 'audio', 'marker', 'skeletal_world_root_lock',
})

# CED types may be extended without changing this registry.
FAMILY_FOR_PREFIX = {
    'entity.camera': 'camera', 'camera.': 'camera', 'entity.character': 'skeletal',
    'animation.': 'skeletal', 'entity.prop': 'geometry', 'transform.': 'spatial',
    'entity.light': 'lighting', 'light.': 'lighting', 'audio.': 'audio',
    'event.': 'narrative', 'material.': 'materials', 'texture.': 'materials',
    'particle.': 'fx', 'vfx.': 'fx', 'simulation.': 'simulation',
    'timeline.': 'timeline', 'sequence.': 'timeline', 'ui.': 'ui',
    'media.': 'media', 'animation.blendshape': 'facial',
}



# The newest CED covers specialized native groups beyond the historical
# cinematic categories above. Extend the read-only inventory automatically,
# preserving the original compatibility keys for old downstream consumers.
_CED_V2_PATH = Path(__file__).resolve().parents[1] / 'packages' / 'contracts' / 'dictionary' / 'cutscene-elements-v0.2.json'
if _CED_V2_PATH.is_file():
    _ced_v2 = json.loads(_CED_V2_PATH.read_text(encoding='utf-8'))
    for _family in _ced_v2.get('feature_families', []):
        FAMILIES.setdefault(
            _family['id'],
            (', '.join(_family['ced_domains']), 'needs_verified_engine_adapter'),
        )
    for _domain in _ced_v2.get('categories', {}):
        if not any(_domain == prefix.rstrip('.') or _domain.startswith(prefix)
                   for prefix in FAMILY_FOR_PREFIX):
            _preferred = next(
                (f['id'] for f in _ced_v2['feature_families']
                 if _domain in f['ced_domains']), 'custom',
            )
            FAMILY_FOR_PREFIX[_domain + '.'] = _preferred


def family_for(ced: str) -> str:
    matching = [(prefix, family) for prefix, family in FAMILY_FOR_PREFIX.items()
                if ced == prefix or ced.startswith(prefix)]
    if not matching:
        return 'custom'
    return max(matching, key=lambda pair: len(pair[0]))[1]


def audit(csir: dict, plan: dict | None = None) -> dict:
    """Inventory CED features and show which real UE actions are planned.

    A plan can be structurally prepared yet fail during engine import.
    'PLANNED_UNVERIFIED' deliberately does not claim success or parity.
    """
    rows = []
    for collection in ('entities', 'tracks'):
        for item in csir.get(collection, []):
            if not isinstance(item, dict):
                continue
            ced = str(item.get('ced_type') or 'unknown')
            family = family_for(ced)
            rows.append({'collection': collection, 'name': str(item.get('name') or ''),
                         'ced_type': ced, 'family': family,
                         'source_id': str(item.get('entity_id') or item.get('track_id') or '')})
            if collection == 'tracks':
                for section in item.get('sections', []):
                    if isinstance(section, dict) and section.get('ced_type'):
                        section_ced = str(section['ced_type'])
                        rows.append({'collection':'sections', 'name':str(item.get('name') or ''),
                                     'ced_type':section_ced,'family':family_for(section_ced),
                                     'source_id':str(section.get('section_id') or '')})
    actions = Counter(str(a.get('kind') or 'unknown') for a in (plan or {}).get('actions', [])
                      if isinstance(a, dict))
    unknown_actions = sorted(x for x in actions if x not in CURRENT_BUILDER_ACTIONS)
    family_counts = dict(sorted(Counter(row['family'] for row in rows).items()))
    return {
        'kind':'cutsceneai.studio.cinematic_feature_inventory',
        'schema_version':'0.1.0', 'source_engine': csir.get('source', {}).get('engine'),
        'source_cutscene_id':csir.get('cutscene_id'),
        'families': {key:{'examples':examples,'proposed_strategy':strategy,
                          'implementation_verified':False}
                     for key,(examples,strategy) in FAMILIES.items()},
        'source_inventory':rows, 'family_counts':family_counts,
        'planned_engine_actions':dict(sorted(actions.items())),
        'unimplemented_action_kinds':unknown_actions,
        'action_support':'PLANNED_UNVERIFIED' if plan is not None else 'NOT_EVALUATED',
        'complete_cutscene_fidelity_verified':False,
        'limitations':['The inventory describes known categories; vendor and custom types remain open-ended.',
                       'Planned actions do not prove saved Sequencer readback, rendered pixels or behavior parity.',
                       'Feature coverage requires independent per-type verification; do not infer it from a working sequence.'],
    }


def audit_files(csir_path: str | Path, plan_path: str | Path | None = None) -> dict:
    csir = json.loads(Path(csir_path).read_text(encoding='utf-8-sig'))
    plan = json.loads(Path(plan_path).read_text(encoding='utf-8-sig')) if plan_path else None
    return audit(csir, plan)
