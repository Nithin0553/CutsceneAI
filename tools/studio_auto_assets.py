"""Read-only, source-bound plan for automatic Unity -> Unreal staging.

Only imports files whose source identity can be resolved unambiguously. An
unresolvable source is a PREPARATION blocker, not a license to invent assets.
This capability intentionally does not assert source/target fidelity.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import studio_source_identity as source_identity
import studio_source_materials


class AutoAssetError(ValueError):
    pass


def digest(path):
    """Stream content hashes; large FBX files must not be buffered in RAM."""
    state = hashlib.sha256()
    with Path(path).open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            state.update(chunk)
    return state.hexdigest()


def _read(path):
    obj = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(obj, dict):
        raise AutoAssetError('Expected JSON object: ' + str(path))
    return obj


def _stem(value):
    # Conservative normalization supports source names like A_Walk_RootMotion
    # versus FBX filenames Walking.fbx. Never accept more than one match.
    tokens = [x.lower() for x in re.findall(r'[A-Za-z0-9]+', str(value))]
    tokens = [x for x in tokens if x not in ('a', 'b', 'rootmotion', 'animation', 'clip')]
    s = ''.join(tokens)
    return s[:-3] if s.endswith('ing') and len(s) > 6 else s


def _match(files, name, suffixes, *, aliases=()):
    wanted = {_stem(v) for v in (name, *aliases) if _stem(v)}
    options = [p for p in files if p.suffix.lower() in suffixes and _stem(p.stem) in wanted]
    return options[0] if len(options) == 1 else None, [str(p) for p in options]


def _model_records(entity):
    models = (entity.get('metadata') or {}).get('source_model_assets') or []
    if not isinstance(models, list) or any(not isinstance(row, dict) for row in models):
        raise AutoAssetError('Invalid Unity renderer model identity for '+str(entity.get('name')))
    return (entity, *models)


def _resolve_model(files, name, entity, root):
    metadata = entity.get('metadata') or {}
    records = _model_records(entity)
    # A new extractor that explicitly found no imported renderer mesh must
    # never turn a coincidentally named FBX into that character or prop.
    if 'source_model_assets' in metadata and len(records) == 1:
        return {'selected': None, 'strategy': 'NO_RENDERED_MODEL_ASSET_REFERENCE',
                'candidates': []}
    return source_identity.resolve(files, name, {'.fbx'}, project_root=root, records=records)


def _source_model_files(root, csir):
    """Include only source-exported FBX identities outside the selected scan scope.

    Broad filename guessing still stays inside the chosen source scope. A
    renderer's exact AssetDatabase path may legitimately live elsewhere in
    this same Unity Assets/ tree; its Unity .meta GUID is checked when exported.
    """
    assets_root = (root / 'Assets').resolve()
    result = set()
    for entity in csir.get('entities', []):
        for record in _model_records(entity)[1:]:
            relative = str(record.get('asset_path') or '').replace('\\', '/')
            parts = relative.split('/')
            if not relative.startswith('Assets/') or '..' in parts or '.' in parts:
                continue
            if Path(relative).suffix.lower() != '.fbx':
                continue
            path = (root / relative).resolve()
            if not path.is_relative_to(assets_root):
                raise AutoAssetError('Unity model identity escapes Assets/: '+relative)
            if path.is_file():
                result.add(path)
            if len(result) > 3000:
                raise AutoAssetError('Too many source-referenced model assets.')
    return result


def _source_reference(root, asset_path, guid, suffix):
    """Verify one exact Unity asset identity inside this project, if supported."""
    relative = str(asset_path or '').replace('\\', '/')
    parts = relative.split('/')
    if not relative.startswith('Assets/') or '..' in parts or '.' in parts:
        return None, 'UNSUPPORTED_OR_UNSAFE_SOURCE_PATH'
    if Path(relative).suffix.lower() != suffix:
        return None, 'UNSUPPORTED_SOURCE_FORMAT'
    path = (root / relative).resolve()
    if not path.is_relative_to((root / 'Assets').resolve()):
        raise AutoAssetError('Referenced Unity asset escapes Assets/: '+relative)
    if not path.is_file():
        return None, 'SOURCE_FILE_NOT_FOUND'
    identity = source_identity.resolve(
        [path], Path(relative).stem, {suffix}, project_root=root,
        records=({'asset_path': relative, 'guid': guid},),
    )
    return identity['selected'], identity['strategy']


def _material_records(entity):
    rows = (entity.get('metadata') or {}).get('source_material_assets') or []
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise AutoAssetError('Invalid Unity renderer material identity for '+str(entity.get('name')))
    return rows


def inspect(csir_path, mapping_path, plan_path, source_project, source_scope, target_folder):
    """Describe every file needed by mapped actions before an editor runs.

    Source root is real Unity Assets/, not a CSIR guess. `source_scope` narrows
    lookup to avoid similarly named models in other scenes.
    """
    csir_path, mapping_path, plan_path = (
        Path(p).resolve() for p in (csir_path, mapping_path, plan_path)
    )
    root = Path(source_project).resolve()
    if not (root / 'Assets').is_dir() or (root / 'Assets').is_symlink():
        raise AutoAssetError('Select a Unity project folder containing Assets/.')
    scope = str(source_scope).replace('\\', '/').strip('/')
    if not scope or not (scope == 'Assets' or scope.startswith('Assets/')) or '..' in scope.split('/'):
        raise AutoAssetError('Choose a source scope under Assets/, such as Assets/Benchmark002.')
    search_root = (root / scope).resolve()
    if not search_root.is_relative_to((root / 'Assets').resolve()) or not search_root.is_dir():
        raise AutoAssetError('Source Assets scope is missing or outside Unity Assets/.')
    if not re.fullmatch(r'/Game(?:/[A-Za-z0-9_]+)+', str(target_folder)):
        raise AutoAssetError('Invalid new Unreal staging namespace.')
    csir, mapping, plan = _read(csir_path), _read(mapping_path), _read(plan_path)
    if csir.get('source', {}).get('engine') != 'unity' or csir.get('schema_version') != '0.1.0':
        raise AutoAssetError('Expected Unity CSIR v0.1.0.')
    if mapping.get('sequence_asset_path') != plan.get('sequence_asset_path'):
        raise AutoAssetError('Prepared sequence and mapping disagree.')
    if mapping.get('overwrite_sequence'):
        raise AutoAssetError('Automatic import refuses sequence overwriting.')
    files = sorted((x.resolve() for x in search_root.rglob('*')
                    if x.is_file() and x.suffix.lower() in {'.fbx', '.wav', '.mp3'}),
                   key=lambda p:str(p).lower())
    if len(files) > 3000:
        raise AutoAssetError('Source scope contains too many import candidates; select a smaller folder.')
    for f in files:
        if not f.is_relative_to(search_root):
            raise AutoAssetError('Source symlink escapes chosen Unity scope: '+str(f))
    files = sorted(set(files) | _source_model_files(root, csir), key=lambda p:str(p).lower())
    # A whole Unity Assets/ folder can include unrelated editor icons and
    # tutorial placeholders. Images are resolved only from source references.
    assets = {str(a.get('asset_id')): a for a in csir.get('assets', [])}
    entity_names = Counter(str(e.get('name')) for e in csir.get('entities', []))
    asset_ids = Counter(str(a.get('asset_id')) for a in csir.get('assets', []))
    entities = {str(e.get('name')): e for e in csir.get('entities', [])}
    blockers, warnings, imports, actors = [], [], [], []
    blockers.extend('Duplicate source entity name requires source-ID mapping: '+name
                    for name, count in sorted(entity_names.items()) if count > 1)
    blockers.extend('Duplicate source asset ID in CSIR: '+asset_id
                    for asset_id, count in sorted(asset_ids.items()) if count > 1)
    asset_resolutions = []
    skipped_optional_textures = []
    deduplicated_textures = []
    used_target = {}
    def add_import(source, dest, kind, *, character=None):
        if not dest.startswith('/Game/') or '..' in dest.split('/'):
            blockers.append('Unsafe target path: '+dest)
            return
        reason = None
        if source.stat().st_size == 0:
            reason = 'empty file'
        elif source.suffix.lower() == '.png':
            with source.open('rb') as stream:
                if stream.read(8) != b'\x89PNG\r\n\x1a\n':
                    reason = 'invalid PNG signature'
        elif source.suffix.lower() == '.wav':
            with source.open('rb') as stream:
                header = stream.read(12)
            if len(header) < 12 or header[:4] != b'RIFF' or header[8:12] != b'WAVE':
                reason = 'invalid WAV header'
        if reason is not None:
            if kind == 'Texture2D':
                skipped_optional_textures.append(str(source) + ' (' + reason + ')')
            else:
                blockers.append('Required ' + kind + ' source is ' + reason + ': ' + str(source))
            return
        sha256 = digest(source)
        if dest in used_target:
            previous = used_target[dest]
            # Unity/FBX packages often contain a second copy of the *same*
            # PNG. Deduplicate only identical texture bytes; never merge
            # animations or actor-specific meshes on name/content alone.
            if kind == 'Texture2D' and previous['kind'] == kind and previous['sha256'] == sha256:
                deduplicated_textures.append({
                    'source_file': str(source), 'source_sha256': sha256,
                    'canonical_source_file': previous['source_file'],
                    'target_asset_path': dest,
                })
                return
            blockers.append('Target asset collision at ' + dest + ': ' +
                            previous['source_file'] + ' versus ' + str(source))
            return
        used_target[dest] = {'source_file': str(source), 'sha256': sha256,
                             'kind': kind, 'character': character}
        imports.append({'source_file':str(source),'source_sha256':sha256,
                        'target_asset_path':dest,'kind':kind,'character':character})
    bindings = plan.get('bindings') or {}
    if not bindings:
        blockers.append('No mapped source actors in the transfer plan.')
    for name, label in sorted(bindings.items()):
        entity = entities.get(name)
        if entity is None:
            blockers.append('Mapped actor not found in source CSIR: '+name)
            continue
        kind = str(entity.get('ced_type') or '')
        if kind == 'entity.character':
            evidence = _resolve_model(files, name, entity, root)
            found = evidence['selected']
            asset_resolutions.append({'source': name, 'kind': 'character',
                                      'strategy': evidence['strategy'],
                                      'candidates': evidence['candidates']})
            if found is None:
                blockers.append('Character '+name+' cannot resolve uniquely ('+evidence['strategy']+
                                '); candidate FBX files: '+str(len(evidence['candidates'])))
                continue
            dest = target_folder+'/Characters/CSAI_'+re.sub('[^A-Za-z0-9_]','_',name)
            add_import(found,dest,'SkeletalMesh',character=name)
        elif kind not in ('entity.camera','entity.light','entity.prop'):
            blockers.append('Unsupported mapped scene actor '+name+' ('+kind+').')
            continue
        actor_spec = {'name':name, 'label':str(label), 'kind':kind}
        if kind == 'entity.light':
            # The Unity exporter already includes Light.type in CSIR. Always
            # keep that source identity; a PointLight cannot stand in for a
            # source DirectionalLight. Unsupported kinds must not silently
            # acquire the wrong lighting semantics.
            light = (entity.get('metadata') or {}).get('light') or {}
            source_type = str(light.get('light_type') or '').strip()
            native_classes = {
                'Directional': 'DirectionalLight',
                'Point': 'PointLight',
                'Spot': 'SpotLight',
            }
            if source_type and source_type not in native_classes:
                blockers.append('Unsupported Unity light type for '+name+': '+
                                source_type+'; no Unreal light class assumed.')
            elif source_type:
                actor_spec['source_light_type'] = source_type
                actor_spec['target_light_class'] = native_classes[source_type]
            else:
                warnings.append('Unity light '+name+
                                ' has no captured source type; PointLight is a legacy '
                                'placeholder, not proven source lighting parity. Re-export.')
        actors.append(actor_spec)
        if kind == 'entity.prop':
            evidence = _resolve_model(files, name, entity, root)
            asset_resolutions.append({'source': name, 'kind': 'prop_mesh',
                                      'strategy': evidence['strategy'],
                                      'candidates': evidence['candidates']})
            if evidence['selected'] is not None:
                dest = target_folder+'/Props/CSAI_'+re.sub('[^A-Za-z0-9_]','_',name)
                add_import(evidence['selected'], dest, 'StaticMesh')
                actors[-1]['mesh_path'] = dest
            else:
                # A transform-only prop preserves Timeline movement but does
                # not constitute a visual mesh transfer. Keep loss explicit.
                warnings.append('Prop '+name+' has no uniquely identified source mesh ('+
                                evidence['strategy']+'); transform-only representation.')
    # Identify exact animation names from source section asset IDs, not arbitrary
    # target path basenames which may be from a different Unreal project.
    clip_sources = defaultdict(set)
    for track in csir.get('tracks', []):
        if track.get('muted') or track.get('ced_type') != 'animation.track':
            continue
        entity_id = track.get('binding_entity_id')
        bound = next((e.get('name') for e in csir.get('entities', []) if e.get('entity_id') == entity_id), None)
        for section in track.get('sections', []):
            asset = assets.get(str((section.get('payload') or {}).get('asset_id')))
            if asset and bound:
                clip_sources[(str(asset.get('name')),bound)].add(str(asset.get('asset_id')))
    mapped_assets = mapping.get('assets') or {}
    for action in plan.get('actions', []):
        kind = action.get('kind')
        if kind not in ('skeletal_animation','audio'):
            continue
        path = str(action.get('unreal_asset_path') or '')
        names = [name for name,target in mapped_assets.items() if target==path]
        if len(names)!=1:
            blockers.append('Cannot identify unique Unity asset for target '+path)
            continue
        name = names[0]
        if kind == 'skeletal_animation':
            character = str(action.get('entity_name') or '')
            if (name,character) not in clip_sources:
                blockers.append('Source animation '+name+' is not bound to character '+character+' in CSIR.')
                continue
            references = [assets[asset_id] for asset_id in clip_sources[(name,character)]
                          if asset_id in assets]
            evidence = source_identity.resolve(files, name, {'.fbx'}, project_root=root,
                                               records=references)
            match = evidence['selected']
            asset_resolutions.append({'source': name, 'kind': 'animation',
                                      'strategy': evidence['strategy'],
                                      'candidates': evidence['candidates']})
            if match is None:
                blockers.append('Animation '+name+' cannot resolve uniquely ('+evidence['strategy']+
                                '); candidate FBX files: '+str(len(evidence['candidates'])))
                continue
            add_import(match,path,'AnimSequence',character=character)
        elif kind == 'audio':
            references = [a for a in assets.values() if str(a.get('name')) == name]
            evidence = source_identity.resolve(files, name, {'.wav', '.mp3'}, project_root=root,
                                               records=references)
            match = evidence['selected']
            asset_resolutions.append({'source': name, 'kind': 'audio',
                                      'strategy': evidence['strategy'],
                                      'candidates': evidence['candidates']})
            if match is None:
                blockers.append('Audio '+name+' cannot resolve uniquely ('+evidence['strategy']+
                                '); candidate WAV/MP3 files: '+str(len(evidence['candidates'])))
                continue
            # Unreal Engine 5.8 imports MP3 directly to SoundWave; do not
            # force a third-party FFmpeg executable in its Python environment.
            add_import(match,path,'SoundWave')
    # Record what the planner did NOT bind; source hierarchy/mesh components
    # are not necessarily independent actors and must never be fabricated.
    unmapped_entities = [
        {'name':str(e.get('name')), 'ced_type':str(e.get('ced_type'))}
        for e in csir.get('entities', []) if e.get('name') not in bindings
    ]
    if unmapped_entities:
        warnings.append(str(len(unmapped_entities)) + ' source entities have no independent target actor binding; inspect CED coverage before claiming full scene transfer.')
    # Separate visible, source-rendered objects from auxiliary Transform parents.
    # A "generated" Level Sequence must not hide missing scenery under a
    # generic count of unbound source entities.
    missing_renderers = [
        e for e in csir.get('entities', [])
        if (e.get('metadata') or {}).get('scene_renderable_root') is True
        and (e.get('metadata') or {}).get('active_self') is not False
        and e.get('ced_type') == 'entity.prop'
        and e.get('name') not in bindings
    ]
    if missing_renderers:
        examples = ', '.join(str(e.get('name') or e.get('entity_id'))
                             for e in missing_renderers[:6])
        warnings.append(
            str(len(missing_renderers)) +
            ' visible scene renderer root(s) are NOT mapped into Unreal actors: ' +
            examples + '. Verify source FBX identity and distinct names; '
            'non-FBX primitives, multi-file LOD groups and unsupported meshes '
            'require separate source-backed adapters.'
        )
    # Import only textures identified by a mapped renderer's source material
    # or an explicit CSIR asset. Scanning all project PNGs imports unrelated
    # tutorial/editor assets and turns invalid placeholders into false warnings.
    material_files = set()
    material_files_by_actor = defaultdict(set)
    texture_files = set()
    for name in sorted(bindings):
        entity = entities.get(name)
        if entity is None or entity.get('ced_type') not in ('entity.character', 'entity.prop'):
            continue
        for record in _material_records(entity):
            path = record.get('asset_path')
            if path:
                material, strategy = _source_reference(root, path, record.get('guid'), '.mat')
                if material is not None:
                    material_files.add(material)
                    # Keep source material identity tied to the exact CSIR
                    # renderer actor. Slot names are not globally unique.
                    material_files_by_actor[name].add(material)
                elif Path(str(path)).suffix.lower() == '.mat':
                    warnings.append('Renderer material '+str(path)+' is unresolved ('+strategy+').')
            texture_path = record.get('albedo_texture_asset_path')
            if texture_path:
                texture, strategy = _source_reference(
                    root, texture_path, record.get('albedo_texture_guid'), '.png'
                )
                if texture is not None:
                    texture_files.add(texture)
                else:
                    warnings.append('Renderer albedo '+str(texture_path)+' is unresolved ('+strategy+').')
    for asset in csir.get('assets', []):
        metadata = asset.get('metadata') or {}
        path = str(metadata.get('asset_path') or '')
        if Path(path).suffix.lower() != '.png':
            continue
        texture, strategy = _source_reference(root, path, metadata.get('guid'), '.png')
        if texture is not None:
            texture_files.add(texture)
        else:
            warnings.append('Referenced source texture '+path+' is unresolved ('+strategy+').')
    for file in sorted(texture_files):
        if file.suffix.lower()=='.png':
            # The filename is only used after header validation. An invalid
            # *optional* image never blocks models, clips or sequence creation.
            with file.open('rb') as stream:
                valid_png = file.stat().st_size > 0 and stream.read(8) == b'\x89PNG\r\n\x1a\n'
            if not valid_png:
                skipped_optional_textures.append(str(file) + ' (invalid or empty PNG)')
                continue
            dest=target_folder+'/Textures/CSAI_'+re.sub('[^A-Za-z0-9_]','_',file.stem)+'_'+digest(file)[:8]
            add_import(file,dest,'Texture2D')
    # The legacy unscoped summary is retained for diagnostics/older clients.
    # Never use it to assign materials to a particular actor: two unrelated
    # imported meshes may both have a "Body" slot but different source .mat.
    material_candidates, _global_diagnostics = studio_source_materials.candidates(
        material_files, imports, target_folder, digest
    )
    actor_material_candidates = {}
    for actor_name, files_for_actor in sorted(material_files_by_actor.items()):
        candidates_for_actor, diagnostics = studio_source_materials.candidates(
            files_for_actor, imports, target_folder, digest
        )
        actor_material_candidates[actor_name] = candidates_for_actor
        warnings.extend(actor_name + ': ' + message for message in diagnostics)
    planned_labels = [str(row['label']) for row in actors]
    duplicated_labels = sorted({label for label in planned_labels
                                if planned_labels.count(label) > 1})
    for label in duplicated_labels:
        blockers.append('Duplicate planned Unreal actor label: ' + label)
    if skipped_optional_textures:
        warnings.append(
            'Skipped ' + str(len(skipped_optional_textures)) +
            ' invalid optional PNG texture(s); other supported cutscene assets can still transfer. '
            'Examples: ' + '; '.join(skipped_optional_textures[:3])
        )
    if any(item['kind'] in ('SkeletalMesh','AnimSequence') for item in imports):
        warnings.append('Resolved FBX source identities; target skeletons, materials and animation motion remain unverified until Unreal readback.')
    import_fbx_materials = mapping.get('enable_fbx_embedded_material_import') is True
    if import_fbx_materials:
        warnings.append(
            'Opt-in FBX material import requested: only basic material information '
            'embedded in the original FBX can be reconstructed. Unity .mat, '
            'shader graphs, URP features and sky/ambient settings are NOT mapped. '
            'New material assets may appear in this unique target namespace; '
            'inspect material slots and visual parity after import.'
        )
    return {'kind':'cutsceneai.studio.automatic_setup_plan','schema_version':'0.1.0',
            'source_project':str(root),'source_scope':scope,'target_folder':target_folder,
            'source_csir_sha256':digest(csir_path),'mapping_sha256':digest(mapping_path),
            'transfer_plan_sha256':digest(plan_path),
            # Bind the prepared candidate to the exact staging adapter code.
            # Neither Unity data nor a newer adapter may be swapped in later.
            'inspector_code_sha256':digest(Path(__file__).resolve()),
            'identity_adapter_sha256':digest(Path(source_identity.__file__).resolve()),
            'material_adapter_sha256':digest(Path(studio_source_materials.__file__).resolve()),
            'actors':actors,'imports':imports,'asset_resolutions':asset_resolutions,
            'fbx_embedded_material_import_requested': import_fbx_materials,
            'deduplicated_textures':deduplicated_textures,
            'source_albedo_material_candidates': material_candidates,
            'source_albedo_actor_candidates': actor_material_candidates,
            'unmapped_source_entities':unmapped_entities,
            'source_entity_count':len(csir.get('entities', [])),
            'source_asset_count':len(csir.get('assets', [])),
            'blockers':sorted(set(blockers)),
            'warnings':sorted(set(warnings)), 'ready':not blockers,
            'scope_coverage':'SUPPORTED_ASSETS_ONLY','fidelity_verified':False}


def _mismatch_reason(expected, current):
    """Locate the failed evidence contract without rewriting the old plan."""
    fingerprints = (
        ('source_csir_sha256', 'Unity CSIR source export'),
        ('mapping_sha256', 'prepared target mapping'),
        ('transfer_plan_sha256', 'immutable transfer plan'),
    )
    for field, title in fingerprints:
        if expected.get(field) != current.get(field):
            return title + ' changed since Studio prepared this candidate.'
    adapters = (
        ('inspector_code_sha256', 'automatic asset inspector'),
        ('identity_adapter_sha256', 'Unity source identity resolver'),
        ('material_adapter_sha256', 'source material resolver'),
    )
    for field, title in adapters:
        if expected.get(field) != current.get(field):
            return title + ' code changed between preparation and Unreal verification.'
    before = {
        str(row.get('target_asset_path')): row
        for row in expected.get('imports', []) if isinstance(row, dict)
    }
    after = {
        str(row.get('target_asset_path')): row
        for row in current.get('imports', []) if isinstance(row, dict)
    }
    for path in sorted(set(before) | set(after)):
        old, new = before.get(path), after.get(path)
        if old is None or new is None:
            return 'Required source asset resolution changed for ' + path + '.'
        if old.get('source_file') != new.get('source_file'):
            return 'Source asset identity changed for ' + path + '.'
        if old.get('source_sha256') != new.get('source_sha256'):
            return 'Source asset contents changed for ' + path + '.'
    for field in sorted(set(expected) | set(current)):
        if expected.get(field) != current.get(field):
            return ('Source or native setup planning changed at ' + field +
                    '; confirm the source project and Studio/Unreal checkout.')
    return 'Unexpected manifest mismatch without an identifiable field.'


def verify(manifest, csir_path, mapping_path, plan_path):
    doc = _read(manifest)
    if doc.get('kind') != 'cutsceneai.studio.automatic_setup_plan':
        raise AutoAssetError('Unexpected setup plan.')
    regenerated = inspect(csir_path, mapping_path, plan_path,
                          doc['source_project'], doc['source_scope'],
                          doc['target_folder'])
    if doc != regenerated:
        raise AutoAssetError(
            _mismatch_reason(doc, regenerated) +
            ' No Unreal changes were approved. Check the Unity source files, '
            'restart the Unreal companion from this checkout, and prepare a NEW '
            'candidate; never overwrite the previous candidate.'
        )
    return doc
