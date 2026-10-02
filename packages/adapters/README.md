# Engine Adapter Contract

The executable protocol lives in `packages/adapters/interface.py`.

Every engine adapter is responsible for:

1. project validation and fingerprinting
2. engine/version detection
3. read-only project intelligence analysis (conventions, project settings, runtime APIs, evidence)
4. capability discovery using CED identifiers derived from that analysis
5. relevant-asset discovery
6. cutscene enumeration
7. read-only source extraction
8. native → canonical CED/CSIR conversion plus adaptive source context
9. target-native staging generation from CSIR + Resolved Mapping Dictionary + Transfer Plan
10. readback extraction of the staged/generated result
11. safe commit and rollback hooks

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

## Project-intelligence rule

Adapters prefer observed capability/settings evidence over assumptions based only on an engine version string. Version remains provenance and is used as a conditional selector only when a semantic difference is genuinely version-bound.

The core consumes Project Intelligence Profiles; it does not introspect engine APIs directly.
