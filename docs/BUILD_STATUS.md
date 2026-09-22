# STONIC V2 build status

Version **0.2.0**. Current product direction is text-first. The previous always-listening voice/STT/TTS implementation has been removed intentionally, including its runtime lifecycle, settings, UI controls, dependencies, setup scripts and release assets.

## Coverage

| Area | State | Evidence / boundary |
|---|---|---|
| Foundation | Implemented | Python/Node locks, typed contracts, SQLite, validated configuration, DPAPI secret storage, authenticated loopback API. |
| Intelligence | Implemented | xKiro complete/stream/planning/vision paths, bounded context, cancellation, explicit provider error classes and transient retry handling. |
| Voice | Retired | No capture, VAD, STT, TTS, voice worker, voice models or voice API surface remains in the current product. Legacy voice settings are migrated away. |
| Computer / files / vision | Implemented | Observed Windows actions, workspace confinement, local capture/OCR and explicitly approved image upload. |
| Web / tasks / productivity | Implemented | Source-backed web modes, bounded plans, approvals, reminders, recurrence, calendar export, triggers and notifications. |
| Skills / gaming / developer | Implemented | Skill trust lifecycle, Steam discovery, conditional PresentMon and approved developer tools. |
| UI / packaging | Implemented with release gates | Electron/React workspace, settings, first-run, diagnostics and portable packaging. |

## Provider reliability change

The xKiro path now distinguishes credential rejection from rate limits, overload, upstream errors and connectivity failures. The saved DPAPI key is cached after a successful load, is never deleted on provider/network failure, and transient 429/500/502/503 plus connection-establishment failures receive bounded backoff retries. Streaming is retried only before visible output starts. xKiro `/usage` distinguishes daily free-token exhaustion from credential failure, and mid-stream SSE error frames are treated as provider failures instead of successful truncated output.

## Verification

Run the authoritative suites on the target Windows checkout after applying this build:

```powershell
.venv\Scripts\python.exe -m pytest -q
npm.cmd run typecheck
npm.cmd run build
npm.cmd run test:ui
node scripts\verify-desktop.mjs
```

The package script additionally verifies imports using only the bundled Python runtime. A clean-machine install, code signing, installer validation, DPI/display coverage and an independent security review remain external release gates.
