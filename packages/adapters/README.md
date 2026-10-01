# Engine Adapter Contract

Every engine adapter is responsible for:

1. project validation
2. capability discovery
3. relevant-asset discovery
4. cutscene enumeration
5. read-only extraction
6. native → CED/CSIR conversion
7. CSIR → native staging generation
8. readback extraction
9. safe commit / rollback hooks

Core transfer logic must not import Unity- or Unreal-specific APIs.

## Source-side rule

Source operations are read-only by default. If runtime capture is required for evaluated transfer, it must run in an explicitly isolated/disposable context rather than mutating the authoritative source project.
