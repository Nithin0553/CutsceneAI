"""Read-only, source-bound plan for automatic Unity -> Unreal staging.

Only imports files whose source identity can be resolved unambiguously. An
unresolvable source is a PREPARATION blocker, not a license to invent assets.
This capability intentionally does not assert source/target fidelity.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path


class AutoAssetError(ValueError):
    pass


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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


def inspect(csir_path, mapping_path, plan_path, source_project, source_scope, target_folder):
    """Describe every file needed by mapped actions before an editor runs.

    Source root is real Unity Assets/, not a CSIR guess. `source_scope` narrows
    lookup to avoid similarly named models in other scenes.
    """
    csir_path, mapping_path, plan_path = map(lambda p: Path(p).resolve(), (csir_path, mapping_path, plan_path))
    root = Path(source_project).resolve()
    if not (root / 'Assets').is_dir():
        raise AutoAssetError('Select a Unity project folder containing Assets/.')
    scope = str(source_scope).replace('\\', '/').strip('/')
    if not scope or not scope.startswith('Assets/') or '..' in scope.split('/'):
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
    files = sorted((x.resolve() for x in search_root.rglob('*') if x.is_file() and x.suffix.lower() in {'.fbx', '.png', '.wav', '.mp3'}), key=lambda p:str(p).lower())
    if len(files) > 3000:
        raise AutoAssetError('Source scope contains too many import candidates; select a smaller folder.')
    for f in files:
        if not f.is_relative_to(search_root):
            raise AutoAssetError('Source symlink escapes chosen Unity scope: '+str(f))
    assets = {str(a.get('asset_id')): a for a in csir.get('assets', [])}
    entities = {str(e.get('name')): e for e in csir.get('entities', [])}
    paths = defaultdict(list)
    blockers, warnings, imports, actors = [], [], [], []
    used_source = {}
    used_target = set()
    def add_import(source, dest, kind, *, character=None):
        if dest in used_target:
            return
        if not dest.startswith('/Game/') or '..' in dest.split('/'):
            blockers.append('Unsafe target path: '+dest)
            return
        if source in used_source and used_source[source] != dest:
            blockers.append('One source file resolves to multiple target identities: '+str(source))
            return
        used_source[source] = dest
        used_target.add(dest)
        imports.append({'source_file':str(source),'source_sha256':digest(source),
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
            found, matches = _match(files, name, {'.fbx'})
            if found is None:
                blockers.append('Character '+name+' requires exactly one matching FBX model; found '+str(len(matches)))
                continue
            dest = target_folder+'/Characters/CSAI_'+re.sub('[^A-Za-z0-9_]','_',name)
            add_import(found,dest,'SkeletalMesh',character=name)
        elif kind not in ('entity.camera','entity.light','entity.prop'):
            blockers.append('Unsupported mapped scene actor '+name+' ('+kind+').')
            continue
        actors.append({'name':name, 'label':str(label), 'kind':kind})
        if kind == 'entity.prop':
            warnings.append('Prop '+name+' will use a transform actor; mesh/material transfer is not verified.')
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
            match, matches = _match(files,name,{'.fbx'})
            if match is None:
                blockers.append('Animation '+name+' must resolve to one FBX; found '+str(len(matches))+'. Export its original animation FBX into the selected Unity scope.')
                continue
            add_import(match,path,'AnimSequence',character=character)
        elif kind == 'audio':
            match, matches = _match(files,name,{'.wav','.mp3'})
            if match is None:
                blockers.append('Audio '+name+' must resolve to one WAV/MP3; found '+str(len(matches)))
                continue
            if match.suffix.lower()=='.mp3':
                warnings.append('Audio '+name+' requires FFmpeg MP3-to-WAV conversion in the Unreal editor environment.')
            add_import(match,path,'SoundWave')
    # Record what the planner did NOT bind; source hierarchy/mesh components
    # are not necessarily independent actors and must never be fabricated.
    unmapped_entities = [
        {'name':str(e.get('name')), 'ced_type':str(e.get('ced_type'))}
        for e in csir.get('entities', []) if e.get('name') not in bindings
    ]
    if unmapped_entities:
        warnings.append(str(len(unmapped_entities)) + ' source entities have no independent target actor binding; inspect CED coverage before claiming full scene transfer.')
    # Texture imports are independent of the Sequence track bindings. The
    # corresponding UE materials are not inferred from a filename.
    for file in files:
        if file.suffix.lower()=='.png':
            dest=target_folder+'/Textures/CSAI_'+re.sub('[^A-Za-z0-9_]','_',file.stem)+'_'+digest(file)[:8]
            add_import(file,dest,'Texture2D')
    if any(item['kind'] in ('SkeletalMesh','AnimSequence') for item in imports):
        warnings.append('FBX source files are matched by unambiguous names; compatible target skeletons, materials and animation motion remain unverified.')
    return {'kind':'cutsceneai.studio.automatic_setup_plan','schema_version':'0.1.0',
            'source_project':str(root),'source_scope':scope,'target_folder':target_folder,
            'source_csir_sha256':digest(csir_path),'mapping_sha256':digest(mapping_path),
            'transfer_plan_sha256':digest(plan_path),
            'actors':actors,'imports':imports,'unmapped_source_entities':unmapped_entities,
            'source_entity_count':len(csir.get('entities', [])),
            'source_asset_count':len(csir.get('assets', [])),
            'blockers':sorted(set(blockers)),
            'warnings':sorted(set(warnings)), 'ready':not blockers,
            'scope_coverage':'SUPPORTED_ASSETS_ONLY','fidelity_verified':False}


def verify(manifest, csir_path, mapping_path, plan_path):
    doc=_read(manifest)
    if doc.get('kind')!='cutsceneai.studio.automatic_setup_plan':
        raise AutoAssetError('Unexpected setup plan.')
    regenerated=inspect(csir_path,mapping_path,plan_path,doc['source_project'],doc['source_scope'],doc['target_folder'])
    if doc!=regenerated:
        raise AutoAssetError('Source assets or prepared plan changed; regenerate setup manifest.')
    return doc
