from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

JsonObject = Mapping[str, Any]


@dataclass(frozen=True)
class ProjectDescriptor:
    engine: str
    engine_version: str
    project_path: Path
    project_fingerprint: str


@dataclass(frozen=True)
class CutsceneDescriptor:
    cutscene_id: str
    name: str
    native_ref: str
    duration_seconds: float | None = None


@dataclass(frozen=True)
class CapabilityReport:
    adapter_name: str
    adapter_version: str
    engine: str
    engine_version: str
    supported_ced_ids: frozenset[str]
    conditional_ced_ids: frozenset[str] = field(default_factory=frozenset)
    unsupported_ced_ids: frozenset[str] = field(default_factory=frozenset)
    metadata: JsonObject = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractionResult:
    csir: JsonObject
    source_snapshot: JsonObject
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class StagingResult:
    transfer_id: str
    staging_ref: str
    created_refs: tuple[str, ...] = ()
    modified_refs: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReadbackResult:
    csir: JsonObject
    native_ref: str
    warnings: tuple[str, ...] = ()


class EngineAdapter(Protocol):
    """Stable boundary between CutsceneAI core and an engine implementation.

    Source-side extraction operations are read-only by default. Generation is
    target-side and must occur in a staging namespace/context until committed.
    """

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    def validate_project(self, project_path: Path) -> ProjectDescriptor: ...

    def discover_capabilities(self, project: ProjectDescriptor) -> CapabilityReport: ...

    def list_cutscenes(self, project: ProjectDescriptor) -> Sequence[CutsceneDescriptor]: ...

    def extract_cutscene(
        self,
        project: ProjectDescriptor,
        cutscene: CutsceneDescriptor,
    ) -> ExtractionResult:
        """Read-only extraction of an authoritative source cutscene."""
        ...

    def stage_generate(
        self,
        project: ProjectDescriptor,
        csir: JsonObject,
        transfer_plan: JsonObject,
    ) -> StagingResult:
        """Generate into a target staging context; do not overwrite unrelated assets."""
        ...

    def readback(
        self,
        project: ProjectDescriptor,
        staging: StagingResult,
    ) -> ReadbackResult:
        """Re-extract the generated target result for validation."""
        ...

    def commit_staging(self, project: ProjectDescriptor, staging: StagingResult) -> None: ...

    def rollback_staging(self, project: ProjectDescriptor, staging: StagingResult) -> None: ...
