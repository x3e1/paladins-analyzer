"use client";

import type { Finding, Report } from "../lib/reportTypes";

const SEV_COLORS: Record<Finding["severity"], string> = {
  critical: "#ff6b6b",
  warning: "#f5a623",
  info: "#7aa6ff",
};

const SEV_LABELS: Record<Finding["severity"], string> = {
  critical: "CRITICAL",
  warning: "WARNING",
  info: "INFO",
};

function isNoise(r: Report): boolean {
  return r.mode === "actionable_only" && r.ranked_findings.length === 0;
}

function suppressedLine(r: Report): string | null {
  const s = r.suppressed;
  if (!s || s.total === 0) return null;
  const parts: string[] = [];
  if (s.unknown_keys > 0) parts.push(`${s.unknown_keys} unknown_key`);
  if (s.weak_typoed_keys > 0) parts.push(`${s.weak_typoed_keys} weak typo`);
  if (s.uncertain_overrides > 0) parts.push(`${s.uncertain_overrides} uncertain override`);
  if (s.array_compositions > 0) parts.push(`${s.array_compositions} array composition`);
  if (s.info_noise > 0) parts.push(`${s.info_noise} low-signal info`);
  return `Suppressed ${s.total} low-signal findings (${parts.join(", ")}).`;
}

export default function ReportView({ report }: { report: Report }) {
  const sev = report.summary.highest_severity;
  const actionable = report.summary.actionable_findings;
  const sup = suppressedLine(report);

  return (
    <div>
      {/* Compact summary */}
      <section
        style={{
          padding: "0.75rem 1rem",
          background: "#151923",
          borderRadius: 6,
          border: "1px solid #2a3040",
          marginBottom: "1rem",
        }}
      >
        <div style={{ display: "flex", flexWrap: "wrap", gap: "1.5rem", alignItems: "baseline" }}>
          <div style={{ fontSize: "1.5rem", fontWeight: 700 }}>
            {actionable} actionable{" "}
            {actionable === 1 ? "finding" : "findings"}
          </div>
          {sev && (
            <div style={{ color: SEV_COLORS[sev], fontWeight: 600 }}>
              highest: {SEV_LABELS[sev]}
            </div>
          )}
          <div style={{ opacity: 0.7, fontSize: "0.875rem" }}>
            mode: <code>{report.mode}</code>
          </div>
        </div>
        {sup && (
          <div style={{ marginTop: 8, fontSize: "0.9rem", opacity: 0.75 }}>
            {sup}
          </div>
        )}
      </section>

      {/* Classification — one line per file, only when useful */}
      {report.classification.length > 0 && (
        <section style={{ marginBottom: "1rem", fontSize: "0.875rem", opacity: 0.85 }}>
          {report.classification.map((c, i) => (
            <span key={i} style={{ marginRight: "1.25rem" }}>
              <code>{c.filename_hint}</code> →{" "}
              <strong
                style={{
                  color:
                    c.classified_type === "Unsupported" || c.classified_type === "Mixed"
                      ? "#ff9d9d"
                      : "inherit",
                }}
              >
                {c.classified_type}
              </strong>
            </span>
          ))}
        </section>
      )}

      {report.skipped_files.length > 0 && (
        <section style={{ marginBottom: "1rem" }}>
          <strong style={{ color: "#ff9d9d" }}>Skipped:</strong>{" "}
          {report.skipped_files.map((s, i) => (
            <span key={i} style={{ marginRight: "1rem", fontSize: "0.875rem" }}>
              <code>{s.filename_hint}</code> ({s.reason})
            </span>
          ))}
        </section>
      )}

      {/* Findings */}
      {actionable === 0 ? (
        <section
          style={{
            padding: "1rem",
            background: "#0f1720",
            border: "1px solid #2a3040",
            borderRadius: 6,
            color: "#7dd37d",
          }}
        >
          No actionable issues found. {isNoise(report) && sup ? `(${sup})` : ""}
        </section>
      ) : (
        <section>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {report.ranked_findings.map((f, i) => (
              <li
                key={i}
                style={{
                  marginBottom: "0.75rem",
                  padding: "0.75rem 1rem",
                  borderLeft: `4px solid ${SEV_COLORS[f.severity]}`,
                  background: "#151923",
                  borderRadius: 4,
                }}
              >
                <div style={{ display: "flex", gap: "0.75rem", alignItems: "baseline", flexWrap: "wrap" }}>
                  <span
                    style={{
                      fontSize: "0.75rem",
                      fontWeight: 700,
                      letterSpacing: "0.05em",
                      color: SEV_COLORS[f.severity],
                    }}
                  >
                    {SEV_LABELS[f.severity]}
                  </span>
                  <span style={{ fontWeight: 600 }}>{f.issue_type}</span>
                  <span style={{ opacity: 0.85 }}>
                    <code>
                      [{f.section}] {f.key}
                    </code>{" "}
                    = <code>{f.value}</code>
                  </span>
                </div>
                <div style={{ fontSize: "0.8rem", opacity: 0.7, marginTop: 2 }}>
                  <code>{f.location}</code>
                  {f.effect.length > 0 && <> · effect: {f.effect.join(", ")}</>}
                  {" · "}confidence: {f.confidence}
                </div>
                {f.rationale && (
                  <p style={{ margin: "8px 0 0", fontSize: "0.92rem", lineHeight: 1.4 }}>
                    {f.rationale}
                  </p>
                )}
                {f.fix && (
                  <p
                    style={{
                      margin: "6px 0 0",
                      fontSize: "0.9rem",
                      color: "#8de58d",
                    }}
                  >
                    <strong>Fix:</strong> {f.fix.op}{" "}
                    <code>
                      [{f.fix.section}] {f.fix.key}
                    </code>
                    {f.fix.value !== null && (
                      <>
                        {" "}= <code>{f.fix.value}</code>
                      </>
                    )}
                  </p>
                )}
                {f.ai_note && (
                  <p style={{ margin: "4px 0 0", fontSize: "0.9rem", fontStyle: "italic", opacity: 0.85 }}>
                    AI: {f.ai_note}
                  </p>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Verified overrides — always show if any, they are real */}
      {report.override_map.length > 0 && (
        <section style={{ marginTop: "1.25rem" }}>
          <h3 style={{ fontSize: "1rem", margin: "0 0 0.5rem" }}>Verified overrides</h3>
          <ul style={{ margin: 0, paddingLeft: "1.25rem" }}>
            {report.override_map.map((o, i) => (
              <li key={i} style={{ fontSize: "0.9rem" }}>
                <code>
                  [{o.section}] {o.key}
                </code>{" "}
                winner <strong>{o.winner.file_type}</strong> = <code>{o.winner.value}</code>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Cleaned patch — rule-backed edits only */}
      {Object.keys(report.cleaned_patch).length > 0 && (
        <section style={{ marginTop: "1.25rem" }}>
          <h3 style={{ fontSize: "1rem", margin: "0 0 0.5rem" }}>Cleaned patch</h3>
          {Object.entries(report.cleaned_patch).map(([ft, ops]) => (
            <div key={ft} style={{ marginBottom: "0.75rem" }}>
              <div style={{ fontSize: "0.85rem", opacity: 0.7 }}>{ft}</div>
              <pre
                style={{
                  margin: "4px 0 0",
                  padding: "0.5rem 0.75rem",
                  background: "#0b0d12",
                  border: "1px solid #2a3040",
                  borderRadius: 4,
                  fontSize: "0.85rem",
                  overflowX: "auto",
                }}
              >
                {ops
                  .map(
                    (op) =>
                      `; ${op.rule_id}\n[${op.section}]\n${op.key}=${op.value ?? ""}`
                  )
                  .join("\n\n")}
              </pre>
            </div>
          ))}
        </section>
      )}

      {/* Verbose-only panels */}
      {report.mode !== "actionable_only" && report.uncertain_overrides.length > 0 && (
        <section style={{ marginTop: "1.25rem" }}>
          <h3 style={{ fontSize: "1rem", margin: "0 0 0.5rem" }}>Uncertain overrides</h3>
          <ul style={{ margin: 0, paddingLeft: "1.25rem" }}>
            {report.uncertain_overrides.map((u, i) => (
              <li key={i} style={{ fontSize: "0.85rem" }}>
                <code>
                  [{u.section}] {u.key}
                </code>{" "}
                — {u.candidates.map((c) => `${c.file_type}=${c.value}`).join(", ")}
              </li>
            ))}
          </ul>
        </section>
      )}

      {report.mode !== "actionable_only" && report.array_compositions.length > 0 && (
        <section style={{ marginTop: "1.25rem" }}>
          <h3 style={{ fontSize: "1rem", margin: "0 0 0.5rem" }}>Array compositions</h3>
          <ul style={{ margin: 0, paddingLeft: "1.25rem" }}>
            {report.array_compositions.map((a, i) => (
              <li key={i} style={{ fontSize: "0.85rem" }}>
                <code>
                  [{a.section}] {a.key}
                </code>
                : [{a.merged.join(", ")}]
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* Meta footer — one compact line */}
      <footer
        style={{
          marginTop: "1.5rem",
          paddingTop: "0.75rem",
          borderTop: "1px solid #2a3040",
          fontSize: "0.75rem",
          opacity: 0.55,
        }}
      >
        rule {report.meta.rule_pack_version} · registry {report.meta.registry_version} ·
        precedence {report.meta.precedence_version} · {report.meta.elapsed_ms}ms
        {report.meta.warnings.length > 0 && (
          <> · <span style={{ color: "#f5a623" }}>warnings: {report.meta.warnings.join("; ")}</span></>
        )}
      </footer>
    </div>
  );
}
