# Paladins .ini Config Analyzer — v1.0.0-beta.1

A deterministic, rule-based analyzer for **Paladins** (Hi-Rez UE3 fork, "Chaos" codename)
config files. Upload config files or paste contents, get a structured
technical report back: ranked issues, overrides, cleaned patch, Markdown
export.

No cargo-cult advice. Every finding is anchored in observable parser state
(keys, values, sections, files) plus a Paladins-specific rule set derived
from a verified clean install.

## Scope (strict)

- **Single game**: Paladins only. No other game will ever be added to this tool.
- **Six supported config types**, identified by content rather than filename:
  `ChaosEngine.ini`, `ChaosGame.ini`, `ChaosInput.ini`, `ChaosLightmass.ini`,
  `ChaosSystemSettings.ini`, `ChaosUI.ini`.
- Renamed files are fine. If you paste content saved as `foo.txt`, the
  classifier decides whether it is one of the six supported types.
- Files whose content does not match any supported type are warned and skipped.
- Fragments (single signature key, no required section) are classified and
  reported but do not participate in cross-file analysis or cleaned-patch output.
- Mixed dumps (sections from 2+ supported types in one file) are rejected; split
  them and re-upload.

## Quick start

Requires Docker (tested with Docker Desktop on Windows).

```bash
cp .env.example .env   # optional; defaults are fine
docker compose up --build
```

Then open <http://localhost:3000>.

For local development without Docker:

```bash
# backend
cd backend
python -m venv .venv
./.venv/Scripts/python -m pip install -e ".[dev]"
./.venv/Scripts/python -m uvicorn app.main:app --reload --port 8000

# frontend (in a second shell)
cd frontend
npm install
npm run dev
```

## Known limitations (v1-beta)

The analyzer deliberately **does not** claim knowledge it has not verified.
These are explicit limitations, not bugs:

- **Class-inheritance is not modeled.** UE3 uses UScript class hierarchies;
  a key set in `[Engine.GameEngine]` can shadow the same key set in
  `[Engine.Engine]` of the same file. v1-beta does not resolve this
  shadowing — it treats each section literally. A rule that matches a
  parent-class section will fire even when a child-class section
  overrides the effective value at runtime. Avoid relying on the tool's
  output for these specific keys until v1.1 ships inheritance modeling:
  `bSmoothFrameRate`, `MaxSmoothedFrameRate`, `MinSmoothedFrameRate`,
  `bUseTextureStreaming` in ChaosEngine.ini.
- **Cross-file precedence data is empty.** No verified Paladins-specific
  cross-file precedence has been recorded yet. Multi-file conflicts surface
  as `uncertain_override` findings at low confidence — never as confident
  overrides. The tool refuses to guess.
- **Platform/device-variant sections** (`SystemSettingsBucket1..5`,
  `SystemSettingsMobile`, `SystemSettingsIPhone*`, etc.) are treated as
  distinct sections from their bases. No conditional-activation logic.
- **AI explanation layer is disabled in v1-beta.** No LLM provider is
  wired; the `/meta` endpoint returns `ai_enabled: false` unconditionally.
  Architecture is in place (`app/ai/provider.py`), wiring arrives in v1.0.
- **No rate limiting.** The backend enforces per-request size/count caps
  but not per-IP throttling. Run behind a reverse proxy that rate-limits
  if you expose this publicly.
- **No persistence.** Uploaded bytes live only for the request lifetime.
  This is a feature (zero data retention, no database required) but also
  means there is no analysis history.
- **Rule packs for ChaosGame and ChaosUI are empty.** Those file types are
  parsed and classified; they just don't have deterministic rules yet.

## What has been verified

- Registry (`backend/app/data/paladins_known_keys.yaml`): 31 entries, all
  `status: confirmed` against a clean install of Paladins build
  **8.1.5838.0 (8.1)**, captured 2026-04-20 from the Steam launcher on
  Windows 11 Home 25H2 (OS build 26200.8246). Provenance is recorded
  per-entry.
- Classifier fingerprints for all six file types verified against the
  clean-install dump.
- 52 tests pass (`pytest -q`).

## Upload limits (defaults, configurable via env)

| Variable | Default | Meaning |
|---|---:|---|
| `PALADINS_ANALYZER_MAX_FILE_BYTES` | 1 MiB | per-file size cap |
| `PALADINS_ANALYZER_MAX_FILES` | 10 | files per request |
| `PALADINS_ANALYZER_MAX_TOTAL_BYTES` | 6 MiB | aggregate per request |
| `PALADINS_ANALYZER_PARSE_TIMEOUT` | 5 s | per-file parse timeout |

Oversized files, binary content, archives (ZIP/GZIP/7Z/TAR/RAR), and
non-UTF-8/UTF-16 encodings are rejected at the upload boundary with
structured `skipped_files` entries or `HTTP 400/413`.

## Reporting issues

Open a GitHub issue with:
1. The `meta` block from the report (rule pack / registry / precedence versions).
2. The input that triggered the problem (or a minimal reproduction).
3. What you expected vs. what you got.

**Do not paste real API keys, server credentials, or personal info** — config
files from multiplayer games can contain account identifiers.
