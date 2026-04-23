"""FastAPI surface.

Endpoints:
  - GET  /health  -> liveness/readiness probe
  - GET  /meta    -> rule pack/registry/precedence versions, feature flags
  - POST /analyze -> accept one or more files (multipart) or JSON pastes,
                     return a ``Report``.

Phase 1: AI layer is always disabled (no concrete provider wired). The
endpoint accepts an ``ai`` query flag but logs a warning and returns
``meta.ai_enabled: false`` regardless.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import time
from typing import Literal

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .ai.explainer import AIExplainer
from .engine.cleaned_patch import build_cleaned_patch
from .engine.cross_file import to_findings as cross_file_findings
from .engine.evaluator import evaluate, FindingData
from .engine.precedence import load_precedence
from .engine.registry import load_registry
from .engine.report_mode import ReportMode, highest_severity, partition
from .engine.resolver import resolve
from .engine.rules_loader import load_rules
from .parser.content_classifier import SUPPORTED_TYPES, classify
from .parser.ue3_ini import parse_bytes
from .parser.upload_policy import (
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    PARSE_TIMEOUT_SECONDS,
    RequestRejection,
    UploadRejection,
    enforce_request_limits,
    validate_upload,
)
from .schemas import (
    ArrayCompositionRecord,
    ClassificationEntry,
    ConfidenceNote,
    EntryRefModel,
    Finding,
    HealthResponse,
    Meta,
    MetaResponse,
    OverrideRecord,
    PatchOp,
    Report,
    SkippedFile,
    SkippedSection,
    SuppressedSummary,
    Summary,
    UncertainOverrideRecord,
)

DATA_DIR = pathlib.Path(__file__).parent / "data"
RULES_DIR = DATA_DIR / "rules"
REGISTRY_PATH = DATA_DIR / "paladins_known_keys.yaml"
PRECEDENCE_PATH = DATA_DIR / "verified_precedence.yaml"


def _hash_file(path: pathlib.Path) -> str:
    if not path.exists():
        return "missing"
    h = hashlib.sha256(path.read_bytes()).hexdigest()
    return h[:12]


def _hash_dir(path: pathlib.Path) -> str:
    if not path.exists():
        return "missing"
    h = hashlib.sha256()
    for f in sorted(path.glob("*.yaml")):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:12]


class _State:
    def __init__(self) -> None:
        self.rules = load_rules(RULES_DIR)
        self.registry = load_registry(REGISTRY_PATH)
        self.precedence = load_precedence(PRECEDENCE_PATH)
        self.rule_pack_version = _hash_dir(RULES_DIR)
        self.registry_version = _hash_file(REGISTRY_PATH)
        self.precedence_version = _hash_file(PRECEDENCE_PATH)
        # Phase 1: no provider wired.
        self.explainer = AIExplainer(provider=None)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    app.state.core = _State()
    yield


app = FastAPI(
    title="Paladins Config Analyzer",
    version="1.0.0-beta.1",
    lifespan=_lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    core: _State = app.state.core
    if not core.rules:
        return HealthResponse(status="degraded", reason="no rules loaded")
    return HealthResponse(status="ok")


@app.get("/meta", response_model=MetaResponse)
def meta() -> MetaResponse:
    core: _State = app.state.core
    return MetaResponse(
        ai_enabled=core.explainer.enabled,
        rule_pack_version=core.rule_pack_version,
        registry_version=core.registry_version,
        precedence_version=core.precedence_version,
        supported_types=list(SUPPORTED_TYPES),
        rules_loaded=len(core.rules),
        registry_entries=len(core.registry.entries),
        precedence_entries=len(core.precedence.entries),
    )


class PasteItem(BaseModel):
    filename_hint: str
    content: str


class AnalyzeBody(BaseModel):
    pastes: list[PasteItem] = []


@app.post("/analyze", response_model=Report)
async def analyze(
    files: list[UploadFile] | None = File(default=None),
    ai: Literal["true", "false"] | None = None,
    mode: ReportMode = "actionable_only",
) -> Report:
    """Analyze uploaded files.

    Phase 1 accepts ``files`` only (multipart/form-data). Pasted content
    may be sent as a file with the filename acting as the hint.
    """
    core: _State = app.state.core
    start = time.monotonic()

    if files is None:
        files = []

    warnings: list[str] = []
    if ai == "true" and not core.explainer.enabled:
        warnings.append(
            "AI layer requested but no LLM provider is configured; returning deterministic report only."
        )

    # Pre-read + per-request limit enforcement. Read every file eagerly so
    # we can apply aggregate caps before any parsing happens. Also avoids
    # partial work if a single oversized file is rejected.
    raw_uploads: list[tuple[str, bytes]] = []
    total_bytes = 0
    for f in files:
        data = await f.read()
        total_bytes += len(data)
        raw_uploads.append((f.filename or "<unnamed>", data))
    try:
        enforce_request_limits(len(raw_uploads), total_bytes)
    except RequestRejection as e:
        raise HTTPException(
            status_code=413 if e.reason == "request_too_large" else 400,
            detail={"reason": e.reason, "detail": e.detail,
                    "max_files": MAX_FILES,
                    "max_file_bytes": MAX_FILE_BYTES,
                    "max_total_bytes": MAX_TOTAL_BYTES},
        )

    # Parse + classify
    parsed = []
    skipped: list[SkippedFile] = []
    skipped_sections: list[SkippedSection] = []
    classification: list[ClassificationEntry] = []
    for filename_hint, data in raw_uploads:
        try:
            validate_upload(filename_hint, data)
        except UploadRejection as e:
            skipped.append(SkippedFile(filename_hint=filename_hint, reason=e.reason))
            continue
        try:
            doc = await asyncio.wait_for(
                asyncio.to_thread(parse_bytes, data, filename_hint),
                timeout=PARSE_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            skipped.append(SkippedFile(filename_hint=filename_hint, reason="parse_timeout"))
            continue
        except Exception as e:
            skipped.append(
                SkippedFile(filename_hint=filename_hint, reason=f"parse_error: {e}")
            )
            continue
        cls = classify(doc)
        classification.append(
            ClassificationEntry(
                filename_hint=doc.filename_hint,
                classified_type=cls.classified_type,
                score=cls.score,
            )
        )
        if cls.classified_type in {"Unsupported", "Mixed"}:
            reason = (
                "content did not match any supported type"
                if cls.classified_type == "Unsupported"
                else "file contains sections from multiple supported types; split into per-type files"
            )
            skipped.append(SkippedFile(filename_hint=doc.filename_hint, reason=reason))
            continue
        parsed.append((doc, cls))
        for sec in cls.foreign_sections:
            skipped_sections.append(
                SkippedSection(
                    file=cls.classified_type,
                    section=sec,
                    reason="not part of supported type's vocabulary",
                )
            )

    # Evaluate per-file rules and unknown/placebo pass.
    findings_data: list[FindingData] = []
    for doc, cls in parsed:
        findings_data.extend(
            evaluate(doc=doc, classification=cls, rules=core.rules, registry=core.registry)
        )

    # Cross-file resolver — Fragments excluded (done inside resolver via
    # classified_type filter).
    eligible_for_crossfile = [
        (doc, cls.classified_type)
        for doc, cls in parsed
        if cls.classified_type
        in {"ChaosEngine", "ChaosGame", "ChaosInput", "ChaosLightmass", "ChaosSystemSettings", "ChaosUI"}
    ]
    crossfile_result = resolve(eligible_for_crossfile, core.registry, core.precedence)
    findings_data.extend(cross_file_findings(crossfile_result))

    # Presentation filter: partition findings by the selected mode before
    # we bind them to the Pydantic Finding model. Suppressed findings are
    # counted (by reason) but not serialised.
    kept_findings, suppressed_counts = partition(findings_data, mode)
    suppressed_total = sum(suppressed_counts.values())
    highest_sev = highest_severity(kept_findings)

    # AI annotation runs on kept findings only (no notes for suppressed).
    ai_notes = core.explainer.annotate(kept_findings)
    ranked_findings: list[Finding] = []
    severity_order = {"critical": 0, "warning": 1, "info": 2}
    confidence_order = {"high": 0, "medium": 1, "low": 2}
    for f, note in zip(kept_findings, ai_notes):
        ranked_findings.append(
            Finding(
                id=f.id,
                file=f.file_type,
                filename_hint=f.filename_hint,
                section=f.section,
                key=f.key,
                value=f.value,
                severity=f.severity,
                issue_type=f.issue_type,
                effect=list(f.effect),
                location=f.location,
                fix=f.fix,
                confidence=f.confidence,
                key_status=f.key_status,
                rationale=f.rationale,
                ai_note=note,
            )
        )
    ranked_findings.sort(
        key=lambda r: (severity_order[r.severity], confidence_order[r.confidence])
    )

    # Summary. finding_counts tallies ALL computed findings (kept +
    # suppressed); actionable_findings counts only what passed the filter.
    finding_counts = {"critical": 0, "warning": 0, "info": 0}
    effects_tally: dict[str, int] = {}
    coverage = {"confirmed": 0, "observed": 0, "unknown": 0}
    total_sections = 0
    total_entries = 0
    for doc, _ in parsed:
        total_sections += len(doc.sections)
        for entries in doc.sections.values():
            total_entries += len(entries)
    for f in findings_data:
        finding_counts[f.severity] = finding_counts.get(f.severity, 0) + 1
        for eff in f.effect:
            effects_tally[eff] = effects_tally.get(eff, 0) + 1
        coverage[f.key_status] = coverage.get(f.key_status, 0) + 1
    top_effects = sorted(effects_tally.items(), key=lambda kv: -kv[1])
    summary = Summary(
        files_accepted=len(parsed),
        files_skipped=len(skipped),
        sections=total_sections,
        entries=total_entries,
        findings=finding_counts,
        top_effects=[e for e, _ in top_effects if e != "nothing"][:5],
        key_coverage=coverage,
        actionable_findings=len(kept_findings),
        suppressed_findings=suppressed_total,
        highest_severity=highest_sev,
    )

    suppressed_summary = SuppressedSummary(
        total=suppressed_total,
        unknown_keys=suppressed_counts["unknown_keys"],
        uncertain_overrides=suppressed_counts["uncertain_overrides"],
        array_compositions=suppressed_counts["array_compositions"],
        weak_typoed_keys=suppressed_counts["weak_typoed_keys"],
        info_noise=suppressed_counts["info_noise"],
    )

    # Cross-file records: always emit confident overrides; emit uncertain
    # and array_composition records only in verbose/raw modes (they carry
    # no actionable content and duplicate the kept-findings stream).
    override_records = [
        OverrideRecord(
            section=ov.section,
            key=ov.key,
            winner=EntryRefModel(**ov.winner.__dict__),
            losers=[EntryRefModel(**r.__dict__) for r in ov.losers],
            verified=ov.verified,
            precedence_source=ov.precedence_source,
        )
        for ov in crossfile_result.overrides
    ]
    if mode in ("verbose", "raw"):
        uncertain_records = [
            UncertainOverrideRecord(
                section=uc.section,
                key=uc.key,
                candidates=[EntryRefModel(**r.__dict__) for r in uc.candidates],
            )
            for uc in crossfile_result.uncertain_overrides
        ]
        composition_records = [
            ArrayCompositionRecord(
                section=ac.section,
                key=ac.key,
                merged=list(ac.merged),
                sources=[EntryRefModel(**r.__dict__) for r in ac.sources],
            )
            for ac in crossfile_result.array_compositions
        ]
    else:
        uncertain_records = []
        composition_records = []

    # Cleaned patch: always built from kept_findings so patch ops never
    # reflect suppressed or rejected rule matches.
    raw_patch = build_cleaned_patch(kept_findings)
    cleaned_patch = {
        ft: [PatchOp(**op) for op in ops] for ft, ops in raw_patch.items()
    }

    # Confidence notes (static v1 limitations).
    confidence_notes: list[ConfidenceNote] = [
        ConfidenceNote(
            area="precedence",
            note=(
                "Cross-file overrides are emitted only for narrowly verified Paladins "
                "precedence entries. Section-wide precedence is not supported in v1."
            ),
        ),
        ConfidenceNote(
            area="class inheritance",
            note="UE3 class-inheritance precedence is not modeled in v1.",
        ),
        ConfidenceNote(
            area="platform variants",
            note="Platform/device variant sections are treated as distinct sections in v1.",
        ),
    ]

    elapsed_ms = int((time.monotonic() - start) * 1000)
    # Skipped sections (foreign-to-classified-type section names) are
    # inventory noise in actionable_only mode; keep them only in
    # verbose/raw.
    visible_skipped_sections = skipped_sections if mode in ("verbose", "raw") else []
    return Report(
        mode=mode,
        summary=summary,
        suppressed=suppressed_summary,
        skipped_files=skipped,
        classification=classification,
        ranked_findings=ranked_findings,
        override_map=override_records,
        uncertain_overrides=uncertain_records,
        array_compositions=composition_records,
        skipped_sections=visible_skipped_sections,
        cleaned_patch=cleaned_patch,
        confidence_notes=confidence_notes,
        meta=Meta(
            ai_enabled=core.explainer.enabled,
            rule_pack_version=core.rule_pack_version,
            registry_version=core.registry_version,
            precedence_version=core.precedence_version,
            elapsed_ms=elapsed_ms,
            supported_types=list(SUPPORTED_TYPES),
            warnings=warnings,
        ),
    )
