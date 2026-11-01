"""Local-only two-folder connection for CutSceneAI Studio.

Discovery is read-only. It uses saved Unity CSIR exports and actual Unreal maps;
never invents an exported cutscene, loads an editor, or changes engine projects.
A generated mapping is a proposal bound to an immutable CSIR/project identity.
"""
from __future__ import annotations

import hashlib
import json
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


def browse_project_folder(kind: str) -> str:
    """Choose a folder on the same Windows machine as the local companion.

    A child process owns Tk's GUI loop; it never runs in an HTTP worker thread.
    This cannot browse another machine's filesystem and is deliberately local.
    """
    if kind not in {'unity', 'unreal'}:
        raise DiscoveryError('Choose Unity or Unreal project.')
    if sys.platform != 'win32':
        raise DiscoveryError('Native folder selection is currently supported on Windows only.')
    title = 'Select Unity project folder (contains Assets)' if kind == 'unity' else 'Select Unreal project folder (contains .uproject)'
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
    selected = result.stdout.strip()
    if not selected:
        return ''  # Explicit cancellation, not a failed connection.
    directory = Path(selected).expanduser().resolve()
    if not directory.is_dir():
        raise DiscoveryError('Selected folder no longer exists.')
    return str(directory)


def scan_unity(folder: str) -> dict:
    root = Path(folder).expanduser().resolve()
    if not root.is_dir() or not (root / 'Assets').is_dir() or not (root / 'ProjectSettings').is_dir():
        raise DiscoveryError('Choose the Unity project root containing Assets/ and ProjectSettings/.')
    if not _inside(root / 'Assets', root):
        raise DiscoveryError('Unity Assets folder escapes the selected project.')
    dirs = [root / 'CutsceneAI' / 'Exports', root / 'CutSceneAI' / 'Exports', root / 'Exports']
    exports: list[Path] = []
    for directory in dirs:
        if not directory.is_dir() or not _inside(directory, root):
            continue
        for candidate in directory.glob('*.json'):
            if candidate.is_file() and candidate.stat().st_size <= 32 * 1024 * 1024:
                exports.append(candidate.resolve())
    scenes = []
    for path in sorted(set(exports), key=lambda p: str(p).lower()):
        try:
            obj = _read_json(path)
        except DiscoveryError:
            continue
        if (obj.get('schema_version') != '0.1.0' or
            (obj.get('source') or {}).get('engine') != 'unity' or
            not isinstance(obj.get('tracks'), list) or
            not isinstance(obj.get('entities'), list) or
            not obj.get('cutscene_id')):
            continue
        scenes.append({'path': str(path),
                       'name': str(obj.get('name') or obj.get('title') or path.stem),
                       'cutscene_id': str(obj['cutscene_id']),
                       'tracks': len(obj['tracks']), 'entities': len(obj['entities'])})
    return {'folder': str(root), 'cutscenes': scenes,
            'source_scope': 'Assets',
            'message': ('Found ' + str(len(scenes)) + ' exported cutscene(s).' if scenes else
                        'No exported CSIR found. In Unity, export the selected Timeline using Tools > CutsceneAI > Export Selected Timeline.')}


def scan_unreal(folder: str, worker: dict | None = None) -> dict:
    root = Path(folder).expanduser().resolve()
    if not root.is_dir():
        raise DiscoveryError('Choose an existing Unreal project folder.')
    projects = sorted((p.resolve() for p in root.glob('*.uproject') if p.is_file()),key=lambda p:p.name.lower())
    if len(projects) != 1:
        raise DiscoveryError(f'The Unreal project folder must contain exactly one .uproject file (found {len(projects)}).')
    if projects[0].parent != root:
        raise DiscoveryError('Unreal .uproject must belong to the selected project root.')
    content = root / 'Content'
    levels = []
    if content.is_dir():
        if not _inside(content, root):
            raise DiscoveryError('Unreal Content folder escapes the selected project.')
        # Avoid reading external repositories or arbitrary directories.
        for p in content.rglob('*.umap'):
            if not _inside(p, content):
                continue
            rel = p.relative_to(content).with_suffix('')
            if len(levels) >= 500:
                raise DiscoveryError('Unreal Content contains more than 500 maps. Narrow the project before connecting.')
            parts = rel.parts
            if all(re.fullmatch(r'[A-Za-z0-9_]+', x) for x in parts):
                levels.append('/Game/' + '/'.join(parts))
    levels = sorted(set(levels))
    active = ''
    if worker and worker.get('connected') and Path(str(worker.get('project') or '')).resolve() == projects[0]:
        active = str(worker.get('level') or '')
        if active.startswith('/Game/') and active not in levels:
            # Worker is authoritative only for a loaded /Game level.
            levels.append(active)
            levels.sort()
    return {'folder': str(root), 'project': str(projects[0]), 'levels': levels,
            'active_level': active,
            'message': ('Found ' + str(len(levels)) + ' saved or loaded Unreal map(s).' if levels else
                        'No map found. Save a level in Unreal first, then refresh discovery.')}


def discover(unity_folder: str, unreal_folder: str, *, worker: dict | None = None) -> dict:
    result = {'unity': None, 'unreal': None, 'ready': False}
    if unity_folder:
        result['unity'] = scan_unity(unity_folder)
    if unreal_folder:
        result['unreal'] = scan_unreal(unreal_folder, worker)
    result['ready'] = bool(result['unity'] and result['unreal'] and
                           result['unity']['cutscenes'] and result['unreal']['levels'])
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
                     source_rights_confirmed: bool = False) -> dict:
    discovered = discover(unity_folder, unreal_folder, worker=worker)
    unity, unreal = discovered['unity'], discovered['unreal']
    if not unity or not unreal:
        raise DiscoveryError('Select both project folders.')
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
            'capture': capture, 'source_rights_confirmed': bool(source_rights_confirmed),
            'skeletal_root_world_lock': False}
