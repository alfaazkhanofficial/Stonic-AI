# STONIC V2

STONIC V2 is a local Windows intelligence workspace. The current product is **text-first**: the voice/listening/TTS subsystem has been intentionally removed. The historical specification is preserved in [docs/MASTER_SPEC_REFERENCE.md](docs/MASTER_SPEC_REFERENCE.md), but its voice requirements are superseded by this product decision.

## Run it

Double-click `Start-Stonic.cmd` to build and launch the native desktop app. It starts the private loopback service, opens the Electron window, and stops its owned backend when the app closes.

For a new machine, install Node.js 22 and `uv`, run `Setup-Stonic.cmd`, then run `Start-Stonic.cmd`. Python is locked to 3.12.x and restored from `uv.lock`.

From `C:\Stonic`:

```powershell
npm.cmd run build
npm.cmd run desktop
npm.cmd run dev
.venv\Scripts\python.exe -m pytest -q
npm.cmd run test:ui
node scripts\verify-desktop.mjs
```

## Intelligence provider

STONIC uses the OpenAI-compatible xKiro endpoint. The saved key is encrypted with Windows DPAPI and cached in memory only after a successful decrypt/save, so a transient file or provider failure does not make a configured session suddenly behave as if the key disappeared. xKiro 429/500/502/503 responses and connection-establishment failures receive bounded retries with backoff. Streaming is retried only before any visible token is emitted, preventing duplicate answers after a partial stream.

Provider failures are classified separately from credential failures. A temporary upstream/network error does not delete or overwrite the saved key. The AI & Providers connection test uses the public xKiro model catalog plus the authenticated, free `/usage` endpoint. Free-token exhaustion is reported as a usage limit rather than as a missing key. Mid-stream xKiro error frames are surfaced explicitly instead of being mistaken for a successful truncated answer.

## Implemented product areas

The application includes typed contracts and state transitions; local SQLite records and memory; Windows context and computer control; local screen/image capture and OCR; xKiro text, planning, streaming and consented vision; source-backed web research; approved autonomous tasks; notes, tasks and reminders; proactive notifications; cancellation; exact-input approvals; local skills; Steam/PresentMon integration; developer tools; diagnostics/recovery; and the Electron/React workspace UI.

The calendar boundary is export-only. Browser control uses an owned Edge/Chrome profile and rejects stale/unobserved targets. OCR is local and English-only in the current adapter. STONIC does not fabricate web, tool, FPS or action results.

## Data and security

User records, conversations (when enabled), settings, schedules and audit events live under `data/` or `STONIC_DATA_DIR`. Test data stays under `.runtime/`. The loopback API uses a per-launch token plus origin/host checks. Electron uses sandboxed renderers, context isolation, no Node integration and constrained preload IPC. Tools use typed schemas, bounded permission levels and exact-input approvals.

## Release folder

After `npm.cmd run build`, run `.venv\Scripts\python.exe scripts\package-windows.py`. It creates `release\Stonic-V2-0.2.0-win-x64` from an explicit allowlist containing Electron, bundled Python/Node runtimes, locked packages, OCR and notices. It excludes `data/`, credentials, browser profiles, caches, `.env`, test artifacts and all retired voice models/runtimes.

See [docs/BUILD_STATUS.md](docs/BUILD_STATUS.md) for current verification state and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for service boundaries.

For test dependencies, install with: `pip install -e ".[test]"`.

## MADE BY ALFAAZ KHAN 