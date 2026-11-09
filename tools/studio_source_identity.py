"""Deterministic Unity asset identity resolution for Studio staging.

Evidence precedence: explicit Unity project-relative path, asset GUID stored in
Unity .meta, exact filename, normalized logical name, content-equivalent copies.
When distinct source bytes remain ambiguous, fail closed. No model inference.
"""
from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from pathlib import Path

GUID = re.compile(r"^[0-9a-fA-F]{32}$")
UNITY_ID = re.compile(r"^unity-asset:([0-9a-fA-F]{32}):[-+]?\d+$")


def _tokens(text: str) -> str:
    words = [x.lower() for x in re.findall(r"[A-Za-z0-9]+", str(text))]
    words = [x for x in words if x not in {'a', 'b', 'rootmotion', 'animation', 'clip'}]
    result = ''.join(words)
    return result[:-3] if result.endswith('ing') and len(result) > 6 else result


def _metadata_guids(records: Iterable[Mapping]) -> set[str]:
    result: set[str] = set()
    for record in records:
        if not isinstance(record, Mapping):
            continue
        for key in ('guid', 'asset_guid', 'source_guid', 'unity_guid', 'asset_id'):
            val = str(record.get(key) or '')
            match = UNITY_ID.fullmatch(val) if key == 'asset_id' else None
            guid = match.group(1) if match else val
            if GUID.fullmatch(guid):
                result.add(guid.lower())
        for key in ('asset', 'source_asset', 'metadata'):
            child = record.get(key)
            if isinstance(child, Mapping):
                result.update(_metadata_guids((child,)))
    return result


def _metadata_paths_raw(records: Iterable[Mapping]) -> set[str]:
    result: set[str] = set()
    for record in records:
        if not isinstance(record, Mapping):
            continue
        for key in ('asset_path', 'source_path', 'unity_path', 'prefab_asset_path'):
            val = record.get(key)
            if isinstance(val, str) and val.strip().replace('\\', '/').startswith('Assets/'):
                result.add(val.replace('\\', '/'))
        for key in ('asset', 'source_asset', 'metadata'):
            child = record.get(key)
            if isinstance(child, Mapping):
                result.update(_metadata_paths_raw((child,)))
    return result


def _metadata_paths(records: Iterable[Mapping]) -> set[str]:
    return {path.casefold() for path in _metadata_paths_raw(records)}


def _unity_guid(file: Path) -> str | None:
    meta = file.with_name(file.name + '.meta')
    if not meta.is_file():
        return None
    # A .meta file is small in Unity; don't parse arbitrarily large untrusted files.
    with meta.open('rb') as handle:
        header = handle.read(131072)
    match = re.search(rb'(?:^|\n)guid:[ \t]*([0-9a-fA-F]{32})[ \t]*(?:\r?\n|$)', header)
    return match.group(1).decode('ascii').lower() if match else None


def resolve(files: Iterable[Path], logical_name: str, suffixes: set[str], *,
            project_root: Path, records: Iterable[Mapping] = (), aliases=()) -> dict:
    """Returns selected Path + evidence or unresolved candidate paths.

    Explicit identity can match a differently named file. No match or distinct
    conflicting matches never chooses the first path by enumeration order.
    """
    root = Path(project_root).resolve()
    candidates = sorted((Path(p).resolve() for p in files if Path(p).suffix.lower() in suffixes),
                        key=lambda x: str(x).casefold())
    for file in candidates:
        if not file.is_relative_to((root / 'Assets').resolve()):
            raise ValueError('Asset outside selected Unity project: ' + str(file))
    records = tuple(records)
    explicit_paths = _metadata_paths(records)
    explicit_guids = _metadata_guids(records)
    if explicit_paths or explicit_guids:
        # Prefer the on-disk spelling if the filesystem distinguishes case.
        # A case-folded fallback is safe only if it identifies one file.
        raw_paths = _metadata_paths_raw(records)
        by_path = [p for p in candidates if p.relative_to(root).as_posix() in raw_paths]
        if not by_path:
            by_path = [p for p in candidates if p.relative_to(root).as_posix().casefold() in explicit_paths]
        by_guid = [p for p in candidates if _unity_guid(p) in explicit_guids]
        # A path cannot override a contradictory Unity .meta GUID. The same
        # exported identity must point to the same asset in both sources.
        if by_path and explicit_guids:
            if any(_unity_guid(p) is None for p in by_path):
                return {'selected': None, 'strategy': 'UNITY_META_GUID_NOT_VERIFIABLE',
                        'candidates': [str(p) for p in sorted(set(by_path + by_guid))]}
            wrong_guid = [p for p in by_path
                          if (on_disk := _unity_guid(p)) is not None
                          and on_disk not in explicit_guids]
            if wrong_guid:
                return {'selected': None, 'strategy': 'IDENTITY_CONFLICT',
                        'candidates': [str(p) for p in sorted(set(by_path + by_guid))]}
        if by_path and by_guid and set(by_path).isdisjoint(by_guid):
            return {'selected': None, 'strategy': 'IDENTITY_CONFLICT',
                    'candidates': [str(p) for p in sorted(set(by_path + by_guid))]}
        authoritative = by_path or by_guid
        if authoritative:
            return _finalize(authoritative, 'UNITY_ASSET_PATH' if by_path else 'UNITY_META_GUID')
        return {'selected': None, 'strategy': 'IDENTITY_NOT_FOUND',
                'candidates': [str(p) for p in candidates]}
    wanted = [str(logical_name), *(str(a) for a in aliases)]
    exact = [p for p in candidates if p.stem.casefold() in {a.casefold() for a in wanted}]
    if exact:
        return _finalize(exact, 'EXACT_FILENAME')
    normalized = {_tokens(a) for a in wanted if _tokens(a)}
    matches = [p for p in candidates if _tokens(p.stem) in normalized]
    return _finalize(matches, 'NORMALIZED_FILENAME')


def _sha256_file(path: Path) -> bytes:
    # Stream large FBX files instead of loading multiple gigabytes into RAM.
    state = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            state.update(block)
    return state.digest()


def _finalize(matches: list[Path], strategy: str) -> dict:
    if not matches:
        return {'selected': None, 'strategy': 'NOT_FOUND', 'candidates': []}
    if len(matches) == 1:
        return {'selected': matches[0], 'strategy': strategy, 'candidates': [str(matches[0])]}
    # Two copied FBX files with the same bytes can be safely treated as the
    # same source asset. Different bytes mean different content, not a tie.
    hashes = {_sha256_file(p) for p in matches}
    if len(hashes) == 1:
        return {'selected': matches[0], 'strategy': strategy + '_CONTENT_IDENTICAL',
                'candidates': [str(p) for p in matches]}
    return {'selected': None, 'strategy': 'AMBIGUOUS_DISTINCT_CONTENT',
            'candidates': [str(p) for p in matches]}
