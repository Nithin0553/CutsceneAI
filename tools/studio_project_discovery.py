"""Read-only discovery of Unity and Unreal projects from two folder selections.

Supports choosing the project root, its Assets/Content child, or a parent folder.
Discovers actual CSIR JSON by schema/content, not solely by filename. Never
pretends native .unity/.playable assets are already exported CSIR documents.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path


class DiscoveryError(ValueError):
    pass


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except (OSError, ValueError) as exc:
        raise DiscoveryError(f'Cannot read exported file {path.name}: {exc}') from exc
    if not isinstance(data, dict):
        raise DiscoveryError(f'Expected a JSON object in {path.name}')
    return data


def _inside(path: Path, root: Path) -> bool:
    return path.resolve().is_relative_to(root.resolve())


def _is_project_root(root: Path, kind: str) -> bool:
    if not root.is_dir() or root.is_symlink():
        return False
    if kind == 'unity':
        return (root/'Assets').is_dir() and (root/'ProjectSettings').is_dir() and not (root/'Assets').is_symlink()
    return any(p.is_file() and not p.is_symlink() for p in root.glob('*.uproject'))


def project_roots(folder: str, kind: str) -> list[str]:
    """Find projects under a chosen path; do not descend into game asset trees."""
    if kind not in {'unity', 'unreal'}:
        raise DiscoveryError('Unknown project engine.')
    path = Path(folder).expanduser().resolve() if folder else None
    if path is None:
        return []
    if not path.is_dir():
        raise DiscoveryError('Selected folder does not exist: ' + str(path))
    # Handle Assets, Content, and deeper subfolders. The closest valid ancestor
    # wins rather than guessing another sibling project.
    for parent in (path, *list(path.parents)[:8]):
        if _is_project_root(parent, kind):
            return [str(parent)]
    # Allow selecting a workspace that contains multiple Unity/Unreal projects.
    # Scan only two directory levels, with limits and no symlink traversal.
    choices: list[Path] = []
    frontier = [path]
    ignored = {'Library', 'Temp', 'Logs', '.git', 'node_modules', 'Intermediate', 'Saved', 'Binaries', 'DerivedDataCache'}
    for _depth in range(3):
        next_level = []
        for folder_path in frontier[:100]:
            if _is_project_root(folder_path, kind):
                choices.append(folder_path)
                continue
            try:
                children = sorted((p for p in folder_path.iterdir() if p.is_dir() and not p.is_symlink()
                                   and p.name not in ignored), key=lambda p:p.name.casefold())[:80]
            except OSError:
                continue
            next_level.extend(children)
        frontier = next_level[:150]
    return [str(p.resolve()) for p in sorted(set(choices), key=lambda p:str(p).casefold())]


def browse_project_folder(kind: str) -> str:
    """Open native picker in Windows companion and normalize known child folders."""
    if kind not in {'unity', 'unreal'}:
        raise DiscoveryError('Choose Unity or Unreal project.')
    if sys.platform != 'win32':
        raise DiscoveryError('Native folder selection is currently supported on Windows only.')
    title = ('Choose Unity project or any folder inside it' if kind == 'unity'
             else 'Choose Unreal project or any folder inside it')
    code = (
        'import tkinter as tk; from tkinter import filedialog; '
        'root=tk.Tk(); root.withdraw(); root.attributes("-topmost",True); '
        'path=filedialog.askdirectory(parent=root, title=' + repr(title) + ', mustexist=True); '
        'print(path); root.destroy()'
    )
    try:
        result = subprocess.run([sys.executable, '-c', code], capture_output=True,
                                text=True, timeout=180, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DiscoveryError('Folder dialog could not open on the local desktop.') from exc
    if result.returncode != 0:
        raise DiscoveryError('Folder picker unavailable. Run the Studio companion in a normal Windows desktop session.')
    chosen = result.stdout.strip()
    if not chosen:
        return ''
    candidates = project_roots(chosen, kind)
    return candidates[0] if len(candidates) == 1 else str(Path(chosen).resolve())


def _find_csir_files(root: Path):
    """Walk the Unity project excluding engine caches and external symlinks."""
    ignored = {'Library', 'Temp', 'Logs', 'Obj', '.git', 'node_modules', '.vs',
               '.idea', 'Build', 'Builds', 'PackagesCache', 'UserSettings'}
    visited = 0
    for base, dirs, files in os.walk(root, topdown=True, followlinks=False):
        base_path = Path(base)
        rel_parts = base_path.relative_to(root).parts
        if len(rel_parts) >= 8:
            dirs[:] = []
        else:
            dirs[:] = sorted(d for d in dirs if d not in ignored and not (base_path/d).is_symlink())
        for name in sorted(files):
            if not name.casefold().endswith('.json'):
                continue
            p = base_path/name
            if p.is_symlink() or not _inside(p, root):
                continue
            visited += 1
            if visited > 8000:
                raise DiscoveryError('Too many JSON files to scan safely. Place exported CSIR files in CutSceneAI/Exports.')
            try:
                if p.stat().st_size <= 32*1024*1024:
                    yield p.resolve()
            except OSError:
                continue


def scan_unity(folder: str) -> dict:
    choices = project_roots(folder, 'unity')
    if len(choices) != 1:
        raise DiscoveryError('Select a Unity project containing Assets and ProjectSettings.' if not choices
                             else 'Multiple Unity projects found; choose one from the available options.')
    root = Path(choices[0])
    scenes = []
    for path in _find_csir_files(root):
        # Not every JSON document in a Unity project is a CSIR. Ignore unrelated
        # JSON instead of treating it as a parsing error.
        try:
            obj = _read_json(path)
        except DiscoveryError:
            continue
        if (obj.get('schema_version') != '0.1.0' or
            not isinstance(obj.get('source'), dict) or
            obj['source'].get('engine') != 'unity' or
            not isinstance(obj.get('tracks'), list) or
            not isinstance(obj.get('entities'), list) or
            not obj.get('cutscene_id')):
            continue
        scenes.append({'path': str(path),
                       'name': str(obj.get('name') or obj.get('title') or path.stem),
                       'cutscene_id': str(obj['cutscene_id']),
                       'tracks': len(obj['tracks']), 'entities': len(obj['entities']),
                       'relative_path': path.relative_to(root).as_posix()})
    return {'folder': str(root), 'cutscenes': scenes, 'source_scope': 'Assets',
            'message': (f'Found {len(scenes)} exported cutscene(s).' if scenes else
                        'No CutSceneAI CSIR export found. Native Unity scene/Timeline files cannot yet be decoded directly; export a Timeline using Tools > CutsceneAI > Export Selected Timeline, then Scan again.')}


def scan_unreal(folder: str, worker: dict | None = None, *, project_choice: str = '') -> dict:
    choices = project_roots(folder, 'unreal')
    if len(choices) != 1:
        raise DiscoveryError('Select an Unreal project containing a .uproject file.' if not choices
                             else 'Multiple Unreal projects found; choose one from the available options.')
    root = Path(choices[0])
    projects = sorted((p.resolve() for p in root.glob('*.uproject') if p.is_file() and not p.is_symlink()),
                      key=lambda p:p.name.casefold())
    if not projects:
        raise DiscoveryError('No .uproject file found in selected Unreal project.')
    options = [str(p) for p in projects]
    selected_project = next((p for p in projects if str(p) == project_choice), None)
    if selected_project is None and len(projects) == 1:
        selected_project = projects[0]
    content = root/'Content'
    levels = []
    if content.is_dir() and not content.is_symlink():
        for base, dirs, files in os.walk(content, followlinks=False):
            here = Path(base)
            dirs[:] = [d for d in dirs if not (here/d).is_symlink()]
            for name in files:
                p=here/name
                if p.suffix.casefold() != '.umap' or p.is_symlink():
                    continue
                rel = p.relative_to(content).with_suffix('')
                if len(levels) >= 500:
                    raise DiscoveryError('Too many Unreal maps found (over 500).')
                if all(re.fullmatch(r'[A-Za-z0-9_]+', part) for part in rel.parts):
                    levels.append('/Game/'+'/'.join(rel.parts))
    levels=sorted(set(levels))
    active=''
    if (selected_project is not None and worker and worker.get('connected') and
        Path(str(worker.get('project') or '')).resolve()==selected_project):
        active=str(worker.get('level') or '')
        if active.startswith('/Game/') and active not in levels:
            levels.append(active)
            levels.sort()
    create_level = False
    if not levels:
        # A planned path is not an existing .umap: the opt-in Unreal worker
        # must create and save it before any scene import or Sequencer build.
        levels = ['/Game/CutSceneAI/AutoTransfer/L_Studio_Fresh']
        create_level = True
    return {'folder':str(root), 'project':str(selected_project) if selected_project else '',
            'project_options':options, 'levels':levels, 'active_level':active,
            'new_level_required':create_level,
            'message': ('No saved map found. Studio will create a fresh target level during Generate, after your approval.'
                        if create_level else f'Found {len(levels)} Unreal map(s).')}


def discover(unity_folder: str, unreal_folder: str, *, worker: dict | None = None,
             unreal_project: str = '') -> dict:
    """Partial discovery never fails the other project because one path is wrong."""
    result = {'unity':None,'unreal':None,'unity_projects':[], 'unreal_projects':[],
              'errors':{},'ready':False}
    for kind, chosen in [('unity',unity_folder),('unreal',unreal_folder)]:
        if not chosen:
            continue
        try:
            options = project_roots(chosen, kind)
            result[kind+'_projects'] = options
            if not options:
                result['errors'][kind] = f'No {kind.title()} project found inside the selected folder.'
            elif len(options) > 1:
                result['errors'][kind] = f'Found {len(options)} {kind.title()} projects. Select one from the list.'
            elif kind == 'unity':
                result['unity'] = scan_unity(options[0])
            else:
                result['unreal'] = scan_unreal(options[0], worker, project_choice=unreal_project)
        except DiscoveryError as exc:
            result['errors'][kind] = str(exc)
    unreal = result['unreal'] or {}
    result['ready'] = bool(result['unity'] and result['unity']['cutscenes'] and
                           result['unreal'] and unreal['project'] and unreal['levels'])
    return result


def _safe_label(name: str) -> str:
    base = re.sub(r'[^A-Za-z0-9_]', '_', name).strip('_')[:45]
    return base or 'Item'


def _source_mapping(csir: dict, csir_bytes: bytes, project: str, level: str) -> dict:
    """Only map track-bound CED actors, never arbitrary source child components."""
    entities = {str(e.get('entity_id')): e for e in csir.get('entities', [])}
    used_ids: set[str] = set()
    for track in csir.get('tracks', []):
        if track.get('muted') is True or not track.get('sections'):
            continue
        eid = str(track.get('binding_entity_id') or '')
        if eid in entities and entities[eid].get('ced_type') in {
                'entity.character', 'entity.camera', 'entity.prop', 'entity.light'}:
            used_ids.add(eid)
    # Include attached child props when their parent is a mapped actor.
    for eid, e in entities.items():
        if e.get('ced_type') == 'entity.prop' and str(e.get('parent_entity_id')) in used_ids:
            used_ids.add(eid)
    selected = [entities[eid] for eid in sorted(used_ids)]
    names = [str(x.get('name') or '') for x in selected]
    if not selected or any(not x for x in names) or len(names) != len(set(names)):
        raise DiscoveryError('Cutscene actor identities are incomplete or ambiguous. Export a fresh CSIR.')
    fingerprint = hashlib.sha256(csir_bytes + project.encode('utf-8') + level.encode('utf-8')).hexdigest()[:10].upper()
    target_dir = '/Game/CutSceneAI/AutoTransfer/T_' + fingerprint
    bindings = {}
    for e in selected:
        name = str(e['name'])
        bindings[name] = {'actor_label': 'CSAI_' + fingerprint + '_' + _safe_label(name)}
    if len({x['actor_label'] for x in bindings.values()}) != len(bindings):
        raise DiscoveryError('Source actor names collide after normalization.')
    by_id = {str(x.get('asset_id')): x for x in csir.get('assets', [])}
    used_assets = {}
    for track in csir.get('tracks', []):
        if track.get('muted') is True:
            continue
        if track.get('ced_type') not in {'animation.track', 'audio.track'}:
            continue
        for section in track.get('sections', []):
            aid = str((section.get('payload') or {}).get('asset_id') or '')
            asset = by_id.get(aid)
            if not asset:
                continue
            name = str(asset.get('name') or '')
            if not name:
                raise DiscoveryError('Source referenced asset has no export name.')
            kind = 'Animations' if track.get('ced_type') == 'animation.track' else 'Audio'
            dest = target_dir + '/' + kind + '/CSAI_' + _safe_label(name)
            if name in used_assets and used_assets[name] != dest:
                raise DiscoveryError('Source asset name is used in incompatible track categories: ' + name)
            used_assets[name] = dest
    return {'sequence_asset_path': level.rsplit('/',1)[0] + '/LS_CS_' + fingerprint,
            'overwrite_sequence': False, 'entities': bindings, 'assets': used_assets}


def build_connection(unity_folder: str, unreal_folder: str, csir_path: str, level: str,
                     *, workspace: Path, worker: dict | None = None,
                     source_rights_confirmed: bool = False, unreal_project: str = '') -> dict:
    discovered = discover(unity_folder, unreal_folder, worker=worker, unreal_project=unreal_project)
    unity, unreal = discovered['unity'], discovered['unreal']
    if not unity or not unreal or not unreal.get('project'):
        raise DiscoveryError('Select one Unity and one Unreal project, then Scan again.')
    choice = next((x for x in unity['cutscenes'] if x['path'] == csir_path), None)
    if choice is None:
        raise DiscoveryError('The selected cutscene is not a verified export from this Unity project.')
    if level not in unreal['levels']:
        raise DiscoveryError('The selected level is not part of the chosen Unreal project.')
    csir_file = Path(csir_path)
    csir_bytes = csir_file.read_bytes()
    source = _read_json(csir_file)
    mapping = _source_mapping(source, csir_bytes, unreal['project'], level)
    # Keep generated mappings in the local Studio workspace, never Unity/Unreal project folders.
    key = hashlib.sha256((str(csir_file) + unreal['project'] + level).encode('utf-8') + csir_bytes).hexdigest()[:24]
    mapping_path = workspace / 'discovered-mappings' / (key + '.json')
    mapping_text = json.dumps(mapping, sort_keys=True, indent=2, ensure_ascii=False) + '\n'
    mapping_path.parent.mkdir(parents=True, exist_ok=True)
    if mapping_path.exists():
        if mapping_path.read_text(encoding='utf-8') != mapping_text:
            raise DiscoveryError('Generated mapping conflicts with an earlier immutable mapping.')
    else:
        with mapping_path.open('x', encoding='utf-8') as out:
            out.write(mapping_text)
    capture = ''
    for candidate in sorted(csir_file.parent.glob('*.cinetwin.behavior.json')):
        try:
            parsed = _read_json(candidate)
        except DiscoveryError:
            continue
        if (parsed.get('kind') == 'cinetwin.behavior_capture' and
            parsed.get('cutscene_id') == source.get('cutscene_id') and
            (parsed.get('source') or {}).get('csir_sha256') == hashlib.sha256(csir_bytes).hexdigest()):
            if capture:
                capture = ''  # Multiple valid captures: no arbitrary choice.
                break
            capture = str(candidate.resolve())
    return {'csir': str(csir_file), 'mapping': str(mapping_path),
            'target_project': unreal['project'], 'level_path': level,
            'unity_project': unity['folder'], 'source_scope': 'Assets',
            'auto_create_level': bool(unreal.get('new_level_required')),
            'capture': capture, 'source_rights_confirmed': bool(source_rights_confirmed),
            'skeletal_root_world_lock': False}
