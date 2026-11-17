"""Conservative native Unreal albedo restoration on newly staged actors.

Only exact FBX material-slot names with source-backed Unity .mat/PNG GUIDs
qualify. Does not translate arbitrary Unity/URP shaders or prove render parity.
"""
from __future__ import annotations

import math


def _name(value):
    return str(value)


def _fallback(material):
    if material is None:
        return True
    try:
        path = str(material.get_path_name()).lower()
    except Exception:
        return False
    return ("/enginematerials/worldgridmaterial" in path
            or "/enginematerials/defaultmaterial" in path)


def _slots(component):
    """Return list of (slot name, index) from the *actual* imported mesh."""
    mesh = None
    for property_name in ("skeletal_mesh_asset", "static_mesh"):
        try:
            mesh = component.get_editor_property(property_name)
        except Exception:
            pass
        if mesh is not None:
            break
    if mesh is None:
        return []
    # SkeletalMesh exposes "materials", while StaticMesh exposes
    # "static_materials" (the inherited "materials" property is protected).
    # Probe both without changing the mesh or its original material slots.
    raw = None
    for property_name in ("materials", "static_materials"):
        try:
            raw = mesh.get_editor_property(property_name)
        except Exception:
            continue
        if raw is not None:
            break
    if raw is None:
        return []
    slots = []
    for index, item in enumerate(raw):
        try:
            slots.append((_name(item.get_editor_property("material_slot_name")), index))
        except Exception:
            continue
    return slots


def restore(api, actor, candidates, *, existing_assets=None):
    """Assign only unique source-backed exact slot matches to fallback slots.

    Returns explicit per-slot evidence; throws for native material construction
    failure so calling setup records partial mutations rather than false success.
    """
    by_name = {}
    for candidate in candidates:
        by_name.setdefault(candidate["slot_name"], []).append(candidate)
    results = []
    cache = existing_assets if existing_assets is not None else {}
    for klass in ("SkeletalMeshComponent", "StaticMeshComponent"):
        component_type = getattr(api, klass, None)
        if component_type is None or not hasattr(actor, "get_components_by_class"):
            continue
        for component in actor.get_components_by_class(component_type) or []:
            for name, index in _slots(component):
                matching = by_name.get(name, [])
                entry = {"slot_name": name, "index": index}
                if len(matching) != 1:
                    entry["status"] = "NO_UNIQUE_SOURCE_MATERIAL_MATCH"
                elif not _fallback(component.get_material(index)):
                    entry["status"] = "EXISTING_NONDEFAULT_PRESERVED"
                else:
                    item = matching[0]
                    path = item["target_material"]
                    if path not in cache:
                        if api.EditorAssetLibrary.does_asset_exist(path):
                            raise RuntimeError("Material destination already occupied: " + path)
                        texture = api.load_asset(item["target_texture"])
                        if texture is None or str(texture.get_class().get_name()) != "Texture2D":
                            raise RuntimeError("Imported source texture unavailable: " + item["target_texture"])
                        factory = api.MaterialFactoryNew()
                        asset_tools = api.AssetToolsHelpers.get_asset_tools()
                        folder, asset_name = path.rsplit("/", 1)
                        material = asset_tools.create_asset(asset_name, folder, api.Material, factory)
                        if material is None:
                            raise RuntimeError("Native MaterialFactoryNew failed: " + path)
                        # Creation may persist even if any subsequent step fails.
                        expression = api.MaterialEditingLibrary.create_material_expression(
                            material, api.MaterialExpressionTextureSample, -320, 0
                        )
                        if expression is None:
                            raise RuntimeError("TextureSample creation failed: " + path)
                        expression.set_editor_property("texture", texture)
                        api.MaterialEditingLibrary.connect_material_property(
                            expression, "RGB", api.MaterialProperty.MP_BASE_COLOR
                        )
                        api.MaterialEditingLibrary.recompile_material(material)
                        if not api.EditorAssetLibrary.save_loaded_asset(material):
                            raise RuntimeError("Unable to persist recovered material: " + path)
                        cache[path] = material
                    component.set_material(index, cache[path])
                    entry["status"] = "SOURCE_ALBEDO_ASSIGNED_RENDER_PARITY_UNVERIFIED"
                    entry["target_material"] = path
                    entry["source_material_sha256"] = item["source_material_sha256"]
                results.append(entry)
    return results


def preflight_constant_surfaces(api, candidates_by_actor):
    if not candidates_by_actor:
        return
    names = ("MaterialFactoryNew", "MaterialExpressionVectorParameter",
             "MaterialExpressionScalarParameter", "MaterialEditingLibrary", "LinearColor")
    if any(getattr(api, name, None) is None for name in names):
        raise RuntimeError("The Unreal editor does not expose constant PBR material APIs.")
    for group, entries in (
        ("BlendMode", ("BLEND_OPAQUE", "BLEND_MASKED")),
        ("MaterialProperty", ("MP_BASE_COLOR", "MP_EMISSIVE_COLOR", "MP_METALLIC",
                              "MP_ROUGHNESS", "MP_OPACITY_MASK")),
    ):
        if any(getattr(getattr(api, group, None), name, None) is None for name in entries):
            raise RuntimeError("The Unreal editor does not expose a required PBR material property.")


def _constant_slots(api, actor, item):
    matches = []
    for classname in ("SkeletalMeshComponent", "StaticMeshComponent"):
        cls = getattr(api, classname, None)
        if cls is None:
            continue
        for component in actor.get_components_by_class(cls) or []:
            matches.extend((component, index) for name, index in _slots(component)
                           if name == item["slot_name"])
    if len(matches) == 1 and matches[0][1] == item["slot_index"]:
        return matches[0]
    return None


def _constant_parameters(surface):
    yield "CSAI_BaseColor", "MP_BASE_COLOR", surface["base_color_linear"]
    yield "CSAI_Emission", "MP_EMISSIVE_COLOR", [*surface["emission_linear"], 1.0]
    yield "CSAI_Metallic", "MP_METALLIC", surface["metallic"]
    yield "CSAI_Roughness", "MP_ROUGHNESS", surface["roughness"]
    if surface["blend"] == "masked":
        yield "CSAI_OpacityMask", "MP_OPACITY_MASK", surface["base_color_linear"][3]


def _native_blend(api, surface):
    return (api.BlendMode.BLEND_MASKED if surface["blend"] == "masked"
            else api.BlendMode.BLEND_OPAQUE)


def _build_constant_material(api, item):
    path = item["target_material"]
    if api.EditorAssetLibrary.does_asset_exist(path):
        raise RuntimeError("Material destination already occupied: " + path)
    folder, name = path.rsplit("/", 1)
    asset_tools = api.AssetToolsHelpers.get_asset_tools()
    material = asset_tools.create_asset(name, folder, api.Material, api.MaterialFactoryNew())
    if material is None:
        raise RuntimeError("Unreal material creation failed: " + path)
    surface = item["pbr"]
    material.set_editor_property("blend_mode", _native_blend(api, surface))
    material.set_editor_property("two_sided", surface["two_sided"])
    if surface["blend"] == "masked":
        material.set_editor_property("opacity_mask_clip_value", surface["opacity_mask_clip"])
    library = api.MaterialEditingLibrary
    for index, (parameter, property_name, value) in enumerate(_constant_parameters(surface)):
        vector = isinstance(value, list)
        node_class = (api.MaterialExpressionVectorParameter if vector
                      else api.MaterialExpressionScalarParameter)
        node = library.create_material_expression(material, node_class, -300, index * 120)
        if node is None:
            raise RuntimeError("Cannot create material parameter " + parameter)
        node.set_editor_property("parameter_name", parameter)
        node.set_editor_property("default_value", api.LinearColor(*value) if vector else value)
        if not library.connect_material_property(node, "RGB" if vector else "",
                                                 getattr(api.MaterialProperty, property_name)):
            raise RuntimeError("Cannot connect material input " + property_name)
    library.recompile_material(material)
    if not api.EditorAssetLibrary.save_loaded_asset(material):
        raise RuntimeError("Cannot save constant PBR material: " + path)
    return material


def stage_constant_surfaces(api, actor, candidates, cache):
    """Assign constant materials to exact slots on freshly staged actors."""
    results = []
    for item in candidates:
        slot = _constant_slots(api, actor, item)
        status = "PBR_NATIVE_SLOT_IDENTITY_UNRESOLVED"
        if slot is not None:
            component, index = slot
            path = item["target_material"]
            if path not in cache:
                cache[path] = (item["pbr"], _build_constant_material(api, item))
            previous, material = cache[path]
            if previous != item["pbr"]:
                raise RuntimeError("Source material snapshot conflicts with staged material: " + path)
            component.set_material(index, material)
            status = "PBR_ASSIGNED_RENDER_PARITY_UNVERIFIED"
        results.append({"slot_name": item["slot_name"], "slot_index": item["slot_index"],
                        "target_material": item["target_material"], "status": status})
    return results


def inspect_constant_surfaces(api, actor, candidates):
    """Read actual saved slot materials and parameter defaults after reopening."""
    results = []
    for item in candidates:
        record = {"status": "INCOMPLETE", "slot_name": item["slot_name"],
                  "target_material": item["target_material"], "render_parity_verified": False}
        results.append(record)
        try:
            slot = _constant_slots(api, actor, item)
            if slot is None:
                continue
            component, index = slot
            material = component.get_material(index)
            if (material is None or str(material.get_class().get_name()) != "Material"
                    or str(material.get_path_name()).split(".")[0] != item["target_material"]):
                record["status"] = "FAIL"
                continue
            surface = item["pbr"]
            defaults = {}
            matches = (material.get_editor_property("blend_mode") == _native_blend(api, surface)
                       and material.get_editor_property("two_sided") is surface["two_sided"])
            if surface["blend"] == "masked":
                clip = material.get_editor_property("opacity_mask_clip_value")
                matches &= math.isclose(clip, surface["opacity_mask_clip"], abs_tol=1e-6)
                defaults["opacity_mask_clip"] = clip
            library = api.MaterialEditingLibrary
            for name, _, expected in _constant_parameters(surface):
                if isinstance(expected, list):
                    color = library.get_material_default_vector_parameter_value(material, name)
                    value = [color.r, color.g, color.b, color.a]
                    matches &= all(math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-6)
                                   for a, b in zip(value, expected))
                else:
                    value = library.get_material_default_scalar_parameter_value(material, name)
                    matches &= math.isclose(value, expected, rel_tol=1e-6, abs_tol=1e-6)
                defaults[name] = value
            record.update(status="PASS" if matches else "FAIL", observed_parameter_defaults=defaults)
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            record["reason"] = str(exc)
    return results
