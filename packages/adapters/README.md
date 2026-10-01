# Engine Adapter Contract

The executable protocol lives in `packages/adapters/interface.py`.

Every engine adapter is responsible for:

1. project validation and fingerprinting
2. engine/version detection
3. capability discovery using CED identifiers
4. relevant-asset discovery
5. cutscene enumeration
6. read-only source extraction
7. native → canonical CED/CSIR conversion
8. target-native staging generation from CSIR + Transfer Plan
9. readback extraction of the staged/generated result
10. safe commit and rollback hooks

Core transfer logic must not import Unity- or Unreal-specific APIs.

## Source-side invariant

Source operations are read-only by default.

If runtime capture is required for evaluated transfer, it must run in an explicitly isolated/disposable context rather than mutating the authoritative source project.

## Target-side invariant

Generation occurs in a staging context first. The adapter must expose enough information to identify everything created or modified by a transfer.

A failed transfer must be rollback-capable before unrelated target assets are touched.

## Capability reporting

An adapter reports CED identifiers as:

- supported
- conditional
- unsupported

This is consumed by the Transfer Readiness Advisor and Transfer Planner.

## Extraction contract

Extraction returns two representations:

1. canonical CSIR used by the transfer system
2. source snapshot preserving source-native information required for audit, debugging, or later adapter improvements

Semantic interpretation may enrich CSIR but must never erase authoritative extracted values.

## Readback rule

Successful target generation is not sufficient. The adapter must re-extract the generated target result so validation compares source ground truth against what actually exists in the target engine.
