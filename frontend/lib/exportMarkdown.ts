import type { Report } from "./reportTypes";

export function reportToMarkdown(report: Report): string {
  const lines: string[] = [];
  lines.push("# Paladins Config Analysis Report");
  lines.push("");
  lines.push(`_Mode: \`${report.mode}\`_`);
  lines.push("");
  lines.push("## Summary");
  lines.push("");
  lines.push(`- Actionable findings: **${report.summary.actionable_findings}**`);
  lines.push(`- Suppressed findings: ${report.summary.suppressed_findings}`);
  if (report.summary.highest_severity) {
    lines.push(`- Highest severity: **${report.summary.highest_severity}**`);
  }
  lines.push(`- Files accepted: ${report.summary.files_accepted}, skipped: ${report.summary.files_skipped}`);
  if (report.suppressed && report.suppressed.total > 0) {
    const s = report.suppressed;
    const parts: string[] = [];
    if (s.unknown_keys) parts.push(`${s.unknown_keys} unknown_key`);
    if (s.weak_typoed_keys) parts.push(`${s.weak_typoed_keys} weak typo`);
    if (s.uncertain_overrides) parts.push(`${s.uncertain_overrides} uncertain override`);
    if (s.array_compositions) parts.push(`${s.array_compositions} array composition`);
    if (s.info_noise) parts.push(`${s.info_noise} low-signal info`);
    lines.push(`- Suppressed: ${parts.join(", ")}`);
  }
  lines.push("");

  if (report.classification.length) {
    lines.push("## Classification");
    lines.push("");
    for (const c of report.classification) {
      lines.push(`- \`${c.filename_hint}\` -> **${c.classified_type}** (score ${c.score.toFixed(2)})`);
    }
    lines.push("");
  }

  if (report.skipped_files.length) {
    lines.push("## Skipped files");
    lines.push("");
    for (const s of report.skipped_files) {
      lines.push(`- \`${s.filename_hint}\` — ${s.reason}`);
    }
    lines.push("");
  }

  lines.push("## Ranked findings");
  lines.push("");
  if (!report.ranked_findings.length) {
    lines.push("_No findings._");
    lines.push("");
  } else {
    for (const f of report.ranked_findings) {
      lines.push(
        `### [${f.severity.toUpperCase()}/${f.confidence}] ${f.issue_type} — ${f.section}/${f.key}`
      );
      lines.push("");
      lines.push(`- Location: \`${f.location}\``);
      lines.push(`- Value: \`${f.value}\``);
      lines.push(`- Key status: ${f.key_status}`);
      if (f.effect.length) lines.push(`- Effect: ${f.effect.join(", ")}`);
      if (f.rationale) lines.push(`- Rationale: ${f.rationale}`);
      if (f.fix)
        lines.push(
          `- Fix: \`${f.fix.op}\` ${f.fix.section}/${f.fix.key} = \`${f.fix.value ?? ""}\``
        );
      if (f.ai_note) lines.push(`- AI note: ${f.ai_note}`);
      lines.push("");
    }
  }

  if (report.override_map.length) {
    lines.push("## Verified overrides");
    lines.push("");
    for (const o of report.override_map) {
      lines.push(
        `- ${o.section}/${o.key}: winner=${o.winner.file_type} (${o.winner.filename_hint}:${o.winner.line_no}) value=\`${o.winner.value}\` (source: ${o.precedence_source})`
      );
    }
    lines.push("");
  }
  if (report.uncertain_overrides.length) {
    lines.push("## Uncertain overrides (precedence not yet verified)");
    lines.push("");
    for (const u of report.uncertain_overrides) {
      const parts = u.candidates
        .map((c) => `${c.file_type} (${c.filename_hint}:${c.line_no}) = \`${c.value}\``)
        .join("; ");
      lines.push(`- ${u.section}/${u.key}: ${parts}`);
    }
    lines.push("");
  }
  if (report.array_compositions.length) {
    lines.push("## Array compositions");
    lines.push("");
    for (const a of report.array_compositions) {
      lines.push(
        `- ${a.section}/${a.key}: merged=\`[${a.merged.join(", ")}]\` sources=${a.sources
          .map((s) => `${s.file_type}:${s.line_no}`)
          .join(", ")}`
      );
    }
    lines.push("");
  }
  if (report.skipped_sections.length) {
    lines.push("## Skipped sections");
    lines.push("");
    for (const s of report.skipped_sections) {
      lines.push(`- ${s.file}/[${s.section}] — ${s.reason}`);
    }
    lines.push("");
  }

  const patchTypes = Object.keys(report.cleaned_patch);
  if (patchTypes.length) {
    lines.push("## Cleaned patch (rule-backed edits only)");
    lines.push("");
    for (const ft of patchTypes) {
      lines.push(`### ${ft}`);
      lines.push("");
      for (const op of report.cleaned_patch[ft]) {
        lines.push(
          `- [${op.rule_id}] \`${op.op}\` ${op.section}/${op.key} = \`${op.value ?? ""}\``
        );
      }
      lines.push("");
    }
  }

  if (report.confidence_notes.length) {
    lines.push("## Confidence notes");
    lines.push("");
    for (const n of report.confidence_notes) {
      lines.push(`- **${n.area}**: ${n.note}`);
    }
    lines.push("");
  }

  lines.push("## Meta");
  lines.push("");
  lines.push(`- AI enabled: ${report.meta.ai_enabled}`);
  lines.push(`- Rule pack: ${report.meta.rule_pack_version}`);
  lines.push(`- Registry: ${report.meta.registry_version}`);
  lines.push(`- Precedence: ${report.meta.precedence_version}`);
  lines.push(`- Elapsed: ${report.meta.elapsed_ms} ms`);
  if (report.meta.warnings.length) {
    lines.push(`- Warnings: ${report.meta.warnings.join("; ")}`);
  }
  lines.push("");

  return lines.join("\n");
}
