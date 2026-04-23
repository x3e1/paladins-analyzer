"""Pydantic request/response schemas for the FastAPI surface."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["info", "warning", "critical"]
Confidence = Literal["high", "medium", "low"]
Effect = Literal["latency", "fps", "frame_pacing", "stability", "visuals", "nothing"]
KeyStatus = Literal["confirmed", "observed", "unknown"]

IssueType = Literal[
    "dead_entry",
    "typoed_key",
    "unsupported_setting",
    "override",
    "uncertain_override",
    "array_composition",
    "conflict",
    "placebo",
    "unknown_key",
    "no_effect",
    "latency_risk",
    "frame_pacing_risk",
    "stutter_risk",
    "queue_depth",
    "resource_waste",
    "dangerous_streaming",
    "dangerous_visual",
    "dangerous_stability",
]


class Fix(BaseModel):
    op: Literal["set", "remove"]
    section: str
    key: str
    value: str | None = None


class Finding(BaseModel):
    id: str
    file: str
    filename_hint: str
    section: str
    key: str
    value: str
    severity: Severity
    issue_type: IssueType
    effect: list[Effect]
    location: str
    fix: Fix | None = None
    confidence: Confidence
    key_status: KeyStatus
    rationale: str
    ai_note: str | None = None


class ClassificationEntry(BaseModel):
    filename_hint: str
    classified_type: str
    score: float


class SkippedFile(BaseModel):
    filename_hint: str
    reason: str


class SkippedSection(BaseModel):
    file: str
    section: str
    reason: str


class EntryRefModel(BaseModel):
    file_type: str
    filename_hint: str
    line_no: int
    value: str


class OverrideRecord(BaseModel):
    section: str
    key: str
    winner: EntryRefModel
    losers: list[EntryRefModel]
    verified: bool
    precedence_source: Literal["narrow", "section_wide", "unverified"]


class UncertainOverrideRecord(BaseModel):
    section: str
    key: str
    candidates: list[EntryRefModel]


class ArrayCompositionRecord(BaseModel):
    section: str
    key: str
    merged: list[str]
    sources: list[EntryRefModel]


class PatchOp(BaseModel):
    op: Literal["set", "remove"]
    section: str
    key: str
    value: str | None = None
    rule_id: str
    rationale: str


class Summary(BaseModel):
    files_accepted: int
    files_skipped: int
    sections: int
    entries: int
    findings: dict[Severity, int]
    top_effects: list[Effect]
    key_coverage: dict[KeyStatus, int]
    # Added for actionable_only default:
    actionable_findings: int = 0
    suppressed_findings: int = 0
    highest_severity: Severity | None = None


class SuppressedSummary(BaseModel):
    total: int = 0
    unknown_keys: int = 0
    uncertain_overrides: int = 0
    array_compositions: int = 0
    weak_typoed_keys: int = 0
    info_noise: int = 0


ReportMode = Literal["actionable_only", "verbose", "raw"]


class ConfidenceNote(BaseModel):
    area: str
    note: str


class Meta(BaseModel):
    ai_enabled: bool = False
    rule_pack_version: str
    registry_version: str
    precedence_version: str
    elapsed_ms: int
    supported_types: list[str]
    warnings: list[str] = Field(default_factory=list)


class Report(BaseModel):
    mode: ReportMode = "actionable_only"
    summary: Summary
    suppressed: SuppressedSummary = Field(default_factory=SuppressedSummary)
    skipped_files: list[SkippedFile] = Field(default_factory=list)
    classification: list[ClassificationEntry] = Field(default_factory=list)
    ranked_findings: list[Finding] = Field(default_factory=list)
    override_map: list[OverrideRecord] = Field(default_factory=list)
    uncertain_overrides: list[UncertainOverrideRecord] = Field(default_factory=list)
    array_compositions: list[ArrayCompositionRecord] = Field(default_factory=list)
    skipped_sections: list[SkippedSection] = Field(default_factory=list)
    cleaned_patch: dict[str, list[PatchOp]] = Field(default_factory=dict)
    confidence_notes: list[ConfidenceNote] = Field(default_factory=list)
    meta: Meta


class MetaResponse(BaseModel):
    ai_enabled: bool
    rule_pack_version: str
    registry_version: str
    precedence_version: str
    supported_types: list[str]
    rules_loaded: int
    registry_entries: int
    precedence_entries: int


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    reason: str | None = None
