# STONIC V2 architecture

```text
Electron shell / React renderer
        │ constrained preload + authenticated loopback HTTP/SSE
        ▼
FastAPI application and lifecycle
        ├── CoreService ── StateEngine ── IntelligenceProvider (xKiro/OpenAI-compatible)
        ├── ToolRegistry ── PermissionGate ── typed ActionResult
        ├── TaskEngine ── approvals ── verification ── continuation/repair
        ├── SQLite Database ── records, FTS5, conversations, schedules, audit
        ├── EventBus/Scheduler/Triggers ── SSE + persistent notices
        ├── Windows/Browser/Gaming/Vision adapters
        └── Diagnostics ── live health, metrics and recovery
```

The voice/listening/TTS subsystem is intentionally absent from the current product. No microphone capture worker, VAD, speech recognizer, TTS engine, speech model downloader or voice API lifecycle runs at startup.

The renderer owns presentation state and local previews. It cannot open the database, read credentials, spawn arbitrary processes or perform OS actions. Preload exposes constrained window controls, notifications and approved capture paths. The native main process starts one owned backend and shuts down only its owned children.

Core conversations append user/assistant messages locally when saving is enabled. Provider prompts use bounded recent history and explicit context fields. Tool decisions are schema-validated. Safe tools run directly; higher-risk operations create jobs with exact inputs, single-use approvals and post-action verification.

The xKiro adapter holds a long-lived HTTP client. The DPAPI secret store caches a key only after successful decrypt/save. Bounded retries are applied to documented transient provider statuses and connection-establishment failures. Streaming retries stop permanently after the first visible token so a dropped stream cannot silently duplicate a generation. Provider/network failures never clear credentials. The free `/usage` endpoint is consulted after ambiguous 429s and during connection tests so daily free-token exhaustion is not misreported as a credential problem. SSE error frames are parsed explicitly after HTTP 200 streaming has begun.

Web research fails closed when source evidence is missing. Vision upload requires explicit image consent. Browser actions bind to an observed owned profile and target. Gaming reports only measured PresentMon evidence when available. Calendar integration exports RFC 5545; it does not synchronize an external calendar.

SQLite migrations and indexes keep records, sessions, jobs and schedules durable. Settings are schema-validated before persistence. Retired voice-setting keys are automatically removed from older databases during configuration loading so upgrades do not fail.

The portable release is assembled by allowlist into `release/`, with bundled runtimes and locked dependencies. User data, credentials, profiles, caches, tests and retired voice assets are excluded.
