"""Conservative native Unreal albedo restoration on newly staged actors.

Only exact FBX material-slot names with source-backed Unity .mat/PNG GUIDs
qualify. Does not translate arbitrary Unity/URP shaders or prove render parity.
"""
from __future__ import annotations


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
