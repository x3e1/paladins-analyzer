"use client";

import { useState } from "react";
import ReportView from "../components/ReportView";
import { reportToMarkdown } from "../lib/exportMarkdown";
import type { Report, ReportMode } from "../lib/reportTypes";

type Status = "idle" | "analyzing" | "done" | "error";

export default function Page() {
  const [files, setFiles] = useState<File[]>([]);
  const [pasted, setPasted] = useState<string>("");
  const [pastedName, setPastedName] = useState<string>("pasted.ini");
  const [mode, setMode] = useState<ReportMode>("actionable_only");
  const [report, setReport] = useState<Report | null>(null);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string>("");

  async function analyze() {
    setStatus("analyzing");
    setError("");
    const form = new FormData();
    for (const f of files) form.append("files", f);
    if (pasted.trim()) {
      const blob = new Blob([pasted], { type: "text/plain" });
      form.append("files", blob, pastedName || "pasted.ini");
    }
    try {
      const resp = await fetch(`/api/analyze?mode=${encodeURIComponent(mode)}`, {
        method: "POST",
        body: form,
      });
      if (!resp.ok) {
        setStatus("error");
        setError(`HTTP ${resp.status}: ${await resp.text()}`);
        return;
      }
      const json = (await resp.json()) as Report;
      setReport(json);
      setStatus("done");
    } catch (e) {
      setStatus("error");
      setError(String(e));
    }
  }

  function downloadMarkdown() {
    if (!report) return;
    const md = reportToMarkdown(report);
    const blob = new Blob([md], { type: "text/markdown" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "paladins-config-report.md";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div>
      <h1>Paladins .ini Config Analyzer</h1>
      <p style={{ opacity: 0.8 }}>
        Upload one or more Paladins config files, or paste config text. Classification
        is content-based, not filename-based — you may rename files before uploading.
      </p>

      <section style={{ marginTop: "1.5rem" }}>
        <h2>Upload files</h2>
        <input
          type="file"
          multiple
          accept=".ini,.txt,text/plain"
          onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
        />
        {files.length > 0 && (
          <ul>
            {files.map((f) => (
              <li key={f.name}>
                <code>{f.name}</code> ({f.size} bytes)
              </li>
            ))}
          </ul>
        )}
      </section>

      <section style={{ marginTop: "1.5rem" }}>
        <h2>Or paste content</h2>
        <label style={{ display: "block", marginBottom: "0.5rem" }}>
          Filename hint:{" "}
          <input
            value={pastedName}
            onChange={(e) => setPastedName(e.target.value)}
            style={{ padding: "0.25rem 0.5rem" }}
          />
        </label>
        <textarea
          value={pasted}
          onChange={(e) => setPasted(e.target.value)}
          placeholder="[Engine.Engine]&#10;bSmoothFrameRate=TRUE"
          style={{
            width: "100%",
            minHeight: 160,
            fontFamily: "monospace",
            fontSize: "0.875rem",
            background: "#151923",
            color: "#e4e7ee",
            border: "1px solid #2a3040",
            borderRadius: 4,
            padding: "0.5rem",
          }}
        />
      </section>

      <section style={{ marginTop: "1.5rem", display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
        <button
          onClick={analyze}
          disabled={status === "analyzing" || (files.length === 0 && !pasted.trim())}
          style={{
            padding: "0.6rem 1.25rem",
            background: "#2b7fff",
            color: "white",
            border: "none",
            borderRadius: 4,
            cursor: "pointer",
          }}
        >
          {status === "analyzing" ? "Analyzing…" : "Analyze"}
        </button>
        <label style={{ fontSize: "0.875rem", opacity: 0.85 }}>
          Report mode:{" "}
          <select
            value={mode}
            onChange={(e) => setMode(e.target.value as ReportMode)}
            style={{
              padding: "0.3rem 0.5rem",
              background: "#151923",
              color: "#e4e7ee",
              border: "1px solid #2a3040",
              borderRadius: 4,
            }}
          >
            <option value="actionable_only">actionable_only (default)</option>
            <option value="verbose">verbose</option>
            <option value="raw">raw</option>
          </select>
        </label>
        {report && (
          <button
            onClick={downloadMarkdown}
            style={{
              marginLeft: "0.75rem",
              padding: "0.6rem 1.25rem",
              background: "transparent",
              color: "#e4e7ee",
              border: "1px solid #2a3040",
              borderRadius: 4,
              cursor: "pointer",
            }}
          >
            Export Markdown
          </button>
        )}
      </section>

      {error && (
        <section style={{ marginTop: "1.5rem", color: "#ff6b6b" }}>
          <strong>Error:</strong> {error}
        </section>
      )}

      {report && (
        <section style={{ marginTop: "2rem" }}>
          <ReportView report={report} />
        </section>
      )}
    </div>
  );
}
