# Executable CED adapters

The CED names source concepts. A name or a candidate route does not itself
convert a Unity feature. `packages/studio/feature_dispatch.py` now provides a
code-installed handler registry that runs inside the deterministic Studio
planner. Each handler receives the source CSIR, the target mapping, and one
source occurrence. It must return a list of existing Unreal builder actions.

## Transfer contract

1. Export source evidence with a stable CED semantic and source occurrence ID.
   The separate Unity feature census is needed for native components omitted
   by CSIR. Discovery alone never counts as source behavior capture.
2. Implement a pure Python source adapter and register its exact semantic,
   source collection, native builder action kinds, name and version in
   `transfer_backend._installed_ced_handlers()`. Source files cannot name or
   import executable adapter modules. Preparation and the independent Unreal
   re-planner load the same installed registry.
3. The adapter returns only declared action kinds. The registry records the
   source location, source ID, semantic, adapter version and evidence gates on
   each action. It rejects false verification flags, non-JSON values and
   invalid Boolean/float property keys. The existing builder preflight still
   checks the actual Unreal actor, component, property and engine capability
   before scene mutation.
4. If an element needs a new native action kind, implement and test its Unreal
   builder and readback before adding that kind to `BUILDER_ACTIONS` and the
   handler declaration. A proposed route cannot make an unsupported action
   executable.
5. Generate into a new target namespace, save and reopen the level and
   sequence, then compare source-aligned behavior. Only independent native
   readback and behavior evidence can establish fidelity. A missing handler,
   source property, mapping or proof remains visible in CED coverage.

`event.state` is the installed example: when the user opts into the visual
fallback, the registry invokes `visual_activation.build_action` on the exact
Unity ActivationTrack and emits an Unreal `actor_visibility` action. It
retains `RENDER_ONLY_PARTIAL_UNVERIFIED` because Unity activation also affects
scripts and collision. Opting out emits no action.

The registry can bind assets, entities, tracks, sections, curves and
relationships. New adapters are reviewed code, not auto-generated Python from
an unknown source component or an AI suggestion. Existing
`scalar_property_mappings` and `component_property_mappings` remain the
declarative route for explicitly authored native scalar bindings; they also
require source evidence and target readback. The local discovery registry
records unknowns for developer review without changing CED or installing
handlers automatically.

## Native component adapters

The installed `HandlerRegistry` also accepts `ComponentAdapter` declarations
for native Unity census occurrences. A declaration binds an exact component
type and assembly to one versioned implementation. It declares supported
Unity and Unreal version families, the target class and action kind, required
source fields and dependencies, the conversion strategy, preflight, readback
and behavior requirements, and unsupported properties. Studio exposes this
data in the prepared candidate's adaptive component summary.

Register the implementation from the installed planner via
`adaptive_components.install_adapters`. The census cannot install modules or
pick an Unreal command. A planner receives the audited occurrence and its
unique mapped entity. Validate domain-specific field types and dependencies
inside the planner. Return one declared action, or raise
`ComponentEvidenceError` with a specific reason so unrelated features can
continue. Add tests for valid source evidence and malformed, incompatible,
unmapped or ambiguous occurrences. Adding a native action kind also requires
an allowlisted native handler, runtime preflight, and independent readback.

The initial registered adapter handles Unity `Light` shadow enable through
the existing editable Sequencer Boolean property track. A fresh census must
match the CSIR project's identity, engine version, scene scope and native
GameObject ID. Duplicate component IDs invalidate both occurrences.
`coverage-report.json` has the `component_transfer_ledger` keyed by census
index. It records planning without awarding native or behavior credit. After
opening the saved sequence in a different Unreal process, the existing Studio
persistence audit checks the owning native binding, property path and saved
channel keys for registered scalar actions. Capture rendered shadows at
matching times before claiming visual equivalence.

Previously saved source documents can be reused. Prepare a new candidate
after updating Studio because the worker recomputes the immutable plan and
coverage report with the installed registry.

### Unity package and custom component adapters

The feature census preserves the class, assembly version, registered package,
and package version of loaded types where Unity resolves their assembly
definition. The installed package inventory comes from the running Editor.
For scene MonoBehaviours, the source snapshot records visible serialized
Boolean, integer, float, string, enum, vector, color, array, and reference
fields and the enabled state. The reference evidence records the native
global ID and asset GUID when available. The report distinguishes missing
references and incomplete capture. Managed references and other unrecognized
field types retain their property path and native type for review. The
existing CSIR animation records provide native component type, property path
and keys for bindings discovered by the Unity clip exporter.

Install a package adapter by declaring the exact `source_type`,
`source_assembly`, `source_package`, and `source_package_versions` on a
`ComponentAdapter`. Registry eligibility requires agreeing version evidence
from the component and installed package inventory. Have the planner call
`source_surface_gap.source_capture_valid`, select just the typed fields its
semantics require, and validate their values and dependencies before returning
a declared action. If the action writes an Unreal Sequencer property with a
different UProperty name and Python alias, declare the original name as
`native_property_name`.

`tests/studio/test_serialized_component_adapters.py` contains a fixture
adapter for a test package's Boolean shadow intent. The test runs the same
component registration and planning path as Studio. The package version
mismatch, missing package, missing reference, and no-adapter cases remain
visible without a native action. Run a real-editor fixture before shipping any
production middleware adapter.

The agent summary receives adapter identifiers, CED semantics, versions, and
occurrence counts. Candidates, scripts, source fields, and asset paths stay
local. The guarded model executor continues to use its existing repair
allowlist. Static collision geometry is documented in
[Native collider geometry](../studio/NATIVE_COLLIDER_GEOMETRY.md).

## Current boundary

This is an executable extension framework, not a universal converter for the
735 CED semantic IDs. The repository has no live Unity/Unreal engine in CI;
tests can prove action contracts and fail-closed planning, while a successful
real transfer still needs project assets, engine import, saved readback and
source/target behavior evidence. Signal callbacks, collider runtime physics,
URP rendering, custom shaders and proprietary plugins require dedicated
source and target adapters before their warnings can honestly be resolved.
