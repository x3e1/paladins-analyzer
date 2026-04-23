export type Severity = "info" | "warning" | "critical";
export type Confidence = "high" | "medium" | "low";
export type Effect =
  | "latency"
  | "fps"
  | "frame_pacing"
  | "stability"
  | "visuals"
  | "nothing";
export type KeyStatus = "confirmed" | "observed" | "unknown";

export interface Fix {
  op: "set" | "remove";
  section: string;
  key: string;
  value: string | null;
}

export interface Finding {
  id: string;
  file: string;
  filename_hint: string;
  section: string;
  key: string;
  value: string;
  severity: Severity;
  issue_type: string;
  effect: Effect[];
  location: string;
  fix: Fix | null;
  confidence: Confidence;
  key_status: KeyStatus;
  rationale: string;
  ai_note: string | null;
}

export interface ClassificationEntry {
  filename_hint: string;
  classified_type: string;
  score: number;
}

export interface SkippedFile {
  filename_hint: string;
  reason: string;
}

export interface SkippedSection {
  file: string;
  section: string;
  reason: string;
}

export interface EntryRef {
  file_type: string;
  filename_hint: string;
  line_no: number;
  value: string;
}

export interface OverrideRecord {
  section: string;
  key: string;
  winner: EntryRef;
  losers: EntryRef[];
  verified: boolean;
  precedence_source: "narrow" | "section_wide" | "unverified";
}

export interface UncertainOverrideRecord {
  section: string;
  key: string;
  candidates: EntryRef[];
}

export interface ArrayCompositionRecord {
  section: string;
  key: string;
  merged: string[];
  sources: EntryRef[];
}

export interface PatchOp {
  op: "set" | "remove";
  section: string;
  key: string;
  value: string | null;
  rule_id: string;
  rationale: string;
}

export interface Summary {
  files_accepted: number;
  files_skipped: number;
  sections: number;
  entries: number;
  findings: Record<Severity, number>;
  top_effects: Effect[];
  key_coverage: Record<KeyStatus, number>;
  actionable_findings: number;
  suppressed_findings: number;
  highest_severity: Severity | null;
}

export interface SuppressedSummary {
  total: number;
  unknown_keys: number;
  uncertain_overrides: number;
  array_compositions: number;
  weak_typoed_keys: number;
  info_noise: number;
}

export type ReportMode = "actionable_only" | "verbose" | "raw";

export interface ConfidenceNote {
  area: string;
  note: string;
}

export interface Meta {
  ai_enabled: boolean;
  rule_pack_version: string;
  registry_version: string;
  precedence_version: string;
  elapsed_ms: number;
  supported_types: string[];
  warnings: string[];
}

export interface Report {
  mode: ReportMode;
  summary: Summary;
  suppressed: SuppressedSummary;
  skipped_files: SkippedFile[];
  classification: ClassificationEntry[];
  ranked_findings: Finding[];
  override_map: OverrideRecord[];
  uncertain_overrides: UncertainOverrideRecord[];
  array_compositions: ArrayCompositionRecord[];
  skipped_sections: SkippedSection[];
  cleaned_patch: Record<string, PatchOp[]>;
  confidence_notes: ConfidenceNote[];
  meta: Meta;
}
