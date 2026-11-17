"""Source-provenanced Unity albedo material candidates for fresh Unreal imports.

A matching material slot name AND a Unity .mat -> texture GUID -> imported PNG
chain are required. Never select textures by filename similarity alone.
These are base-color candidates, not full URP/shader or appearance parity.
"""
from __future__ import annotations

import re
from pathlib import Path

_GUID = re.compile(r"(?m)^\s*guid:\s*([0-9a-fA-F]{32})\s*$")
_TEXTURE = re.compile(
    r"(?m)^\s*-\s+(_BaseMap|_MainTex):[^\n]*\n"
    r"\s*m_Texture:\s*\{[^\n}]*\bguid:\s*([0-9a-fA-F]{32})\b"
)
_CONSTANT_SHADERS = {
    "Standard": "Resources/unity_builtin_extra",
    "Universal Render Pipeline/Lit":
        "Packages/com.unity.render-pipelines.universal/Shaders/Lit.shader",
}


def _unit_values(values, count, maximum=1.0):
    return (isinstance(values, list) and len(values) == count
            and all(type(value) in (int, float) and 0 <= value <= maximum for value in values))


def constant_surface_candidates(material_records, target_folder, digest):
    """Validate native Unity snapshots for uniquely attributable material slots."""
    by_slot = {}
    diagnostics = []
    for source_file, record in material_records:
        surface = record.get("surface")
        if not isinstance(surface, dict) or not surface.get("status"):
            continue
        slot = record.get("material_name")
        if not isinstance(slot, str) or not slot or type(record.get("slot_index")) is not int:
            diagnostics.append("MISSING_SOURCE_MATERIAL_SLOT_IDENTITY")
            continue
        by_slot.setdefault(slot, []).append((source_file, record))

    planned = []
    for slot, records in sorted(by_slot.items()):
        if len(records) != 1:
            diagnostics.append(slot + " has ambiguous source renderer assignments.")
            continue
        source_file, record = records[0]
        surface = record["surface"]
        if surface["status"] != "CAPTURED_CONSTANT_METALLIC":
            diagnostics.append(slot + " " + str(surface["status"]))
            continue
        actual_sha = digest(source_file)
        shader_name = surface.get("shader_name")
        source_guid = record.get("guid")
        if (surface.get("version") != "1.0.0" or not isinstance(shader_name, str)
                or shader_name not in _CONSTANT_SHADERS
                or surface.get("shader_asset_path") != _CONSTANT_SHADERS[shader_name]
                or surface.get("material_sha256") != actual_sha
                or not isinstance(source_guid, str) or not re.fullmatch(r"[0-9a-fA-F]{32}", source_guid)
                or record["slot_index"] < 0
                or not isinstance(record.get("renderer_path"), str) or not record["renderer_path"]
                or not _unit_values(surface.get("base_color_linear"), 4)
                or not _unit_values(surface.get("emission_linear"), 3, maximum=65504)
                or not _unit_values([surface.get(k) for k in ("metallic", "roughness", "opacity_mask_clip")], 3)
                or surface.get("blend") not in ("opaque", "masked")
                or type(surface.get("two_sided")) is not bool):
            diagnostics.append(slot + " PBR_SOURCE_SNAPSHOT_INVALID_OR_STALE")
            continue
        sanitized = re.sub(r"[^A-Za-z0-9_]", "_", slot)[:64]
        planned.append({
            "slot_name": slot, "slot_index": record["slot_index"],
            "source_renderer_path": record["renderer_path"], "source_material": str(source_file),
            "source_material_guid": source_guid.lower(), "source_material_sha256": actual_sha,
            "target_material": target_folder + "/Materials/CSAI_PBR_" + sanitized + "_" + actual_sha[:16],
            "pbr": {name: surface[name] for name in (
                "base_color_linear", "emission_linear", "metallic", "roughness",
                "blend", "opacity_mask_clip", "two_sided")},
            "strategy": "UNITY_CONSTANT_METALLIC_MATERIAL",
            "fidelity_verified": False,
        })
    return planned, diagnostics


def candidates(source_materials, imports, target_folder, digest):
    """Return (candidates, diagnostic strings); no engine or source writes.

    Only renderer-identified Unity .mat files and textures already in the
    immutable import plan are eligible. Unrelated project materials cannot
    acquire a cutscene character's Unreal slot by coincidental name.
    """
    texture_imports = {
        Path(row["source_file"]).resolve(): row
        for row in imports if row["kind"] == "Texture2D"
    }
    by_guid = {}
    for png, row in sorted(texture_imports.items()):
        meta = png.with_name(png.name + ".meta")
        if not meta.is_file():
            continue
        match = _GUID.search(meta.read_text(encoding="utf-8-sig", errors="replace"))
        if match:
            by_guid.setdefault(match.group(1).lower(), []).append(row)

    names = {}
    for file in sorted(source_materials):
        path = Path(file).resolve()
        if path.is_file() and path.suffix.lower() == ".mat":
            names.setdefault(path.stem, []).append(path)

    planned, diagnostics = [], []
    for name, files in sorted(names.items()):
        if len(files) != 1:
            diagnostics.append("Ambiguous Unity material name: " + name)
            continue
        source = files[0]
        text = source.read_text(encoding="utf-8-sig", errors="replace")
        matches = _TEXTURE.findall(text)
        # Prefer URP _BaseMap, otherwise built-in Standard _MainTex.
        chosen = next((guid for key, guid in matches if key == "_BaseMap"), None)
        if chosen is None:
            chosen = next((guid for key, guid in matches if key == "_MainTex"), None)
        if chosen is None:
            continue
        textures = by_guid.get(chosen.lower(), [])
        if len(textures) != 1:
            diagnostics.append("Unity material " + name +
                               " has no unique imported albedo texture GUID.")
            continue
        # Unreal imports can expose exact slot names from source FBX; do not
        # predict them from the material filename.
        sanitized = re.sub(r"[^A-Za-z0-9_]", "_", name)
        if not sanitized:
            continue
        planned.append({
            "slot_name": name,
            "source_material": str(source),
            "source_material_sha256": digest(source),
            "source_texture": textures[0]["source_file"],
            "source_texture_sha256": textures[0]["source_sha256"],
            "target_texture": textures[0]["target_asset_path"],
            "target_material": target_folder + "/Materials/CSAI_" +
                               sanitized + "_" + digest(source)[:8],
            "strategy": "UNITY_MAT_ALBEDO_GUID_AND_EXACT_FBX_SLOT",
            "fidelity_verified": False,
        })
    # Sanitization/hashing can still collide: remove ambiguous destinations.
    by_dest = {}
    for item in planned:
        by_dest.setdefault(item["target_material"], []).append(item)
    safe = [item for item in planned if len(by_dest[item["target_material"]]) == 1]
    for dest, items in by_dest.items():
        if len(items) > 1:
            diagnostics.append("Ambiguous generated material destination: " + dest)
    return safe, sorted(set(diagnostics))
