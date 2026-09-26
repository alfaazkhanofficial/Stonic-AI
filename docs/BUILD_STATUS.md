# STONIC V3 build status

Version **0.3.0**. V3 adds a real agent core (native tool calling, a plan/act/verify/reflect goal loop, hybrid memory, procedural skills) and full-system PC control on top of the V2 foundation below. Gemini Live voice (`stonic/voicelive/`) is implemented and bridges into the agent core through the existing `ask_stonic` tool plus a `confirm_pending_action` tool for spoken approvals. See [docs/V3_SPEC.md](V3_SPEC.md) and [docs/V3_AUDIT.md](V3_AUDIT.md).

## Coverage

| Area | State | Evidence / boundary |
|---|---|---|
| Foundation | Implemented | Python/Node locks, typed contracts, SQLite, validated configuration, DPAPI secret storage, authenticated loopback API. |
| Intelligence | Implemented | xKiro complete/stream/planning/vision paths, bounded context, cancellation, explicit provider error classes and transient retry handling. |
| Voice | Implemented | Gemini Live speech-to-speech, echo guard, push-to-talk, barge-in; bridged into the V3 agent core (`ask_stonic`, `confirm_pending_action`). |
| Agent core (V3) | Implemented | Native tool calling, plan/act/verify/reflect goal loop, budgets, checkpoint/resume, combined confirmations, model router (agent-configured endpoint -> main provider fallback). |
| Full-system control (V3) | Implemented | Files, folders, apps (winget), registry, services and shell anywhere on disk; Recycle-Bin-first deletes with an undo journal; system-critical paths always confirmed. |
| Memory & skills (V3) | Implemented | Hybrid keyword+vector retrieval, episodic lessons (approval-gated), scheduled consolidation, procedural skills (propose/approve/run). |
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
