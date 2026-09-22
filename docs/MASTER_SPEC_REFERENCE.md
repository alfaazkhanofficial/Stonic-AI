> **Current implementation override (September 2026):** This file is retained as a historical specification reference. The current STONIC V2 build intentionally removes the complete voice/listening/TTS subsystem. All voice, microphone, VAD, STT, TTS, wake-word, barge-in and always-listening directives below are superseded and non-operative.

# STONIC V2 — UNIFIED MASTER BUILD & UI SPECIFICATION

## Clean-Rebuild Product, Engineering, Voice & Locked Desktop UI Directive

> **Status:** FINAL / UNIFIED / IMPLEMENTATION SOURCE OF TRUTH  
> **Product:** STONIC V2  
> **Target:** Production-quality Windows desktop personal AI assistant  
> **Build model:** Clean rebuild from scratch, phase-by-phase, tested at every gate
> **Revision:** 2026-09-02 — locked configuration panel, compact startup splash, fully adaptive display sizing, hover-reveal window controls, and always-listening bottom capability controls
>
> **Role:** You are the lead architect, senior Python/AI engineer, Windows automation engineer, voice-AI engineer, systems engineer, security engineer, integration engineer, and senior desktop UI/UX implementation engineer responsible for delivering the complete **STONIC V2** application.
>
> **Mission:** Build STONIC V2 **from scratch** as one coherent, production-quality, voice-first personal AI assistant for Windows, then implement the locked desktop experience in this same specification over the real backend contracts. This is not a patch, migration, demo, mockup, or continuation of weak legacy architecture.
>
> **Source of truth:** The **19 finalized feature domains in Part I** remain the complete feature-domain scope. The **locked desktop UI in Part II is mandatory cross-cutting product scope**, but it is not a twentieth feature domain. Do not add, remove, silently downgrade, rename, reinterpret, or replace a finalized feature domain or the locked UI concept unless the user explicitly changes the specification.
>
> **Critical build rule:** Treat previous STONIC implementations as legacy reference material only. Build a clean modular foundation. Once a new V2 phase is genuinely completed and tested, preserve that working V2 behavior while implementing later phases; do not rebuild a working new subsystem merely to make another layer easier.

---

# 0. UNIFIED PRECEDENCE & LOCKED TECHNOLOGY DECISIONS

If two inherited passages conflict, apply this precedence order:

1. This unified preamble and explicit locked decisions below.
2. The more specific requirement over the more generic requirement.
3. Part I backend/core requirements for operational behavior and system contracts.
4. Part II locked UI requirements for presentation, interaction, and desktop UX.

The following decisions override older generic/fallback wording:

- **Primary STT:** NVIDIA Nemotron 3.5 ASR Streaming 0.6B, INT8, through sherpa-onnx/ONNX Runtime.
- **Primary VAD:** Silero VAD through sherpa-onnx.
- **Default STT streaming profile:** 160 ms low-latency model/profile.
- **STT languages:** English + Hindi + Hindi-English code-switched Hinglish; `auto` language mode is the production default unless a session/user preference pins a language.
- **STT fallback:** faster-whisper multilingual small INT8, lazy-loaded only for bounded fallback/recovery.
- **Primary TTS:** Supertonic 3, local ONNX Runtime, one consistent STONIC voice identity.
- **Prohibited TTS:** Edge TTS, Piper TTS, Pocket-TTS, Windows SAPI / Windows built-in speech.
- **No production speech quota:** normal STT/TTS must run locally and must not depend on a paid per-character/per-minute speech API.
- **Voice activation:** STONIC is continuously ready for speech while the application is running and microphone permission is available. There is no wake-word requirement and no push-to-talk requirement in the production interaction path.
- **Microphone control semantics:** the Home `MIC` control is a live status/configuration action, never an on/off toggle. Clicking it must not stop the owned microphone pipeline.
- **UI scope:** the purple/obsidian STONIC Core + on-demand glass-panel desktop UI in Part II is mandatory V2 scope.
- **Configuration surface:** an on-demand `CONFIG` entry must exist in the quick-access grid and open the real Configuration panel. Every supported user-facing behavior that is safe and meaningful to customize must be represented there; fake or nonfunctional controls are prohibited.
- **Startup experience:** every normal desktop launch begins with a small, centered STONIC splash window whose primary label is **`INITIALIZING STONIC`** and whose stage/progress comes from the real startup lifecycle. The main window appears only after critical startup has reached `READY` or an honest bounded `DEGRADED` result.
- **Adaptive desktop sizing:** the complete UI must adapt to the current monitor work area, window size, aspect ratio, and Windows DPI/scaling. It must never ship with clipped content, controls outside the viewport, or a composition that becomes unusably tiny on a supported display.
- **Window controls:** the frameless main window uses a top-right hover/focus reveal zone for minimize, maximize/restore, and close. The controls remain keyboard-accessible and native-window reliable even while visually hidden.
- **No fake integration:** a UI surface, provider badge, transcript, task, tool state, or diagnostic indicator counts only when driven by a real execution path.

Do not silently substitute another speech engine because installation is easier. If a locked engine cannot run, diagnose it, enter an honest degraded state, and continue implementing/recovering according to this specification.

---

# PART I — CORE PRODUCT & ENGINEERING SPECIFICATION

# 1. PRODUCT IDENTITY

**Name:** STONIC V2

**Core vision:**

> STONIC is a voice-first, context-aware personal AI that can understand the user, understand the user's computer and environment, remember useful context, reason about goals, plan tasks, safely operate the computer, use external tools, and communicate naturally.

STONIC should feel like one coherent personal AI system, not a collection of unrelated scripts.

It must be:

- Voice-first
- Context-aware
- Conversational
- Proactive when useful
- Tool-capable
- Computer-capable
- Memory-enabled
- Vision-enabled
- Secure
- Extensible
- Reliable
- Modular
- Maintainable
- Fast enough for natural interaction
- Able to recover gracefully from failures

STONIC is voice-first, and the **locked STONIC V2 desktop UI in Part II of this unified specification is mandatory V2 scope**. The UI is a presentation/client layer over clean, documented backend contracts; it must never become a second intelligence implementation or force the core to depend on UI internals. The new core must not depend on V1 backend internals, and the UI must connect only to real V2 services, state, events, tools, and provider contracts.

---

# 2. FINALIZED V2 FEATURE DOMAINS

These 19 sections are **FINALIZED**, and the content within them is also finalized:

1. Advanced Intelligence Core
2. Long-Term Memory
3. Context Awareness
4. Full Computer Control
5. Computer Vision
6. Voice V2
7. Real-Time Web Intelligence
8. Autonomous Task Engine
9. Personal Productivity
10. Proactive STONIC
11. Conversation Interruption
12. Security Layer
13. Plugin / Skill Architecture
14. Gaming Intelligence
15. Developer Mode
16. STONIC State Engine
17. Personalization & Learning Engine
18. Event & Trigger Engine
19. Self-Diagnostics & Recovery

Do not treat these as optional ideas.

The feature plan is closed. Any additional work described later in this document is **engineering infrastructure required to implement these finalized features correctly**, not a new product feature domain.

---

# 3. CLEAN-REBUILD CONTRACT

STONIC V2 must be rebuilt on a fresh foundation.

## 3.1 Zero-legacy rule

- Do not patch the old STONIC backend into V2.
- Do not preserve weak architecture for compatibility.
- Do not copy old modules unless their design is independently justified and rewritten to fit the new architecture.
- Do not rely on old global state, ad-hoc routers, keyword chains, or tightly coupled tool logic.
- Do not reuse broken workarounds merely because they already exist.
- Existing code may be inspected only to understand expected behavior, assets, configuration names, or external integration details.
- If the old project is present, create the rebuild in a new clean project root unless the user explicitly instructs otherwise.
- Never destroy or overwrite the legacy project just to create V2.

## 3.2 No-placeholder rule

Do not claim a capability is implemented when it is only:

- a stub
- a TODO
- a fake success response
- a hard-coded demo
- an unconnected class
- an untested code path
- a UI-only indicator with no backend behavior

A capability counts as implemented only when its real execution path exists, returns structured results, handles failure, and passes its acceptance checks.

## 3.3 Build for integration from day one

Every subsystem must have explicit interfaces and typed contracts so that voice, intelligence, memory, state, tools, permissions, events, and diagnostics can work together without circular dependencies.

Prefer dependency injection and provider interfaces over importing concrete implementations throughout the codebase.

## 3.4 Preserve product behavior, redesign implementation freely

The 19 feature domains define **what STONIC must do**. This prompt intentionally allows the internal implementation to be redesigned when a cleaner solution exists.

---

# 4. ENGINEERING FOUNDATIONS

These are mandatory implementation foundations for the finalized feature set. They are not additional feature domains.

## 4.1 Project structure

Use a clear package structure with separate responsibilities for at least:

```text
stonic/
├── app/                  # application bootstrap / API + desktop integration boundary
├── core/                 # orchestration, intelligence contracts, shared models
├── state/                # centralized runtime state machine
├── context/              # context collection and context snapshots
├── memory/               # persistent memory and retrieval
├── voice/                # always-listening capture, VAD, STT, TTS, interruption
├── vision/               # screenshots, OCR/vision adapters, screen understanding
├── tools/                # tool registry and common execution contracts
├── automation/           # Windows, mouse, keyboard, browser, files
├── web/                  # search/research/deep-research pipeline
├── tasks/                # autonomous task planning/execution
├── productivity/         # reminders, timers, todos, notes, schedule state
├── events/               # timers, triggers, event bus, proactive rules
├── security/             # permissions, confirmation, audit
├── skills/               # plugin/skill system and built-in skills
├── personalization/      # approved learned preferences
├── diagnostics/          # health checks, recovery, subsystem status
├── providers/            # model/STT/TTS/search/vision provider adapters
├── storage/              # databases, repositories, migrations
├── config/               # typed configuration and environment loading
├── desktop/              # STONIC V2 desktop UI client, shell, panels, state bridge
└── tests/                # unit, integration, acceptance tests
```

The exact tree may change, but these responsibilities must remain separated.

## 4.2 Typed contracts

Define structured models for important system boundaries, including:

- user input
- transcripts
- intent/goal interpretation
- plans and plan steps
- tool calls
- tool results
- permission requests
- confirmation decisions
- memory records
- context snapshots
- state transitions
- events
- notifications
- task progress
- health checks
- final assistant responses

Do not pass loosely structured dictionaries everywhere when a stable schema should exist.

## 4.3 Standard action result

All tools and automated actions should return a consistent result shape conceptually similar to:

```text
ActionResult
├── success
├── status
├── message
├── data
├── error
├── retryable
├── verification
├── permission_level
└── metadata
```

The intelligence layer must reason from real results rather than assuming an action succeeded.

## 4.4 Configuration and secrets

- Centralize configuration.
- Define a typed, versioned configuration schema with category, key, type, default, validation, restart requirement, sensitivity, supported choices, and user-facing help metadata.
- Validate configuration at startup.
- Keep secrets out of source code.
- Support environment variables and local configuration files where appropriate.
- Expose safe read/update/reset operations to the Part II Configuration panel; the UI must not edit `.env` or internal files directly.
- Persist user changes atomically and keep the last known-valid configuration recoverable.
- Distinguish changes that apply live from changes that require a service or application restart.
- Emit configuration-change events so affected services and UI surfaces update without stale duplicated state.
- Support per-setting reset, per-category reset, and full reset with confirmation; export/import must omit or securely handle secrets.
- Provide a safe example configuration with no real credentials.
- Fail with useful diagnostics when required configuration is missing.
- Do not expose a control merely because a key exists internally. Security invariants, unsupported experiments, and implementation-only values remain internal unless intentionally promoted to the public schema.

## 4.5 Logging and observability

Use structured logs with subsystem, event, severity, timestamps, correlation/task identifiers where relevant, and sanitized error details.

Log enough to diagnose failures without logging secrets or unnecessary sensitive user content.

## 4.6 Concurrency and cancellation

Voice capture, TTS, tools, events, long-running tasks, and web work may overlap. Use explicit async/concurrency boundaries and cancellation tokens/events rather than unmanaged background threads.

Long operations must be cancellable where practical.

## 4.7 Storage discipline

Persistent state must use explicit repositories/schemas and migrations where appropriate. Avoid unrelated JSON files scattered throughout the project.

Backups, corruption handling, and safe recovery should be considered for important persistent state.

## 4.8 Provider abstraction

External or replaceable services must sit behind interfaces/adapters, including where applicable:

- LLM / reasoning provider
- embeddings provider
- STT provider
- TTS provider
- always-listening/voice-lifecycle controller
- vision/OCR provider
- web/search provider
- browser automation provider

A provider failure must not require rewriting the intelligence core.

---

# 5. ARCHITECTURAL PRINCIPLE

Use a layered, modular architecture:

```text
                         USER
                          │
             ┌────────────┴────────────┐
             │                         │
          VOICE                       UI
             │                         │
 STT / VAD / Always-listening     Visual State
             │                         │
             └────────────┬────────────┘
                          │
                   INPUT / CONTEXT
                          │
                 ┌────────▼────────┐
                 │ INTELLIGENCE    │
                 │     CORE        │
                 └────────┬────────┘
                          │
        ┌─────────────────┼──────────────────┐
        │                 │                  │
      MEMORY           PLANNER            STATE
        │                 │                  │
        └─────────────────┼──────────────────┘
                          │
                    TOOL / SKILL
                       ENGINE
                          │
       ┌──────────┬───────┼───────┬──────────┐
       │          │       │       │          │
      WEB      WINDOWS   FILES   VISION   SPECIALIZED
                                             SKILLS
                          │
                    ACTION VERIFIER
                          │
                     RESULT / TTS
                          │
                         USER
```

The exact implementation may differ, but responsibilities must remain clearly separated.

---

# 6. SECTION 1 — ADVANCED INTELLIGENCE CORE

STONIC must evolve beyond keyword-based command execution.

Required capabilities:

- Context-aware conversations
- Multi-turn reasoning
- Intent understanding
- Follow-up understanding
- Goal understanding
- Task decomposition
- Planning before execution
- Tool selection
- Tool argument generation
- Error recovery
- Result verification
- Self-check before consequential actions
- Natural clarification when information is missing
- Explanation of failures
- Conversation continuity

Example:

```text
User: Open Chrome.
STONIC: Opens Chrome.

User: Search YouTube.
STONIC: Understands Chrome is the relevant context.

User: Open the third result.
STONIC: Understands the third result from the current browser context.
```

Separate:

1. Understanding
2. Planning
3. Tool selection
4. Execution
5. Verification
6. Response generation

Never blindly execute an ambiguous or high-impact action.

---

# 7. SECTION 2 — LONG-TERM MEMORY

STONIC must have persistent memory across sessions.

### User Memory
- Name
- Preferences
- Preferred workflows
- Frequently used apps
- Useful stable information

### Conversation Memory
- Important previous discussions
- Relevant decisions
- Project context

### Task Memory
- Incomplete tasks
- Previous attempts
- Task status
- Useful recurring workflows

### Environmental Memory
- Installed applications
- Common folders
- Computer configuration
- Useful system information

Memory must be selective. Do not indiscriminately store everything.

Required controls:

- Remember useful information
- Forget information
- Update incorrect memory
- Inspect relevant memory
- Avoid sensitive/unnecessary retention
- Clear memory when explicitly requested

Example:

```text
User: Remember that I prefer Chrome.
STONIC: Stores the preference.

User: Forget that I prefer Chrome.
STONIC: Removes that memory.
```

Use persistent storage with clear schemas, metadata, timestamps, indexing, and relevance-based retrieval.

Do not dump the entire memory database into every prompt.

---

# 8. SECTION 3 — CONTEXT AWARENESS

STONIC must understand the user's current environment.

Context sources:

- Active application
- Active window
- Current task
- Current conversation
- Screen state
- System state
- Recent commands
- Recent tool results
- Current STONIC mode

Examples:

```text
User: Close this.
STONIC: Understands what "this" refers to.

User: Fix this error.
STONIC: Uses visible application/screen context.

User: Continue.
STONIC: Uses current task context.
```

Represent context as structured state, not only raw text.

---

# 9. SECTION 4 — FULL COMPUTER CONTROL

STONIC must safely operate Windows.

Capabilities:

- Launch applications
- Close applications
- Switch applications
- Keyboard input
- Mouse movement
- Mouse clicks
- Scrolling
- Hotkeys
- Clipboard operations
- File operations
- Browser control
- Windows settings interaction where appropriate
- Window management
- Task execution

Example:

```text
"Go to YouTube, search for Minecraft survival ideas, open the third result."
```

Execution:

```text
Understand
→ Plan
→ Open browser
→ Navigate
→ Search
→ Identify result
→ Click
→ Verify
→ Report
```

Application launching must use reliable Windows application resolution instead of blindly passing spoken names to `cmd.exe`.

Every automated action must return an execution result.

---

# 10. SECTION 5 — COMPUTER VISION

Provide a vision layer capable of understanding the visible computer environment.

Capabilities:

- Screenshot capture
- Screenshot understanding
- OCR
- UI element recognition
- Visible text extraction
- Error detection
- Document understanding
- Code understanding
- Browser page understanding
- Game HUD/context recognition

Example:

```text
User: What's wrong with this code?

STONIC:
→ Inspects visible editor
→ Identifies error
→ Explains it
→ Suggests a fix
```

Activate vision according to context and permissions rather than unnecessarily transmitting screenshots continuously.

---

# 11. SECTION 6 — VOICE V2

Voice is a **PRIMARY capability** and a latency-critical subsystem. The production voice path is fully local for speech recognition and speech synthesis so normal STONIC voice interaction has no per-request speech quota and does not require a cloud speech service.

## 11.1 Locked voice technology stack

The production implementation must use these defaults unless the user explicitly changes this specification later:

### Primary STT

- **Model:** NVIDIA **Nemotron 3.5 ASR Streaming 0.6B**
- **Runtime:** **sherpa-onnx / ONNX Runtime**
- **Precision:** **INT8**
- **Default streaming profile:** **160 ms chunk model** for low conversational latency
- **Language mode:** `auto` by default, with per-stream language hints available
- **Required languages:** English, Hindi, and Hindi-English code-switched **Hinglish**
- **Execution:** local/on-device; do not require a hosted STT API for normal operation
- **License handling:** preserve the applicable model/runtime license notices in distribution

Nemotron must be loaded once and kept warm while the voice subsystem is active. Do not recreate the recognizer for every utterance.

### VAD / endpointing

- **Primary VAD:** **Silero VAD through sherpa-onnx**
- Use a rolling microphone ring buffer with pre-roll so the first syllable is not clipped.
- Endpointing must combine VAD state, minimum speech duration, trailing silence, maximum utterance duration, and the current always-listening conversation/activity state.
- VAD must continue to support barge-in/interruption detection while STONIC is speaking, without feeding STONIC's own speaker output back into normal command recognition.

### STT fallback

- **Fallback:** `faster-whisper` with a multilingual **small** model using **INT8 CPU** inference.
- It is a **lazy fallback**, not a second recognizer that runs concurrently with Nemotron.
- Load it only when the primary recognizer cannot initialize, becomes unhealthy, or a bounded recovery policy explicitly routes an utterance to fallback.
- Unload or release it when practical after recovery so RAM is not permanently consumed by two ASR engines.

Do not use a browser Web Speech API or a paid/cloud STT API as the production default.

### Primary TTS

- **Model:** **Supertonic 3**
- **Runtime:** local **ONNX Runtime**
- **Execution:** fully local/on-device for normal speech
- **Output:** 44.1 kHz production playback path
- **Languages:** English and Hindi are required; Hinglish must be handled through language-aware text normalization/chunking
- **Voice identity:** use one locked STONIC voice/style by default so the assistant has a consistent sonic identity
- **Default speech speed:** tune around natural conversational speed; expose a user setting rather than hard-coding one pace for every response
- **Expression tags:** may be used sparingly when they improve naturalness; never turn normal assistant responses into theatrical narration

**Explicitly prohibited production TTS engines:**

- Edge TTS
- Piper TTS
- Pocket-TTS
- Windows SAPI / Windows built-in speech

Do not silently reintroduce any of these as a fallback.

Supertonic's open-source repository is no longer expected to receive ongoing official development after its 2026 archival notice. Therefore STONIC must pin and package the tested local runtime/model assets it legally redistributes, record checksums/versions, and avoid a runtime dependency on a remote repository being available.

### TTS failure behavior

If Supertonic cannot recover after bounded reinitialization:

1. mark TTS as `DEGRADED` or `FAILED` as appropriate;
2. keep STONIC's intelligence/UI operational;
3. present the response as text in the UI;
4. expose a clear diagnostic reason;
5. do **not** fall back to Edge, Piper, Pocket-TTS, or SAPI.

## 11.2 Always-listening activation and conversation behavior

STONIC must be **always listening and immediately ready for intentional user speech** while the desktop application is running, the voice subsystem is healthy, and Windows microphone permission is available.

Locked behavior:

- no wake word is required;
- no push-to-talk control is required;
- the microphone capture/VAD path starts during application initialization and remains owned by STONIC until shutdown, device loss, permission loss, or a recoverable voice-service restart;
- an inactivity timeout may clear short-lived conversational context, but it must not disable the microphone or return to wake-word mode;
- clicking the Home `MIC` control opens voice configuration/status and must not mute, pause, or stop capture;
- phrases such as `stop` or `cancel` stop the current speech/action where applicable; they do not silently turn off always-listening mode;
- fully ending microphone capture occurs only when STONIC exits, Windows permission/device availability prevents capture, or a required recovery operation temporarily restarts the owned audio service.

Desired behavior:

```text
APPLICATION START
     ↓
CONTINUOUS LISTENING READY
     ↓
User speaks naturally
     ↓
VAD + endpointing + streaming STT
     ↓
Intent / confidence / safety gate
     ↓
Response or approved action
     ↓
CONTINUOUS LISTENING READY
```

Always listening does **not** mean always saving or uploading audio. Raw microphone audio stays in bounded in-memory buffers unless the user explicitly invokes a diagnostic/recording workflow that explains and obtains the required permission.

To avoid reacting to television, other people, or unrelated ambient speech without reintroducing a wake word:

- use VAD, speaker-output reference/echo suppression, transcript confidence, recent conversation context, direct-address/command likelihood, and foreground-user interaction signals where available;
- ignore or ask for clarification on low-confidence or obviously unrelated fragments;
- never transform uncertain background speech into a consequential action;
- route sensitive or consequential actions through the existing confirmation and permission layer regardless of confidence;
- preserve a clear visible `LISTENING`, `PROCESSING`, `DEGRADED`, `PERMISSION DENIED`, or `DEVICE UNAVAILABLE` status.

During normal capture, processing, execution, and TTS playback, one centralized voice controller must prevent duplicate pipelines and self-trigger loops. The separate barge-in path remains active while STONIC speaks so the user can say `stop`, `cancel`, or an immediate new command without a wake word.

## 11.3 Audio capture pipeline

Use one owned microphone pipeline rather than several libraries competing for the device.

Conceptual flow:

```text
MICROPHONE
   ↓
16 kHz mono float/PCM capture
   ↓
rolling pre-roll ring buffer
   ↓
VAD / endpointing
   ↓
Nemotron streaming recognizer
   ↓
partial transcript events
   ↓
final transcript
   ↓
normalization / confidence checks
   ↓
intelligence core
```

Requirements:

- application-lifecycle capture start/stop must be explicit, centralized, observable, and cancellable during shutdown/recovery;
- normal utterance boundaries must be controlled by VAD/endpointing rather than repeatedly opening and closing the hardware device;
- the continuous capture service must begin during startup before the main window reports `READY`;
- device disconnect/reconnect must be handled;
- microphone errors must not crash the full app;
- keep enough pre-roll to preserve utterance beginnings;
- avoid unnecessary audio copies;
- do not write raw microphone audio to disk by default;
- expose microphone level/amplitude events to the UI at a throttled rate;
- sanitize or suppress transcript logging according to privacy settings.

## 11.4 STT behavior

Required:

- True streaming/online recognition for the primary engine
- Partial/transient transcript updates
- Final transcript event
- Voice activity detection
- Noise-tolerant endpointing
- Pre-roll
- Silence detection
- Command segmentation
- Automatic language detection
- English
- Hindi
- Hinglish / Hindi-English code switching
- Short commands
- Natural sentences
- Punctuation/capitalization where the model provides them
- Transcript cleanup without changing the user's meaning
- Proper nouns/app-name adaptation through post-processing/context where practical
- Robust failure handling
- Cancellation

STT must avoid clipping the beginning of commands.

Do not wait for a long fixed recording window after the user has clearly finished speaking.

### Transcript normalization

Normalization may:

- trim duplicated streaming fragments;
- normalize obvious spacing/punctuation artifacts;
- map known application/product names using a controlled vocabulary;
- remove language tags from the model output when the runtime exposes them separately;
- preserve the semantic content of the user's speech.

Normalization must **not** hallucinate missing commands or rewrite uncertain speech into a more consequential action.

## 11.5 Hinglish strategy

Hinglish is a first-class input mode, not an edge case.

- Start with Nemotron language mode `auto` for mixed Hindi-English speech.
- Preserve English technical terms and application names when spoken inside Hindi sentences.
- Keep language metadata separate from transcript text where possible.
- If auto-detection is repeatedly unstable in one session, the voice controller may pin a user-selected language preference for that session.
- Post-processing may normalize script/transliteration for internal understanding, but must retain the original transcript for debugging/inspection when privacy settings allow.

## 11.6 TTS response pipeline

STONIC must not wait for an entire long LLM answer before beginning speech when safe chunking is possible.

Preferred flow:

```text
LLM RESPONSE STREAM
   ↓
spoken-text formatter
   ↓
safe phrase/sentence chunker
   ↓
Supertonic 3 synthesis
   ↓
small ordered audio queue
   ↓
playback
```

Requirements:

- begin synthesis from stable phrase/sentence boundaries;
- preserve ordering;
- keep the audio queue shallow so interruption is immediate;
- cancel queued/in-flight synthesis on barge-in when practical;
- avoid speaking markdown syntax, raw URLs, code fences, or UI-only metadata;
- pronunciation normalization for numbers, abbreviations, app names, and Hinglish where appropriate;
- proper completion detection based on actual playback completion;
- normal command routing must be gated against STONIC's own playback until speech finishes or is intentionally interrupted;
- never write every TTS response to permanent disk just to play it;
- reuse the loaded model/session across responses.

## 11.7 Speech formatter

Before TTS, produce a separate `spoken_text` representation from the richer UI response.

Examples of content that normally should not be spoken verbatim:

- markdown formatting characters;
- long source URLs;
- raw JSON/tool payloads;
- code blocks unless the user explicitly asks STONIC to read them;
- long tables;
- diagnostic identifiers.

The UI may show more detail than TTS speaks.

## 11.8 Interruption / barge-in

While STONIC is speaking:

1. maintain a lightweight microphone/VAD interruption path;
2. detect intentional user speech or stop/cancel intent;
3. stop playback quickly;
4. cancel queued TTS chunks;
5. move state through `SPEAKING → INTERRUPTED → LISTENING`;
6. feed the new utterance to STT immediately through the same always-listening controller.

Use acoustic echo handling/no-self-trigger safeguards so speaker output is not treated as a normal new command.

## 11.9 Performance targets

Treat these as engineering targets, not permission to fake results:

- audio capture and VAD must remain lightweight enough to run continuously for the full application lifetime;
- partial STT text should update at conversational cadence rather than only after full utterance completion;
- the 160 ms Nemotron profile is the default low-latency choice;
- model initialization should happen during subsystem startup/warm-up, not on the first spoken command;
- first audible TTS should begin as soon as a stable response chunk is available;
- UI animation/rendering must never take priority over microphone, STT, LLM-stream, or TTS processing.

Instrument at least:

- speech-start detection latency;
- speech-end/endpoint latency;
- first partial transcript latency;
- final transcript latency;
- LLM first-token latency;
- TTS first-audio latency;
- end-to-end speech-to-first-audio latency;
- interruption-to-silence latency.

## 11.10 Voice diagnostics

Health checks must independently report:

- microphone device/capture
- VAD
- Nemotron model/runtime loaded
- STT stream health
- STT fallback availability
- always-listening controller/lifecycle
- ambient-speech/command-confidence gate
- echo suppression and no-self-trigger path
- Supertonic model/runtime loaded
- playback device
- interruption path
- end-to-end loopback test where practical without storing sensitive audio

A healthy UI indicator must come from these real checks, not merely from a loaded frontend component.

---

# 12. SECTION 7 — REAL-TIME WEB INTELLIGENCE

Dedicated web/research capability.

### Quick Search
For direct current information.

### Research
For multi-source information gathering.

### Deep Research
For complex comparisons and investigations.

Capabilities:

- Search web
- Read relevant pages
- Extract information
- Compare sources
- Summarize
- Identify conflicts
- Cite sources where appropriate
- Handle current/time-sensitive information

Requests requiring current information must route to web intelligence.

Malformed model output must not silently turn a web request into generic conversation.

Use structured-output validation and retry/repair logic.

---

# 13. SECTION 8 — AUTONOMOUS TASK ENGINE

Support multi-step goals.

Example:

```text
User:
Prepare everything I need for tomorrow's STONIC video.
```

Possible plan:

```text
1. Find project files
2. Check script
3. Check thumbnail
4. Check assets
5. Identify missing items
6. Create task summary
7. Report results
```

Required:

- Task creation
- Task planning
- Step execution
- Dependencies
- Progress tracking
- Failure handling
- Retry logic
- Verification
- Completion reporting
- Cancellation
- Confirmation for consequential actions

Do not silently perform high-impact actions.

---

# 14. SECTION 9 — PERSONAL PRODUCTIVITY

Capabilities:

- Reminders
- Timers
- To-do list
- Calendar integration architecture
- Notes
- Task tracking
- Recurring tasks
- Daily briefing

Example:

```text
Good morning, Sir.
You have three tasks today.
```

Productivity state must persist.

---

# 15. SECTION 10 — PROACTIVE STONIC

STONIC can initiate useful notifications when appropriate.

Examples:

- "Your download has finished."
- "Your disk space is getting low."
- "The build failed."
- "You've been debugging the same error for a while. Want me to inspect it?"

Proactive behavior must have permission controls.

User-configurable:

- What STONIC may report
- Notification frequency
- Quiet periods
- Sensitive categories
- Disable all proactive behavior

Do not spam the user.

---

# 16. SECTION 11 — CONVERSATION INTERRUPTION

Support natural interruption.

Example:

```text
STONIC:
"Sir, I found three..."

User:
"Stop."

STONIC:
Immediately stops speaking.
```

The user must be able to interrupt active speech immediately, with no activation phrase.

After interruption, return to the appropriate state and accept the next command.

---

# 17. SECTION 12 — SECURITY LAYER

Use permission levels.

### Level 0 — Safe

- Answer questions
- Search
- Read screen

### Level 1 — Normal

- Open applications
- Create files
- Normal automation

### Level 2 — Sensitive

- Delete files
- Change important settings
- Send external messages
- Other consequential actions

Requires confirmation.

### Level 3 — Critical

Requires explicit authorization.

Security principles:

- Least privilege
- Explicit confirmation
- Never expose secrets
- Never execute destructive commands without authorization
- Keep credentials outside source code
- Use environment variables/secure storage
- Log security-relevant actions
- Provide permission visibility

---

# 18. SECTION 13 — PLUGIN / SKILL ARCHITECTURE

STONIC must be extensible.

Conceptual:

```text
STONIC
├── Core
├── Memory
├── Voice
├── Vision
├── Browser
├── Windows
├── Files
├── Search
└── Skills
    ├── YouTube
    ├── Spotify
    ├── Coding
    ├── Gaming
    ├── School
    └── Productivity
```

Each skill should define:

- Metadata
- Capabilities
- Tools
- Permission requirements
- Input schema
- Output schema
- Error handling
- Optional configuration

Adding a skill must not require rewriting the core intelligence engine.

---

# 19. SECTION 14 — GAMING INTELLIGENCE

Capabilities:

- Detect current game
- Launch games
- Gaming mode
- FPS monitoring
- Performance monitoring
- Game-specific settings where feasible
- Screenshot analysis
- Gaming-session awareness
- Voice commands during gaming

Examples:

```text
"Launch GTA."
"What's my FPS?"
"Enable gaming mode."
```

Keep gaming capabilities safe.

---

# 20. SECTION 15 — DEVELOPER MODE

Developer Mode is first-class.

Capabilities:

- Inspect project structure
- Read files
- Analyze stack traces
- Diagnose errors
- Explain exceptions
- Search documentation
- Suggest fixes
- Edit code with permission
- Run tests
- Inspect logs
- Diagnose dependencies
- Refactor code
- Verify fixes

Preferred workflow:

```text
Read error
   ↓
Find relevant files
   ↓
Understand cause
   ↓
Propose fix
   ↓
Ask permission when needed
   ↓
Apply fix
   ↓
Run test
   ↓
Verify
   ↓
Report
```

Avoid unnecessary whole-project rewrites.

---

# 21. SECTION 16 — STONIC STATE ENGINE

Maintain centralized structured state.

Example:

```text
USER
├── Current activity
├── Current app
├── Current task
├── Current mode
└── Relevant preferences

SYSTEM
├── CPU
├── RAM
├── Disk
├── Network
└── Battery

STONIC
├── Initializing
├── Ready / Passive Listening
├── Capturing Utterance
├── Understanding
├── Thinking
├── Executing
├── Speaking
├── Interrupted
└── Degraded
```

Avoid contradictory copies of state.

The Core's calm visual `IDLE` presentation must not be confused with the voice service being asleep. While the application is healthy, `voice.capture_state` remains ready/listening even when `core.activity_state` is visually idle. Keep these orthogonal fields explicit rather than overloading one enum.

Suggested transitions:

```text
INITIALIZING
→ READY_LISTENING
→ CAPTURING_UTTERANCE
→ UNDERSTANDING
→ THINKING
→ EXECUTING
→ SPEAKING
→ READY_LISTENING
```

and:

```text
SPEAKING
→ INTERRUPTED
→ CAPTURING_UTTERANCE
→ READY_LISTENING
```

Prevent invalid state transitions.

---

# 22. SECTION 17 — PERSONALIZATION & LEARNING ENGINE

STONIC must become increasingly personalized without storing unnecessary or sensitive information.

Required capabilities:

- Stable user preferences
- Preferred communication style
- Preferred applications and workflows
- Per-application preferences
- User corrections
- Learned workflow preferences
- "Do not do this again" preferences
- Optional learning from repeated behavior
- Explicit approval before storing a new long-term preference when appropriate

Example:

```text
User: No, when I say "open YouTube", use Chrome.

STONIC:
→ Understands the correction
→ Asks whether to remember the preference when appropriate
→ Stores the preference
→ Uses it in future sessions
```

Personalization must remain separate from raw conversation memory.

Memory stores useful information; personalization uses approved information to influence how STONIC behaves.

STONIC must allow the user to inspect, correct, disable, or forget learned preferences.

Do not silently infer sensitive personal traits or store unnecessary behavioral data.

---

# 23. SECTION 18 — EVENT & TRIGGER ENGINE

STONIC must be able to react to relevant events, not only direct user commands.

Event sources may include:

- Timers
- Reminders
- Scheduled tasks
- Application state changes
- Download completion
- Build/test completion
- System conditions
- Battery state
- Disk-space thresholds
- Network changes
- Task completion/failure
- Other authorized system events

Event flow:

```text
EVENT
  ↓
EVENT FILTER
  ↓
PERMISSION / QUIET-HOURS CHECK
  ↓
CONTEXT CHECK
  ↓
STONIC DECISION
  ↓
NOTIFY / ACT / IGNORE
```

Examples:

```text
Download finished
→ Notify the user if permitted.

Build failed
→ Notify the user and offer to inspect the error.

Disk space becomes low
→ Notify the user with the relevant information.

Timer completed
→ Announce the timer result.
```

Requirements:

- Persistent scheduled events
- Event registration
- Event cancellation
- Event history
- Duplicate-event protection
- Permission controls
- Quiet hours
- Notification throttling
- Safe event handling
- Recovery after restart
- No unnecessary notifications

STONIC must never use proactive events as an excuse to spam the user.

---

# 24. SECTION 19 — SELF-DIAGNOSTICS & RECOVERY

STONIC must be able to inspect its own operational health and recover safely from subsystem failures.

Provide a self-diagnostic capability such as:

```text
"STONIC, run a system check."
```

The diagnostic system should be able to check:

- Microphone
- Speakers
- Always-listening controller
- Ambient/self-trigger safeguards
- VAD
- STT
- TTS
- AI/model availability
- Network
- Memory database
- Configuration
- Required dependencies
- Tool availability
- File permissions
- Browser availability
- Vision subsystem
- Integration health

Example:

```text
STONIC SYSTEM CHECK

✓ Microphone
✓ Always listening
✓ Echo/self-trigger guard
✓ STT
✓ Memory
✓ Windows tools
✓ File tools
⚠ Web intelligence — network unavailable
✓ Supertonic TTS

Overall: Operational with limited web capability.
```

Recovery principles:

1. Detect the failing subsystem.
2. Diagnose the failure.
3. Attempt safe recovery where feasible.
4. Retry with bounded limits.
5. Activate a fallback when available.
6. Isolate the failed subsystem.
7. Keep the rest of STONIC running.
8. Explain the limitation clearly to the user.
9. Record the failure in structured logs.
10. Never repeatedly retry a failing operation indefinitely.

Example:

```text
Supertonic TTS fails
→ Detect failure
→ Attempt bounded local reinitialization
→ Mark voice output DEGRADED if recovery fails
→ Present the answer through the UI without switching to a prohibited TTS engine
→ Keep the rest of STONIC operational
```

STONIC should expose a clear health state such as:

- HEALTHY
- DEGRADED
- RECOVERING
- FAILED

A single subsystem failure must not crash the entire assistant.

---

---

# 25. CROSS-SUBSYSTEM EXECUTION CONTRACT

For a normal user request, prefer this end-to-end pipeline:

```text
INPUT
  ↓
VOICE/TEXT NORMALIZATION
  ↓
CONTEXT SNAPSHOT
  ↓
UNDERSTANDING / GOAL MODEL
  ↓
PLAN OR DIRECT RESPONSE DECISION
  ↓
PERMISSION CHECK
  ↓
TOOL / SKILL EXECUTION
  ↓
ACTION RESULT
  ↓
VERIFICATION
  ↓
STATE / MEMORY / TASK UPDATE
  ↓
RESPONSE GENERATION
  ↓
TTS / UI RESULT
```

Not every request requires every step, but no subsystem should bypass security, state consistency, or result verification merely for convenience.

Important rules:

- Conversation should not directly call arbitrary operating-system code.
- Tools should not directly write conversational responses.
- TTS should not decide task logic.
- Memory retrieval should not become an uncontrolled prompt dump.
- State changes should go through the state engine.
- Sensitive actions should go through the permission layer.
- Proactive actions should go through event, permission, quiet-hours, and context checks.
- Diagnostics should be able to query subsystem health without tightly coupling to their internals.

---

# 26. FRESH-BUILD IMPLEMENTATION PLAN

Build STONIC in dependency order. Do not attempt to implement all 19 domains simultaneously.

## Phase 0 — Bootstrap

Create:

- clean repository/project root
- Python environment and pinned dependencies
- package structure
- configuration system
- environment example
- logging
- test framework
- startup/shutdown lifecycle
- structured startup-stage events suitable for the native splash window
- basic health endpoint/command
- developer documentation

**Gate:** The application starts and stops cleanly with zero feature-specific hacks.

## Phase 1 — Core contracts, state, and security

Implement:

- shared schemas
- state engine
- state transitions
- permission levels
- confirmation model
- tool registry contracts
- standard action results
- audit/security logging
- dependency injection/provider registry

**Gate:** Unit tests prove valid/invalid state transitions, permission checks, tool registration, and action-result handling.

## Phase 2 — Intelligence core

Implement:

- conversation/session model
- structured intent/goal understanding
- direct-answer versus tool-use decision
- planning model
- tool selection
- structured tool arguments
- result interpretation
- verification loop
- bounded retry/repair behavior
- clear failure responses

**Gate:** Text-based tests can execute multi-turn contextual scenarios without voice.

## Phase 3 — Voice foundation

Implement and test the **locked Voice V2 stack** before moving on:

- one owned microphone capture pipeline
- rolling pre-roll buffer
- Silero VAD through sherpa-onnx
- Nemotron 3.5 ASR Streaming 0.6B INT8 through sherpa-onnx
- 160 ms streaming model/profile as the production default
- partial and final transcript events
- `auto` language mode with Hindi/English/Hinglish acceptance cases
- transcript normalization
- lazy faster-whisper multilingual small INT8 fallback
- always-listening controller with no wake-word or push-to-talk dependency
- continuous VAD readiness with bounded conversational-context timeout that never disables microphone capture
- ambient-speech/command-confidence gating without an activation phrase
- Supertonic 3 local ONNX TTS adapter
- spoken-text formatter
- streaming/chunked response-to-speech queue
- TTS playback completion events
- interruption/barge-in
- microphone/speaker no-self-trigger safeguards
- cancellation propagation
- voice latency metrics
- microphone, VAD, STT, TTS, playback, and interruption diagnostics

Do **not** add Edge TTS, Piper, Pocket-TTS, Windows SAPI, browser Web Speech STT, or a paid speech API as a hidden production fallback.

**Gate:** From a warmed local voice stack, STONIC accepts intentional English, Hindi, and Hinglish speech without a wake word or push-to-talk and produces real partial/final transcripts; the `MIC` UI action does not disable capture; STONIC does not trigger normal command recognition from its own TTS or low-confidence ambient speech; Supertonic speaks real responses; the user can interrupt speech; disabling the primary STT produces a controlled fallback/degraded state instead of crashing the assistant; disabling TTS leaves a usable text/UI response path.

## Phase 4 — Windows and computer-control tools

Implement reliable tools for:

- app resolution and launching
- closing/switching windows
- keyboard/mouse/hotkeys
- clipboard
- files
- window management
- browser control
- safe settings interaction

Each action must report structured success/failure and verification information.

**Gate:** Multi-step computer tasks run through the intelligence → permission → tool → verification pipeline.

## Phase 5 — Context and memory

Implement:

- active app/window context
- recent command/tool context
- structured context snapshots
- persistent memory schemas
- memory retrieval
- remember/forget/update/inspect controls
- task/environmental memory
- selective retention

**Gate:** Follow-up phrases such as “close this”, “continue”, and “open the third result” resolve from current context where enough information exists.

## Phase 6 — Vision

Implement:

- screenshot capture
- OCR/visible text extraction
- screen-understanding provider
- UI element/context recognition
- error/code/document/browser understanding paths
- permission-aware activation

**Gate:** Vision can inspect the current screen on demand and return structured observations usable by the intelligence core.

## Phase 7 — Web intelligence

Implement separate modes for:

- quick search
- research
- deep research

Include source extraction, comparison, conflict handling, structured model-output validation, retries, and citations where appropriate.

**Gate:** Time-sensitive requests cannot silently fall back to unsupported generic answers when web execution fails.

## Phase 8 — Autonomous tasks and productivity

Implement:

- task records
- plans and dependencies
- step execution
- progress
- cancellation
- retries
- completion reports
- reminders
- timers
- todos
- notes
- recurring tasks
- daily briefing state
- calendar integration boundary

**Gate:** A multi-step task survives normal subsystem errors and reports partial/complete status correctly.

## Phase 9 — Event engine and proactive behavior

Implement:

- event registration
- persistent schedules
- trigger evaluation
- restart recovery
- quiet hours
- throttling
- duplicate suppression
- permission/context checks
- notification routing

**Gate:** Proactive notifications occur only when permitted and relevant, and do not spam the user.

## Phase 10 — Plugin/skill architecture

Implement:

- skill manifest/metadata
- capability registration
- tool registration
- permission declaration
- schemas
- configuration
- lifecycle
- error isolation

Then implement built-in skills required by this specification, including the gaming and developer capabilities.

**Gate:** A new test skill can be added without modifying the intelligence core.

## Phase 11 — Personalization and learning

Implement the approved-preference layer separately from raw memory.

**Gate:** Corrections can influence later behavior, can be inspected or forgotten, and do not silently store sensitive traits.

## Phase 12 — Diagnostics and recovery

Implement subsystem health checks, health aggregation, bounded recovery, fallbacks, isolation, and structured diagnostic reporting.

**Gate:** Deliberately disabling a non-critical provider produces DEGRADED behavior rather than crashing the whole assistant.

## Phase 13 — Integration hardening

Run full-system scenarios covering voice, context, memory, vision, web, tools, tasks, events, permissions, interruption, and recovery.

Fix integration defects at their owning layer rather than adding cross-module hacks.

**Gate:** All acceptance scenarios and automated tests pass from a clean install.


## Phase 14 — Locked desktop UI implementation

Implement **Part II — Locked Desktop UI Specification** using its internal `UI-0` through `UI-9` sequence.

This is mandatory V2 work, not an optional skin and not a twentieth feature domain.

Rules:

- backend contracts remain the source of operational truth;
- the UI must not duplicate the intelligence core;
- no mock/fake backend state may remain in production;
- the central STONIC Core must bind to real state;
- every major implemented backend domain must have the required real UI integration;
- voice partial transcripts, TTS playback, tasks, tools, diagnostics, notifications, permissions, and failures must flow through real events/state;
- keep the Home composition minimal and preserve the locked purple/obsidian design.
- implement the compact real-progress `INITIALIZING STONIC` splash before the main window;
- implement the on-demand quick-access grid with `CONFIG`, the complete schema-backed Configuration panel, always-listening bottom capability actions, adaptive/DPI-safe sizing, and hover-reveal top-right window controls exactly as Part II requires.

**Gate:** All Part II UI acceptance criteria, UI tests, backend-integration tests, Windows/DPI tests, and visual QA checks pass with the real V2 backend.

## Phase 15 — Release integration and final hardening

From a clean Windows install/environment:

- run every backend acceptance scenario;
- run every UI end-to-end scenario;
- run voice latency/interrupt tests;
- verify model/runtime packaging and license notices;
- verify no runtime speech dependency silently requires the Internet;
- verify first-run setup and permissions;
- verify the splash-to-main startup handoff and honest degraded startup stages;
- verify continuous listening begins automatically and no Home control acts as a microphone toggle;
- verify Configuration changes persist, validate, apply/reset correctly, and never reveal secrets;
- verify all supported display sizes/DPI modes and hot-corner window controls;
- verify degraded startup with optional providers unavailable;
- verify graceful shutdown and restart recovery;
- verify logs contain no secrets/raw sensitive data by default;
- verify no placeholder/fake data remains;
- verify exact run/build/package instructions.

**Gate:** The complete desktop application installs, launches, operates, degrades safely, recovers where specified, and shuts down cleanly with all automated acceptance tests passing and all hardware-dependent limitations explicitly recorded.

---

# 27. TESTING STRATEGY

Testing is mandatory, not optional cleanup.

Provide:

- unit tests for pure logic
- contract tests for providers/tools
- integration tests across subsystem boundaries
- state-machine tests
- permission/security tests
- persistence/restart tests
- failure-injection tests
- always-listening lifecycle/state tests using mocks where hardware is unavailable
- end-to-end acceptance scenarios

For hardware/network/provider-dependent tests, use adapters and mocks so core correctness can still be tested deterministically.

Never mark a phase complete solely because the code imports successfully.

---

# 28. REQUIRED ACCEPTANCE SCENARIOS

At minimum, verify these scenarios before declaring V2 complete:

1. **Always-listening voice flow** — after startup, the user gives several natural commands without a wake word or push-to-talk; inactivity may clear conversation context but voice readiness remains active.
2. **No self-trigger or ambient action** — STONIC speaking cannot trigger command recognition, and low-confidence unrelated background speech cannot execute a consequential action.
3. **Interruption** — user can stop STONIC while it is speaking and immediately continue.
4. **Context follow-up** — references such as “this”, “continue”, or an ordinal result resolve from current context when unambiguous.
5. **Computer task** — a multi-step browser/Windows task is planned, executed, verified, and reported.
6. **Sensitive action** — deletion or another Level 2 action is blocked until confirmation.
7. **Memory lifecycle** — remember, retrieve, update, inspect, forget, and restart persistence work.
8. **Vision on demand** — visible screen content can inform an answer/action without continuous unnecessary capture.
9. **Current-information routing** — requests requiring fresh information use web intelligence.
10. **Autonomous task** — a multi-step task tracks dependencies, progress, retries, cancellation, and completion.
11. **Proactive event** — a permitted event produces one useful notification and respects quiet/throttle rules.
12. **Skill isolation** — a failing skill does not crash the core.
13. **Gaming context** — game detection/session state can drive safe gaming intelligence.
14. **Developer workflow** — STONIC can inspect an error, identify relevant files, propose/apply a permitted fix, test, verify, and report.
15. **Personalization correction** — an approved workflow preference changes future behavior and can later be removed.
16. **Recovery** — one provider/subsystem failure moves health to DEGRADED or RECOVERING while unrelated features remain available.
17. **Restart recovery** — persistent memory, productivity state, scheduled events, and incomplete task state recover correctly where applicable.
18. **Malformed model output** — structured-output repair/retry prevents invalid tool calls or silent route changes.
19. **Clean install** — the project can be installed and started from documented instructions without depending on the old STONIC repository.
20. **Startup splash** — a compact `INITIALIZING STONIC` window appears immediately, reflects real stages, and hands off cleanly to the ready or honestly degraded main window without white flashes or duplicate windows.
21. **Configuration lifecycle** — the `CONFIG` quick-grid entry opens the real Configuration panel; supported changes validate, persist, apply or request restart correctly, and reset safely.
22. **Adaptive desktop UI** — Home, Core, panels, bottom actions, and text remain fitted and readable across the required resolution/DPI/window-state matrix.
23. **Hover window controls** — the top-right hot zone reliably reveals minimize, maximize/restore, and close; native shortcuts and keyboard access still work while the controls are visually hidden.
24. **Bottom capability actions** — `MIC`, `SCREEN`, and `PC CONTROL` are buttons/actions rather than switches; `MIC` opens status/configuration and continuous capture remains active.

---

# 29. CODE-QUALITY RULES

- Prefer small modules with one clear responsibility.
- Avoid giant god classes.
- Avoid circular imports.
- Avoid duplicated state.
- Avoid hidden global mutable state.
- Avoid broad `except Exception: pass` behavior.
- Never swallow an error that affects correctness.
- Use bounded retries with backoff where appropriate.
- Validate model-generated structured output before execution.
- Validate external input at boundaries.
- Keep operating-system actions behind tools/adapters.
- Keep business logic testable without hardware where possible.
- Document non-obvious architectural decisions.
- Keep dependencies intentional; do not add libraries for trivial tasks.
- Do not commit secrets, generated caches, virtual environments, model downloads, or unnecessary binaries.
- Maintain a useful `.gitignore`.
- Keep the project runnable throughout development; do not accumulate weeks of unintegrated code.

---

# 30. DEFINITION OF DONE

STONIC V2 is complete only when:

- all 19 finalized feature domains are implemented
- no finalized domain is represented only by stubs or TODOs
- the clean architecture is documented
- the new backend does not depend on V1 backend internals
- installation/setup is documented
- configuration validation works
- secrets are externalized
- important state persists correctly
- tools return structured results
- consequential actions use the permission system
- state transitions are consistent
- the locked Voice V2 stack (Nemotron + Silero VAD + Supertonic) works end-to-end, including Hinglish, partial transcripts, interruption, and degraded behavior
- always-listening activation, ambient/self-trigger safeguards, and interruption work correctly without a wake word or push-to-talk
- failures are visible and recoverable where specified
- diagnostics accurately reflect subsystem health
- the locked Part II desktop UI is implemented and connected to real backend state
- the STONIC Core, floating panels, command palette, notifications, confirmations, diagnostics, and major domain panels pass their acceptance criteria
- the startup splash, `CONFIG` grid entry, Configuration panel, adaptive layout, hover-reveal window controls, and bottom capability actions pass their acceptance criteria
- automated backend and UI tests pass
- required acceptance scenarios pass
- the system starts cleanly on Windows
- the application can shut down cleanly
- logs are sufficient to diagnose failures without exposing secrets
- no critical execution path depends on fake success responses

A partially connected prototype, a backend-only build, or a visually complete UI backed by mocks is **not** V2 complete.

---

# 31. CLAUDE EXECUTION PROTOCOL

When using this specification to build STONIC:

1. Treat this document as the product and engineering source of truth.
2. Do not reopen feature planning unless the user explicitly changes the specification.
3. Begin by inspecting the available environment and repository only to understand constraints.
4. Establish the clean V2 root and architecture before implementing features.
5. Present a concise architecture/file-tree/build-order summary, then proceed with implementation instead of stopping at planning.
6. Build phase by phase in the order above unless a dependency requires a justified change.
7. After each phase, run its tests and acceptance gate.
8. When something fails, diagnose the root cause instead of applying random patches.
9. Do not replace a required capability with a mock in production code just to make tests pass.
10. Use mocks only at test boundaries or when hardware/services are intentionally unavailable.
11. Preserve working behavior while integrating the next phase.
12. Keep a short implementation status document showing completed, in-progress, blocked, and not-started items for the 19 finalized domains **plus the separate mandatory UI implementation track**.
13. Do not claim completion until the Definition of Done and Part II UI completion definition are satisfied.
14. If a choice is unspecified, choose the simplest robust design that fits this architecture and document the decision.
15. Ask the user only when a genuinely product-level choice is missing; do not ask for routine engineering decisions that can be safely made.

---

# 32. FINAL DIRECTIVE

Build **STONIC V2 from scratch** as one coherent personal AI system.

Do not rebuild it as a pile of command handlers. Do not merely repair V1. Do not sacrifice architecture for a quick demo. Do not silently remove difficult requirements. Do not label placeholders as complete.

The 19 feature domains are final, and the locked Part II desktop UI is mandatory. Your job is now **implementation**: create the clean foundation, integrate every finalized capability through explicit contracts, implement the locked UI over those real contracts, test each layer, verify real execution, and deliver a maintainable Windows assistant that remains useful even when individual subsystems fail.

---

# PART II — LOCKED STONIC V2 DESKTOP UI SPECIFICATION

> **Status:** FINAL / LOCKED  
> **Purpose:** Implement the complete production desktop interface over the real Part I backend as the mandatory final product layer.  
> **Core rule:** Do not redesign, simplify, reinterpret, or replace the visual/interaction concept below. Do not rebuild a correctly implemented Part I subsystem merely to make UI integration easier; adapt the UI to clean contracts and fix contract defects at their owning layer.
>
> **Implementation context:** Execute the UI phases after the corresponding backend contracts exist and are tested. The UI must remain a client/presentation layer: backend state is operational truth; frontend state is presentation state.

---

# 1. PRODUCT VISION

STONIC V2 is not a conventional chatbot.

The interface must feel like a premium, intelligent desktop operating layer that assembles itself around what the user is currently doing.

The visual philosophy is:

**Obsidian background + purple intelligence + white typography + one iconic STONIC Core + zero permanent clutter + glass floating panels + voice-first interaction + intelligent workspace composition.**

The Home screen is STONIC's identity.

Everything else should appear only when requested, required by the current task, or necessary for safety/status communication.

---

# 2. NON-NEGOTIABLE DESIGN RULES

These requirements are locked.

- The default Home screen must remain extremely clean.
- The central animated **STONIC Core/Ring** is the primary visual element.
- Center branding must read exactly: **S.T.O.N.I.C**
- Do not add a tagline beneath the name.
- Do not turn the application into a ChatGPT-style chat page.
- Do not use a permanent left navigation sidebar.
- Do not use a permanently visible dashboard grid.
- A compact **on-demand quick-access grid** is allowed and required; it must disappear when dismissed and must contain a `CONFIG` entry. It is navigation, not a dashboard of live cards.
- Do not fill the Home screen with cards.
- All substantial functionality must appear through **on-demand floating panels/workspaces**.
- Panels use premium dark glassmorphism.
- Primary accent family is **purple only**.
- Main surfaces use obsidian/near-black neutrals.
- White/off-white is used primarily for readable text.
- Avoid cyan/blue as the core identity.
- Avoid rainbow gradients.
- Avoid RGB/gaming aesthetics.
- Avoid excessive neon.
- Avoid excessive particle effects.
- Avoid unnecessary decorative widgets.
- Animations must communicate state or hierarchy rather than exist merely for spectacle.
- The UI must expose important autonomous actions and provide control over them.
- The UI must be usable with mouse, keyboard, and voice.
- A compact `INITIALIZING STONIC` splash must precede the main window on every normal launch.
- The whole composition must adapt to the actual display work area, aspect ratio, window size, and Windows DPI without clipping or becoming unreasonably small.
- The bottom-left `MIC`, `SCREEN`, and `PC CONTROL` controls are action/status buttons, not toggles; `MIC` never disables the always-listening pipeline.
- Minimize, maximize/restore, and close remain visually hidden at rest and reveal from the top-right hover/focus zone.

---

# 3. DESIGN TOKENS

Create centralized design tokens instead of scattering values throughout components.

Suggested starting values may be adjusted slightly for contrast/performance while preserving the visual direction.

## 3.1 Colors

```css
--bg-0: #050407;
--bg-1: #09070D;
--bg-2: #0D0913;

--surface-glass: rgba(18, 12, 26, 0.58);
--surface-glass-strong: rgba(20, 13, 30, 0.78);
--surface-hover: rgba(117, 61, 180, 0.10);

--purple-100: #E9DAFF;
--purple-200: #D5B6FF;
--purple-300: #BC8CFF;
--purple-400: #A261F2;
--purple-500: #873DDA;
--purple-600: #6826AF;
--purple-700: #481B79;

--text-primary: #F7F4FA;
--text-secondary: #BDB6C6;
--text-muted: #827B89;

--border-soft: rgba(188, 140, 255, 0.15);
--border-active: rgba(188, 140, 255, 0.42);

--success: #F7F4FA;
--warning: #D5B6FF;
--danger: #BC8CFF;
```

Semantic states may vary by shape/icon/text as well as color. Never rely on color alone.

## 3.2 Glass

Typical floating panel:

- translucent obsidian surface
- background blur
- subtle saturation
- thin purple-tinted border
- restrained outer shadow
- very subtle internal highlight
- no thick glowing outline

## 3.3 Radius

Use a consistent radius system, approximately:

- small controls: 8–10 px
- medium controls: 12–14 px
- cards: 16–18 px
- major floating panels: 20–24 px
- capsules: fully rounded where appropriate

## 3.4 Typography

Use two visual typography roles:

**Display:** futuristic but highly legible, reserved for S.T.O.N.I.C, major states, and selected headings.

**Interface:** modern clean sans-serif for body text, controls, tables, diagnostics, settings, transcripts, etc.

Do not sacrifice readability for sci-fi styling.

## 3.5 Spacing

Implement a consistent spacing scale. Do not place elements using arbitrary margins.

---

# 4. APPLICATION SHELL

Build a lightweight desktop shell containing:

1. compact native startup-splash window and handoff controller
2. background layer
3. custom title/drag region with top-right control reveal zone
4. STONIC Core layer
5. bottom capability-action layer
6. on-demand quick-access grid
7. panel/workspace manager
8. notification layer
9. transient conversation/status layer
10. modal/confirmation layer
11. command palette layer
12. optional developer/debug overlay

The shell must avoid unnecessary re-renders and must not allow expensive visual effects to degrade voice or AI processing.

---

# 5. DEFAULT HOME SCREEN

The default Home screen contains almost nothing.

Conceptual layout:

```text
┌──────────────────────────────────────────────────────────────┐
│ S.T.O.N.I.C                              [hover zone: ─ □ ×] │
│                                                              │
│                                                              │
│                                                              │
│                         STONIC CORE                          │
│                      animated circular                       │
│                         intelligence                         │
│                                                              │
│                        S.T.O.N.I.C                           │
│                                                              │
│                        ● LISTENING                           │
│                                                              │
│                                                              │
│ MIC   SCREEN   PC CONTROL                   GRID   ● READY    │
└──────────────────────────────────────────────────────────────┘
```

The exact visual result must be significantly more refined than this wireframe.

## 5.1 Idle reduction

After inactivity, secondary labels and controls should gently fade to lower prominence.

The visual endpoint should approach:

**Obsidian background + living STONIC Core.**

Moving the pointer, speaking, pressing a shortcut, or receiving an important event restores relevant controls.

## 5.2 Bottom capability actions

Anchor a restrained control group to the bottom-left safe area:

```text
[ ● MIC ]   [ SCREEN ]   [ PC CONTROL ]
```

These controls use normal button/action semantics, not switch/toggle semantics:

- **MIC** — displays the real microphone/voice-service state and opens the Voice section of the Configuration panel or its diagnostic detail. It must not expose an on/off switch, use `aria-pressed`, or stop/pause the always-listening capture service when clicked.
- **SCREEN** — performs the supported one-shot `Analyze Screen` action or opens/focuses the Vision panel for selection and analysis. It is not a permanent screen-sharing toggle.
- **PC CONTROL** — opens/focuses the computer-control activity/permission surface. It does not silently grant or revoke powerful permissions.

Each button may show a small semantic status dot/label such as `LISTENING`, `READY`, `ACTIVE`, `DEGRADED`, `DENIED`, or `UNAVAILABLE`, but status styling must not turn the button into a switch. Tooltip and accessible labels must describe both the current state and the click action.

The control group must:

- remain within work-area and safe-edge insets at every supported size/DPI;
- collapse to icon + accessible tooltip only when space is genuinely constrained;
- never overlap a floating panel, taskbar-safe inset, or the Core;
- fade to lower prominence after inactivity without becoming undiscoverable.

---

# 6. STONIC CORE / CENTRAL RING

This is the visual signature of STONIC V2.

It must not look like a generic loading spinner.

Construct it using multiple coordinated layers, such as:

- faint outer aura
- one or more precision orbital rings
- segmented arcs
- inner energy ring
- subtle central depth
- restrained radial glow
- optional fine technical markings
- central S.T.O.N.I.C text

Keep it sophisticated and minimal.

## 6.1 Core states

The Core must react to actual application state.

### Ready / passive listening
- slow breathing
- minimal movement
- very subtle purple luminance
- microphone/VAD remains active in the backend
- compact status reads `LISTENING` or `READY · LISTENING` without demanding attention
- this calm visual state must never imply that STONIC has stopped listening

### Active utterance
- responsive amplitude movement
- ring reacts to real microphone activity when available
- `LISTENING` state appears
- optional compact live transcript beneath

### Understanding
- controlled inner rotation
- subtle tightening/compression

### Thinking
- multiple coordinated orbital movements
- slightly increased luminance
- never resemble an indefinite loading failure

### Speaking
- waveform-like expansion based on playback amplitude when practical
- smooth outward pulses

### Executing
- deliberate faster rotation or segmented progress movement
- accompanying activity capsule when external actions are occurring

### Success
- one restrained outward confirmation pulse
- return smoothly to idle

### Error
- brief distortion/interruption
- show understandable error state
- do not continuously flash

## 6.2 Motion performance

Prefer GPU-friendly transforms and opacity.

Avoid huge blurred layers being continuously repainted.

Support reduced-motion settings.

Pause or reduce animation when:
- app is hidden/minimized
- battery/resource constraints warrant it
- reduced motion is enabled

---

# 7. FLOATING PANEL SYSTEM

This is the central interaction architecture.

Substantial functionality opens in floating panels rather than replacing the Home screen.

Each appropriate panel should support:

- open
- close
- focus
- drag
- intelligent placement
- optional resize
- minimize/collapse
- stacking/z-order
- keyboard focus
- restoration of relevant state
- optional pinning when useful

Panels must remain inside usable screen bounds.

## 7.1 Panel behavior

When one panel opens, position it so the STONIC Core remains visible where practical.

When several panels open, intelligently compose a workspace rather than randomly overlapping everything.

The panel manager should understand:
- preferred panel size
- minimum size
- current viewport
- other open panels
- task context
- user placement overrides

Manual user positioning should not be constantly overwritten.

## 7.2 Workspace examples

**Compare two files**
- file A panel
- file B panel
- comparison/analysis panel

**Research request**
- Core shifts slightly
- large Research panel opens
- sources/details may appear in secondary panes

**System troubleshooting**
- Diagnostics panel
- System Monitor panel
- optional log/detail panel

Temporary panels may collapse or close after task completion only when doing so will not destroy important user context.

---

# 8. UNIVERSAL COMMAND PALETTE

Recommended shortcut:

**Ctrl + Space**

The palette should open immediately and focus its input.

Concept:

```text
┌──────────────────────────────────────────────┐
│ ✦ Ask STONIC or run a command...            │
├──────────────────────────────────────────────┤
│ Open Memory                                  │
│ Search Web                                   │
│ Analyze Screen                               │
│ Create Task                                  │
│ Open System Monitor                          │
│ CONFIG                                       │
└──────────────────────────────────────────────┘
```

Capabilities:

- natural-language requests
- command search
- fuzzy matching
- recent commands
- keyboard navigation
- enter to execute
- escape to close
- contextual actions
- open panel commands
- backend tool invocation through approved STONIC interfaces

It must not maintain a separate fake command system disconnected from STONIC's real capabilities.

## 8.1 On-demand quick-access grid

Provide a small `GRID` launcher control in the lower-right safe area and a matching command/keyboard route. Activating it opens a compact glass quick-access grid; the grid is never permanently visible on Home and is not a telemetry dashboard.

Required entries:

- **CONFIG** — opens/focuses the schema-backed Configuration panel;
- Conversation;
- Research;
- Vision / Analyze Screen;
- Memory;
- Tasks;
- System Monitor;
- Diagnostics;
- Plugins/Skills where implemented.

The first release may arrange only the entries that connect to real backend capabilities, but `CONFIG` is mandatory. The grid must support keyboard navigation, semantic labels, escape/click-outside dismissal, responsive column count, and bounds-safe placement. At narrow widths it becomes a one- or two-column sheet/popover rather than shrinking tiles and text to illegibility.

The grid opens panels through the centralized panel registry. It must not duplicate configuration logic, tool invocation, permissions, or state.

---

# 9. VOICE EXPERIENCE

Voice interaction is part of the Core.

Do not require the user to enter a separate voice page.

After initialization, the owned voice service remains ready continuously. The UI must not present a wake-word prompt, push-to-talk requirement, or microphone on/off toggle. A quiet ready state and an active-utterance state may look different, but both belong to the always-listening lifecycle.

When listening:
- Core changes state
- live amplitude appears
- Nemotron partial transcripts may appear compactly below the Core
- final transcript replaces transient fragments cleanly
- mic state is obvious
- partial/final transcript updates from the real STT pipeline must be throttled so they do not create render pressure

When STONIC answers briefly:
- show a transient response near the Core
- speak through the locked **Supertonic 3 local TTS** system
- bind Speaking animation to real playback state/amplitude where practical
- dismiss/fade text after an appropriate period

For long-form answers:
- open a Conversation/Response panel when needed
- preserve readable content
- allow copying
- allow related actions

The `MIC` status/action control must clearly expose:
- listening/ready
- active utterance detected
- processing/recovering
- externally muted by the OS/device where detectable
- unavailable/error
- permission denied

Clicking `MIC` opens the Voice configuration/diagnostic surface and must leave capture active. If Windows or the physical device has muted/denied the microphone, the UI may guide the user to resolve that external state; it still must not pretend the Home control is a toggle.

---

# 10. CONVERSATION PANEL

This panel exists for interactions that genuinely benefit from persistent history.

It must not become the application's permanent Home screen.

Include as appropriate:
- message/history timeline
- attachments
- tool/action activity
- copy
- retry/regenerate where supported
- stop generation
- scroll-to-latest
- timestamps where useful
- source references where relevant

Visually keep it consistent with the floating glass workspace system.

---

# 11. WEB INTELLIGENCE / RESEARCH

Create a dedicated floating research experience.

Possible information hierarchy:

- query
- concise synthesized answer
- important findings
- sources
- source cards/list
- relevant images where the backend supports them
- follow-up actions

Useful actions:

- Open Source
- Summarize
- Compare
- Ask STONIC
- Save useful information where supported

Do not imitate a full browser unless the existing system genuinely requires one.

For multi-source research, allow the Research panel to expand into a larger workspace.

---

# 12. VISION UI

The Vision interface must clearly communicate what STONIC is analyzing.

Support backend capabilities such as:
- screen analysis
- camera analysis where implemented
- screenshots
- region selection
- OCR/visual understanding
- detected elements
- action targets

Panel information can include:

- source
- current status
- latest analysis
- recognized regions/objects
- privacy state
- stop button

For screen control, temporary purple overlays/bounding indicators may highlight relevant UI targets.

They must be:
- short-lived
- non-blocking
- visually restrained
- aligned to real detections/actions

Never fake detections.

---

# 13. MEMORY PANEL

Memory must feel like an inspectable intelligence system rather than an opaque database.

Concept:

```text
┌──────────────────────────────────────────┐
│ MEMORY                              ×    │
│ Search memories...                       │
│                                          │
│ TODAY                                    │
│ ○ Current context                        │
│ ○ Recent interactions                    │
│                                          │
│ KNOWLEDGE                                │
│ ○ Projects                               │
│ ○ Preferences                            │
│ ○ People                                 │
│ ○ Places                                 │
│                                          │
│                              Manage →    │
└──────────────────────────────────────────┘
```

Actual categories must follow the real memory architecture rather than inventing unsupported backend types.

Capabilities where supported:

- search
- inspect
- view source/context
- edit/correct
- delete
- clear selected memories
- memory health/status
- privacy explanation

Destructive actions require appropriate confirmation.

---

# 14. TASKS & AUTONOMY

Autonomous tasks require transparency.

Each running task should expose:

1. Objective
2. Plan
3. Current action
4. Progress/state
5. Tools used
6. Important outputs
7. Result
8. Errors/retries when applicable

Controls:

- Pause
- Resume
- Cancel
- Inspect

Do not present fabricated step-by-step reasoning. Display operational task state, actions, tool activity, and user-relevant progress only.

For background tasks, show a compact status indicator rather than forcing the entire panel open.

---

# 15. COMPUTER CONTROL UI

Whenever STONIC performs visible computer actions, provide a compact activity capsule.

Example:

```text
┌──────────────────────────────────────┐
│ ✦ STONIC                            │
│ Opening Visual Studio Code...       │
│                              CANCEL │
└──────────────────────────────────────┘
```

For actions requiring user approval, expand into a confirmation surface that explains:

- what STONIC intends to do
- target
- consequence where relevant
- confirm
- cancel

Never obscure important confirmation information.

Actions should be cancellable where the underlying operation supports cancellation.

---

# 16. NOTIFICATIONS

Build a STONIC-native notification stack.

Preferred position: upper-right, adjusted for open panels.

Notifications should have:
- icon/state
- concise title
- optional detail
- optional action
- auto-dismiss for low priority
- persistence for important/error events

Avoid notification spam.

Group repetitive events where practical.

Notifications should use the purple/obsidian visual system rather than OS-like white cards.

---

# 17. SYSTEM MONITOR PANEL

Expose real telemetry available from STONIC.

Potential metrics:

- CPU
- GPU where supported
- RAM
- disk
- network
- battery
- temperature where reliable
- STONIC process usage
- AI/provider status
- active background services

Use compact live indicators first.

Only render detailed historical charts when requested.

Do not continuously render expensive charts while the panel is hidden.

---

# 18. DIAGNOSTICS PANEL

Create a developer-friendly diagnostics panel.

Concept:

```text
STONIC DIAGNOSTICS

Core                 ● ONLINE
LLM                  ● CONNECTED
Voice Input          ● READY
TTS                  ● READY
Memory               ● HEALTHY
Vision               ● READY
Web                  ● READY
Tools                 ● READY
Event Engine          ● RUNNING
Plugins               ● READY

Errors                         0
Warnings                       0

[ Run Full Diagnostic ]
```

The actual service list and states must come from the existing STONIC implementation.

Capabilities:
- run diagnostics
- refresh
- inspect failure
- view concise error detail
- copy useful diagnostic report
- open the relevant Configuration/log surface
- distinguish warning/degraded/error

Do not mark a service healthy merely because the UI loaded.

---

# 19. CONFIGURATION PANEL (`CONFIG`)

Provide one authoritative, larger floating **Configuration panel**. It is opened by the mandatory `CONFIG` entry in the on-demand quick-access grid, by the command palette, by voice, and by context links such as the bottom-left `MIC` action.

This is the customization center for STONIC. Every real, safe, user-facing option supported by the current build must be discoverable here. “Everything is customizable” means every intentionally supported product behavior and visual preference—not security invariants, fake controls, arbitrary internal constants, or unsupported engine choices.

## 19.1 Layout and interaction

Use a responsive category grid/index inside the panel, followed by the selected category's controls. This is an on-demand panel and therefore does not violate the no-dashboard-grid Home rule.

Required capabilities:

- search settings by name, description, or category;
- category grid/list that adapts from multiple columns to a single column without tiny cards;
- schema-driven controls with correct types, choices, ranges, defaults, validation, and help text;
- live preview for safe appearance/motion changes;
- explicit Apply/Save where batching is needed and immediate apply where safe;
- clear `Restart required` labels for non-live changes;
- per-setting reset, category reset, and full reset with confirmation;
- unsaved-change protection when the panel closes;
- persistence across restart using atomic backend writes;
- import/export of non-secret preferences where supported;
- a concise change result showing applied, pending restart, rejected, or recovered-to-last-valid;
- deep links so `MIC`, `SCREEN`, `PC CONTROL`, diagnostics, and error surfaces can open the relevant subsection directly.

The panel must remain usable at all supported display sizes: internal regions scroll independently where necessary, action buttons remain reachable, labels do not truncate essential meaning, and no setting becomes unusably small.

## 19.2 Required categories

Expose these categories when backed by real implementation:

- **General & Startup** — launch behavior, startup splash detail level, restore valid window/panel state, language/locale, update channel where implemented;
- **Appearance & Core** — theme-preserving purple intensity, glass opacity, Core size within safe limits, animation intensity, typography scale, panel density, UI sounds, reduced motion;
- **Layout & Windows** — default panel sizing/placement, remember panel positions, first-launch window size, hot-corner reveal timing within safe bounds, always-on-top only where supported;
- **AI & Providers** — provider, supported model, generation behavior, endpoint/base URL where applicable, masked credentials, connection test;
- **Voice** — microphone device, VAD sensitivity within validated bounds, endpointing, STT language mode (`auto`, English, Hindi where supported), live transcript visibility, ambient-speech confidence behavior, Supertonic packaged voice/style, speech speed, interruption/barge-in, echo/no-self-trigger diagnostics;
- **Memory** — supported retention, inspectability, auto-save rules, cleanup, and privacy controls;
- **Vision & Screen** — one-shot screen-analysis defaults, region behavior, OCR/vision provider, privacy/permission state;
- **PC Control & Permissions** — action approval policies within the locked security model, per-capability permissions, confirmations, audit visibility;
- **Web & Research** — supported search/research provider settings and source-display behavior;
- **Tasks, Automation & Proactive Behavior** — quiet hours, confirmation thresholds, schedules, notification routing, throttling, and autonomy limits;
- **Notifications & Sound** — visual priority, duration, grouping, UI-sound enable/volume without affecting TTS priority;
- **Privacy & Security** — transcript/log retention, sensor visibility, data handling, credential state, permission review;
- **Plugins & Skills** — installed plugin configuration and declared permissions where supported;
- **Accessibility** — interface scale, text scale, contrast assistance, keyboard behavior, reduced motion, screen-reader labels;
- **Performance** — safe animation/telemetry rates and resource profiles without reducing voice priority;
- **Advanced & Developer** — diagnostics, logs, feature flags intended for users/developers, schema/version information, and recovery actions.

## 19.3 Locked always-listening rules inside Configuration

Voice configuration must not reintroduce a wake-word engine, push-to-talk mode, or Home microphone toggle. The Configuration panel may change microphone device, language, VAD/endpointing, sensitivity/confidence, transcript display, echo handling, voice style, speech speed, and barge-in when those controls are real.

It must show the always-listening lifecycle honestly:

- `LISTENING` when ready;
- `ACTIVE UTTERANCE` while speech is detected;
- `RECOVERING` during a bounded voice-service restart;
- `PERMISSION DENIED`, `DEVICE UNAVAILABLE`, or `DEGRADED` when applicable.

A deliberate microphone-device change may briefly restart the owned audio service and must show that transition; it is configuration, not a persistent listen toggle.

Do not expose Edge TTS, Piper, Pocket-TTS, SAPI, browser Web Speech, or fake provider choices.

## 19.4 Backend ownership and secrets

The backend typed configuration schema is the source of truth. The panel must not directly rewrite `.env`, JSON, YAML, registry, or source files. It calls validated configuration APIs/contracts, receives field-level errors, and refreshes from committed state.

Secrets must:

- never be rendered openly by default;
- never be logged accidentally;
- use secure backend handling;
- be masked in the UI;
- never appear in exported preferences;
- provide explicit replace/remove/test actions without exposing the stored value.

Do not expose settings that do nothing. If a backend option is unavailable, omit it or show an honest disabled explanation rather than a decorative control.

---

# 20. PLUGINS / SKILLS

If STONIC V2 has a plugin/skill architecture, provide a management panel connected to it.

Show:
- installed plugins
- enabled state
- permissions/capabilities
- health/status
- configuration where supported

Do not allow the UI to silently grant new powerful permissions.

---

# 21. EVENT ENGINE / PROACTIVE BEHAVIOR

Proactive STONIC events should appear contextually.

Examples:
- notification
- activity capsule
- temporary Core state
- task panel
- confirmation panel

Do not force every proactive event into a chat message.

Provide a way to inspect why an event occurred when the backend has such metadata.

---

# 22. PANEL-SPECIFIC EMPTY, LOADING, ERROR STATES

Every significant panel needs explicit states.

## Loading
Use skeletons/subtle progress or Core-linked status.

## Empty
Explain what the panel is for and give one useful next action.

## Error
Show:
- concise failure
- retry when applicable
- detail expansion
- relevant Configuration/diagnostic action

Never leave a blank glass rectangle.

---

# 23. MICRO-INTERACTIONS

Target a premium, restrained feel.

Suggested timings:

- hover: ~100–160 ms
- control transition: ~140–200 ms
- panel open: ~250–350 ms
- panel close: ~180–280 ms
- notification entrance: ~200–300 ms

Panel opening may combine:
- slight scale
- fade
- small translation
- blur transition

Do not use springy cartoon motion.

---

# 24. ACCESSIBILITY

The futuristic design must remain usable.

Implement:

- keyboard navigation
- visible keyboard focus
- semantic labels
- adequate text contrast
- scalable typography
- reduced-motion support
- screen-reader-friendly names where applicable
- controls that do not depend solely on icons
- state communication not dependent solely on purple shades

Focus trapping must work correctly for modal confirmations.

Escape should dismiss appropriate temporary layers without accidentally cancelling critical tasks.

---

# 25. RESPONSIVENESS

STONIC V2 is a desktop application, but the complete composition must be **display-adaptive**, not designed for one screenshot size.

## 25.1 Sizing contract

- Enable per-monitor DPI awareness appropriate to the chosen desktop runtime and use device-independent/CSS pixels correctly.
- Calculate the initial/remembered main-window bounds against the current monitor's **work area**, not raw screen size, so the taskbar and reserved edges are respected.
- On first launch, open centered at a generous percentage of the available work area; if the effective work area is too constrained for the normal layout, open maximized and use compact breakpoints.
- Validate saved bounds before restoring them. If a monitor was removed, scaling changed, or bounds are off-screen, clamp/recenter the window automatically.
- Never use one global transform/zoom to shrink the whole application into place.
- Use fluid layout primitives, container/window breakpoints, `min`/`max`/`clamp` sizing, scrollable panel interiors, and sensible minimum interactive target sizes.
- Core size must respond to both width and height so it never collides with bottom controls or becomes a tiny dot on a large/ultrawide display.
- Text may scale within defined limits, but body text and controls must not fall below the accessible minimum chosen by the design system.
- Floating panels must use viewport-relative maximum width/height, remain draggable/resizable within usable bounds, and convert to stacked/docked/sheet layouts before content is clipped.
- Safe-edge insets must reserve space for the bottom capability group, quick-grid launcher, top-right reveal zone, notifications, and the Windows work area.

## 25.2 Required adaptive behavior

At reduced width or effective DPI space:

- panel grids reduce columns and then become a single readable column;
- panels dock/stack or become near-full-work-area sheets;
- secondary labels may collapse to accessible icons/tooltips;
- the Core reduces within its safe clamp but remains the focal point;
- the bottom capability actions wrap/collapse without overlapping the Core;
- window-control targets keep reliable hit areas;
- essential actions remain reachable without horizontal page scrolling.

At large or ultrawide sizes:

- do not stretch text lines and glass panels across the full display;
- use maximum content widths and intentional workspace composition;
- allow more simultaneous panels while preserving the Core and readable scale;
- do not leave the entire functional UI clustered as a tiny island.

## 25.3 Required display/DPI matrix

At minimum, manually and automatically validate representative effective layouts for:

- 1280×720 at 100%;
- 1366×768 at 100% and 125%;
- 1920×1080 at 100%, 125%, 150%, and 200%;
- 2560×1440 at 100%, 125%, and 150%;
- 3840×2160 at 150% and 200%;
- an ultrawide work area;
- a constrained resized window;
- maximize/restore and movement between monitors with different DPI.

For every case verify: no clipping, no off-screen controls, no unreadably small UI, no giant uncontrolled typography, no panel trapped outside bounds, and no overlap between the Core, bottom actions, quick grid, notifications, or title-control hot zone.

---

# 26. WINDOW CHROME

The main window uses reliable custom/frameless chrome with a **top-right hover/focus reveal** interaction.

## 26.1 Reveal behavior

- Reserve a permanent non-content hot zone in the top-right corner, large enough to discover the controls without pixel-perfect aiming.
- At rest, minimize/maximize/restore/close are visually hidden or reduced to near-zero prominence; they must not leave ghost borders or labels.
- When the pointer enters the top-right hot zone, reveal all three controls within approximately 100–160 ms.
- Keep them visible while the pointer is over the controls, while any control has keyboard focus, or while the window-control region is being used.
- After the pointer leaves and focus is elsewhere, fade them out after a short forgiving delay rather than disappearing beneath the cursor.
- Order controls in Windows convention: minimize, maximize/restore, close.
- Show the correct maximize or restore icon from the real native window state.
- The close affordance may gain a restrained danger state on direct hover; the default visual system remains purple/obsidian.

## 26.2 Reliability and accessibility

- Preserve a clear draggable title region that excludes interactive controls and panel content.
- Double-clicking the valid title drag region toggles maximize/restore where supported.
- Keep native resizing, edge/corner hit testing, snap layouts/Windows behavior where the chosen runtime supports them, and minimize/restore reliability.
- `Alt+F4`, `Alt+Space`, Windows taskbar controls, and keyboard focus routes must work even when the buttons are visually hidden; hover must not be the only way to close or manage the window.
- Give each revealed control an accessible name and reliable hit target.
- Handle normal, maximized, restored, and multi-monitor DPI states without a one-pixel dead strip or clipped buttons.
- Do not allow notifications, panels, or Home content to occupy the reveal zone.
- Closing must still invoke the graceful-shutdown/active-task confirmation rules.

Avoid flashy custom chrome that reduces reliability. The reveal interaction is aesthetic hierarchy, not permission to break native window behavior.

---

# 27. ICONOGRAPHY

Use a single consistent icon family.

Icons should be:
- simple
- thin/medium weight
- geometric
- readable at small sizes

Do not mix emoji, filled cartoon icons, and technical line icons.

---

# 28. SOUND DESIGN

UI sounds are optional and must be restrained.

Possible subtle sounds:
- activation
- confirmation
- important alert

Do not play sounds for every hover/click.

Provide a setting to disable UI sounds.

Voice/TTS always has priority over decorative audio.

---

# 29. DATA AND STATE ARCHITECTURE

Do not tightly couple visual components directly to raw backend transport.

Use a clear UI service/state layer.

Recommended conceptual state domains:

- startup
- app
- window/display
- core
- voice
- conversation
- panels
- notifications
- tasks
- memory
- vision
- web/research
- system
- diagnostics
- configuration
- plugins

Normalize event handling.

Avoid duplicate websocket/event subscriptions created by component remounts.

Clean up listeners and timers.

---

# 30. REAL-TIME EVENTS

The UI should respond to backend events for:

- startup stage/readiness
- listening state
- partial/final transcript updates from the real STT pipeline
- LLM generation
- TTS playback
- task progress
- tool execution
- notifications
- diagnostics
- system metrics
- vision state
- memory changes
- errors
- configuration committed/rejected/restart-required
- display/DPI/window-state changes

Implement reconnect behavior where relevant.

The UI must clearly distinguish:
- disconnected
- reconnecting
- connected
- degraded

Do not silently pretend connectivity exists.

---

# 31. SECURITY & PRIVACY UX

STONIC may interact with microphones, cameras, screen contents, files, web services, and PC controls.

The UI must make these states understandable.

Provide visible status for sensitive sensors/capabilities when active.

Important permissions should be manageable.

For consequential actions, use appropriate confirmation.

Do not expose:
- raw secrets
- API keys
- sensitive tokens
- hidden credentials

Do not store secrets in front-end source code.

---

# 32. PERFORMANCE BUDGET

Visual polish must not damage assistant performance.

Priorities:

1. voice responsiveness (microphone/VAD/STT/TTS/interruption)
2. input responsiveness
3. backend event processing
4. panel responsiveness
5. Core animation
6. decorative effects

Optimize:

- animation layers
- event subscription frequency
- system metric polling
- chart updates
- large histories
- source lists
- logs
- memory lists

Use virtualization/pagination where datasets can become large.

Throttle high-frequency visual updates.

---

# 33. CORE UI COMPONENTS

Create reusable components rather than bespoke markup everywhere.

Examples:

- `StartupSplash`
- `StartupProgress`
- `AppShell`
- `WindowChrome`
- `WindowControlRevealZone`
- `StonicCore`
- `CoreStatus`
- `VoiceTranscript`
- `BottomCapabilityActions`
- `QuickAccessGrid`
- `CommandPalette`
- `PanelManager`
- `FloatingPanel`
- `PanelHeader`
- `ActivityCapsule`
- `NotificationStack`
- `ConfirmationDialog`
- `ConversationPanel`
- `ResearchPanel`
- `VisionPanel`
- `MemoryPanel`
- `TasksPanel`
- `SystemPanel`
- `DiagnosticsPanel`
- `ConfigurationPanel`
- `ConfigurationCategoryGrid`
- `ConfigurationField`
- `PluginsPanel`
- `StatusBadge`
- `Metric`
- `EmptyState`
- `ErrorState`
- `LoadingState`

Names may adapt to the existing codebase conventions.

---

# 34. PANEL REGISTRY

Use a centralized panel registry/configuration instead of hard-coding panel logic throughout the app.

A panel definition can conceptually contain:

- unique ID/type
- title
- icon
- component
- preferred size
- minimum size
- resizable
- singleton/multi-instance
- persistence behavior
- keyboard shortcut
- placement preference

This makes future STONIC capabilities easier to add.

Register the Configuration panel with a stable `config`/`configuration` ID and expose it to the quick-access grid, command palette, voice UI intents, and deep links. All routes must focus the same singleton panel instance rather than opening duplicate Configuration panels.

---

# 35. INTELLIGENT PANEL ORCHESTRATION

Create an orchestration layer that can translate STONIC UI intents/events into panel actions.

Examples:

```text
OPEN_PANEL(memory)
OPEN_PANEL(system)
OPEN_RESEARCH(query)
SHOW_CONFIRMATION(action)
SHOW_NOTIFICATION(event)
SHOW_TASK(taskId)
FOCUS_PANEL(panelId)
CLOSE_PANEL(panelId)
```

The backend should not need to know pixel positions.

The UI decides presentation/layout.

---

# 36. KEYBOARD INTERACTION

At minimum support:

- `Ctrl + Space` → command palette
- `Ctrl + ,` → open/focus `CONFIG`
- `Ctrl + Shift + Space` → open/dismiss the quick-access grid
- `Esc` → close current temporary layer where safe
- `Tab` / `Shift + Tab` → accessible focus movement
- `Enter` → activate selected command/action
- standard copy/select behavior

Additional shortcuts can be added only if useful and documented.

---

# 37. STARTUP EXPERIENCE

Every normal desktop launch must use a **small dedicated startup splash window** before the main STONIC window. It is a functional initialization surface, not a long cinematic intro.

## 37.1 Splash appearance

- Primary copy must read exactly: **`INITIALIZING STONIC`**.
- Use a compact frameless purple/obsidian window centered in the current monitor work area.
- Suggested visual structure: small STONIC mark/Core fragment, primary label, one real current-stage label, and restrained determinate or stage progress.
- Use display/DPI-aware sizing with sensible clamps; it must not be microscopic on 4K or too large on a small laptop.
- Keep the splash above STONIC's hidden main window during initialization without permanently forcing it above unrelated applications.
- Do not show a taskbar entry for both splash and main as if two applications launched.
- Do not display a full dashboard, settings, fake terminal output, advertisements, tips carousel, or a skip button.
- Do not allow a white/transparent flash, unstyled frame, or partially rendered main window to appear behind it.

## 37.2 Real startup stages

Drive the stage label and progress from the actual startup coordinator. Recommended user-facing stages are:

1. `STARTING CORE`
2. `LOADING CONFIGURATION`
3. `INITIALIZING VOICE`
4. `CONNECTING SERVICES`
5. `PREPARING INTERFACE`
6. `READY`

Internal services may initialize in parallel. Map them to stable user-facing stages instead of rapidly flashing every module name. Never advance progress on a timer alone and never claim `READY` before the readiness contract is satisfied.

The critical readiness contract includes:

- validated configuration or a recoverable configuration error state;
- backend lifecycle/state service running;
- UI assets/shell ready to paint without a loading flash;
- continuous microphone/VAD controller either `LISTENING` or honestly `DEGRADED`/`PERMISSION DENIED`/`DEVICE UNAVAILABLE`;
- enough diagnostics/event transport to explain any degraded service.

Optional providers and expensive non-critical warmups must not trap the user on the splash indefinitely. After the bounded startup policy classifies them as degraded/continuing, complete the splash and let their honest status continue in the main UI.

## 37.3 Handoff to the main window

Preferred flow:

1. create/show compact splash;
2. initialize backend and continuous voice lifecycle while the main window remains hidden;
3. create and fully style the main window off-screen/hidden;
4. reach `READY` or bounded honest `DEGRADED` startup result;
5. show `READY` briefly enough to register without adding delay;
6. reveal/fade in the main window and Core;
7. close/destroy the splash;
8. focus the main window without a duplicate taskbar/focus flash;
9. Home settles into ready/passive-listening presentation.

If startup cannot produce even a recoverable main shell, the splash must change to a concise error state with `Retry`, `Open Diagnostics/Logs` where possible, and `Exit`; it must not spin forever.

Startup duration, stage failures, and splash-to-main handoff must be logged without secrets and exposed to diagnostics.

---

# 38. FIRST-RUN EXPERIENCE

If setup is required, use a focused onboarding flow only on first run.

Possible setup:
- microphone permission
- optional camera/screen permission
- voice configuration for microphone, Nemotron STT, and Supertonic TTS
- clear explanation that STONIC remains locally ready/listening while the app runs, does not require a wake word, and does not store raw audio by default
- AI/provider configuration
- privacy explanation

After setup, do not repeatedly show onboarding.

On first launch, the normal startup splash still appears first; it hands off to onboarding instead of Home until setup is complete. Later launches hand off directly to Home.

---

# 39. SHUTDOWN EXPERIENCE

When closing STONIC:

- stop listeners safely
- clean up subscriptions
- stop/handle running tasks according to backend rules
- persist allowed UI state
- close gracefully

If critical autonomous work is active, warn before termination where appropriate.

---

# 40. LOGGING

UI logging must be useful but not noisy.

Log:
- significant state transitions
- backend connection failures
- panel orchestration failures
- uncaught UI errors
- critical integration failures

Do not log:
- secrets
- complete sensitive transcripts unnecessarily
- API keys/tokens
- private file contents by default

---

# 41. ERROR BOUNDARIES

A single broken panel must not crash the entire STONIC UI.

Implement appropriate error boundaries/fallbacks.

If a panel fails:
- isolate failure
- show a recoverable error surface
- provide retry/reload where possible
- record diagnostic information

---

# 42. DEVELOPMENT / DEBUG MODE

Provide development-only tooling when useful.

Possible capabilities:

- simulate Core state
- open any panel
- inspect UI events
- inspect connection state
- test notifications
- test panel layout
- test reduced motion
- inspect performance

These controls must not clutter production UI.

---

# 43. TESTING REQUIREMENTS

Do not declare the UI complete after it merely renders.

## 43.1 Component tests

Test important reusable components and state transitions.

## 43.2 Panel manager

Test:
- open
- close
- focus
- drag
- resize
- bounds
- multiple panels
- restoration

## 43.3 Command palette

Test:
- open shortcut
- filtering
- keyboard selection
- command execution
- dismissal
- quick-access grid open/dismiss, responsive column count, keyboard navigation, and mandatory `CONFIG` routing

## 43.4 Core states

Verify all actual states:
- ready/passive listening
- active utterance
- understanding
- thinking
- speaking
- executing
- success
- error

## 43.5 Backend integration

Verify:
- real service state
- real transcripts
- real responses
- real tool activity
- real diagnostics
- real system metrics
- real task events
- real memory data
- real vision status
- real research data
- real configuration schema, values, validation results, commit/reset events, and restart-required state
- real startup-stage and readiness events

## 43.6 Failure testing

Test:
- backend unavailable
- connection loss
- reconnect
- TTS unavailable
- microphone unavailable
- continuous-listening service recovery
- provider failure
- diagnostics warning
- tool failure
- cancelled task
- malformed event
- invalid configuration value and atomic-write recovery
- startup service stall/failure and bounded degraded handoff

## 43.7 Windows testing

Verify:
- normal window
- maximized
- minimize/restore
- top-right hover/focus reveal for minimize/maximize/restore/close
- native shortcuts while controls are hidden
- DPI scaling at every matrix point in Section 25.3
- resizing
- common laptop resolution
- ultrawide/4K layouts
- cross-monitor movement with different DPI
- taskbar/work-area insets
- keyboard shortcuts
- custom chrome if used

## 43.8 Startup splash and handoff

Test:

- splash appears before the main window on normal launch;
- primary copy is exactly `INITIALIZING STONIC`;
- stage/progress is driven by real startup events rather than a timer;
- main remains hidden until fully styled and startup reaches ready or honest degraded status;
- no white flash, duplicate taskbar window, focus bounce, or splash left behind;
- unrecoverable startup exposes retry/diagnostic/exit instead of endless animation;
- first run hands off to onboarding and later runs hand off to Home.

## 43.9 Configuration panel

Test:

- `CONFIG` opens the singleton panel from grid, command palette, keyboard, voice, and deep links;
- search and responsive category grid/list;
- each rendered control matches the typed backend schema;
- validation and field-level error display;
- live apply versus restart-required behavior;
- persistence after restart;
- per-setting/category/full reset;
- unsaved-change protection;
- import/export excludes secrets;
- backend rejection preserves the last known-valid configuration;
- no unsupported or no-op controls appear.

## 43.10 Bottom capability actions and always listening

Test:

- `MIC`, `SCREEN`, and `PC CONTROL` render as buttons/actions, never switches;
- `MIC` has no `aria-pressed`/toggle semantics and opens the correct configuration/diagnostic subsection;
- clicking `MIC` leaves the capture/VAD stream active;
- `SCREEN` triggers/focuses the real one-shot Vision flow;
- `PC CONTROL` opens the real activity/permission surface without changing permission by itself;
- state labels reflect real backend state and remain bounds-safe at all supported sizes;
- no wake word or push-to-talk is required after startup;
- TTS and low-confidence ambient speech do not self-trigger consequential commands.

---

# 44. VISUAL QA CHECKLIST

Before finalizing, inspect the complete UI and reject it if any of these are true:

- looks like a generic chatbot
- looks like a conventional admin dashboard
- permanent sidebar dominates the app
- too many visible cards on Home
- purple glow overwhelms text
- background is pure featureless black with no depth
- text contrast is poor
- glass panels are too transparent
- borders are too bright
- every element glows
- animation is distracting
- panels overlap chaotically
- Core looks like a loading spinner
- Home looks empty because it is unfinished rather than intentionally minimal
- quick-access grid is permanently visible or resembles a dashboard
- Configuration panel contains fake, no-op, unsafe, or unreadably cramped controls
- splash uses fake timed progress, is oversized, flashes white, or leaves two STONIC windows visible
- layout clips, escapes the work area, overlaps the Core, or becomes unreadably small at any required display/DPI case
- window controls remain visually dominant at rest or fail to appear reliably in the top-right reveal zone
- bottom `MIC`, `SCREEN`, or `PC CONTROL` is implemented as a toggle/switch
- typography looks like a game HUD
- UI uses inconsistent spacing/radii/icons
- fake data remains in production

---

# 45. HOME SCREEN ACCEPTANCE CRITERIA

The Home screen is accepted only when:

- STONIC Core is the immediate visual focal point.
- `S.T.O.N.I.C` is spelled exactly.
- no tagline exists.
- there is no permanent chat history.
- there is no permanent navigation sidebar.
- there is no dashboard card grid.
- the quick-access grid is transient, bounds-safe, and includes `CONFIG`.
- state is understandable without clutter.
- always-listening voice state is obvious without a wake-word prompt or push-to-talk control.
- bottom-left `MIC`, `SCREEN`, and `PC CONTROL` are present as action/status buttons and do not overlap the Core.
- clicking `MIC` opens voice configuration/status without disabling capture.
- top-right minimize/maximize/restore/close controls reveal on hover/focus and remain keyboard accessible.
- the complete Home composition fits and stays readable across the required display/DPI matrix.
- Core animation is smooth.
- idle view feels premium even when nothing is happening.
- secondary controls fade into the hierarchy.
- floating panels can open without destroying the Home composition.

---

# 46. FINAL DOMAIN ACCEPTANCE

Each major domain should have a real UI integration if the corresponding backend domain exists:

1. Core intelligence
2. Voice input
3. TTS/output
4. Conversation
5. Memory
6. Vision
7. Web/research
8. Computer/tools
9. Tasks/autonomy
10. Event/proactive system
11. Notifications
12. System monitoring
13. Diagnostics
14. Configuration (`CONFIG`)
15. Privacy/permissions
16. Plugins/skills
17. File/context interactions
18. Provider/service health
19. Application lifecycle

Do not invent missing backend functionality just to tick a UI checkbox. Clearly identify unavailable integrations.

---

# 47. IMPLEMENTATION PROCESS

Follow this sequence.

## Phase UI-0 — Audit

Before coding:

- inspect repository structure
- inspect existing UI
- inspect backend API/event contracts
- inspect state models
- inspect test infrastructure
- identify all working domains
- identify unfinished domains
- identify existing reusable UI components

Produce a short implementation map.

Do not delete functioning code blindly.

## Phase UI-1 — Foundation

Build/refactor:

- startup coordinator event binding and compact `INITIALIZING STONIC` splash/handoff
- design tokens
- global styles
- typography
- adaptive/DPI-aware shell and work-area-safe sizing
- window chrome with top-right hover/focus reveal
- bottom capability-action layer
- reusable controls
- accessibility foundation

## Phase UI-2 — STONIC Core

Implement:

- Core visual
- state machine binding
- always-listening/passive-ready versus active-utterance state binding
- voice amplitude
- state labels
- transient transcript/response
- performance optimization

## Phase UI-3 — Panel Infrastructure

Implement:

- panel registry
- panel manager
- dragging
- resizing
- focus/z-order
- placement
- responsive behavior
- panel persistence rules
- on-demand quick-access grid and mandatory `CONFIG` route

## Phase UI-4 — Command + System Surfaces

Implement:

- command palette
- notifications
- activity capsule
- confirmation system
- bottom `MIC`, `SCREEN`, and `PC CONTROL` real action routing

## Phase UI-5 — Domain Panels

Integrate real backend domains:

- conversation
- research
- vision
- memory
- tasks
- system
- diagnostics
- schema-backed Configuration panel and category grid
- plugins

## Phase UI-6 — Intelligence Orchestration

Connect STONIC/backend events to:

- Core states
- panel actions
- notifications
- task views
- confirmations
- transient responses

## Phase UI-7 — Polish

Perform:

- motion refinement
- responsive tuning
- complete Section 25.3 display/DPI matrix tuning
- splash and hot-corner motion refinement
- accessibility
- reduced motion
- visual consistency
- loading/empty/error states
- performance profiling

## Phase UI-8 — Integration Testing

Run complete automated and manual tests.

Fix failures before proceeding.

## Phase UI-9 — Final Acceptance

Perform a real end-to-end run of STONIC V2.

---

# 48. END-TO-END ACCEPTANCE SCENARIOS

Test realistic flows.

### Scenario A — Voice question

1. startup has completed and STONIC is in ready/passive-listening state
2. user speaks naturally without a wake word or push-to-talk
3. VAD detects the active utterance and the Core responds
4. real Nemotron partial transcript appears and stabilizes into a final transcript
5. Core enters understanding/thinking
6. response streaming begins
7. Supertonic begins real playback from stable spoken-text chunks
8. Core enters speaking and reflects actual playback state
9. response is shown appropriately
10. the user can interrupt playback and immediately speak again
11. Core returns to ready/passive listening while the microphone service remains active

### Scenario B — Open system monitor

User requests system status.

Expected:
- command recognized
- System panel opens
- real metrics appear
- Core remains visible
- panel can be moved/closed

### Scenario C — Research

User asks STONIC to research a topic.

Expected:
- task state appears
- Research panel opens
- real findings/sources populate
- errors are handled
- follow-up actions work

### Scenario D — Screen analysis

Expected:
- Vision state becomes visible
- real analysis is shown
- temporary overlays only represent real targets
- user can stop the operation

### Scenario E — Autonomous PC action

Expected:
- activity capsule appears
- action description is clear
- confirmation appears when required
- cancel works where supported
- result notification appears

### Scenario F — Diagnostics

Expected:
- panel reads actual health
- degraded services are distinguishable
- full diagnostic can be run
- useful failure details are accessible

### Scenario G — Backend interruption

Expected:
- UI remains alive
- connection state changes
- user is informed without spam
- reconnect occurs where supported
- UI returns to normal after recovery

### Scenario H — Startup splash

Expected:

- a small centered `INITIALIZING STONIC` splash appears first;
- real startup stages advance honestly;
- continuous listening is ready or explicitly degraded before handoff;
- the fully styled main window replaces the splash without a white flash, duplicate window, or indefinite spinner.

### Scenario I — Configure STONIC

Expected:

- the user opens the transient quick-access grid and selects `CONFIG`;
- the singleton Configuration panel opens with a responsive category grid;
- a supported visual setting previews/applies;
- a validated voice/device setting restarts only the owned voice service when necessary and returns to listening;
- a restart-required setting is labeled correctly;
- changes persist after restart and secrets never appear.

### Scenario J — Display and window controls

Expected:

- resizing and moving the window between different-DPI monitors preserves readable scale and bounds;
- panels, Core, bottom controls, grid, and notifications never overlap incorrectly or leave the work area;
- hovering/focusing the top-right corner reveals minimize, maximize/restore, and close;
- all native/keyboard window actions work while controls are hidden.

### Scenario K — Bottom capability actions

Expected:

- `MIC`, `SCREEN`, and `PC CONTROL` are normal action buttons rather than toggles;
- `MIC` opens the Voice configuration/diagnostic subsection and listening remains active;
- `SCREEN` opens/runs the real one-shot Vision workflow;
- `PC CONTROL` opens the permission/activity surface without silently changing permissions.

---

# 49. QUALITY BAR

The completed application should feel:

- premium
- cinematic
- intelligent
- calm
- fast
- intentional
- trustworthy
- futuristic without being gimmicky

The user should feel that STONIC is an intelligence occupying a dynamic workspace, not a website embedded in a desktop shell.

Every visible element must justify its presence.

---

# 50. IMPORTANT ANTI-PATTERNS

Do **not**:

- redesign the finalized concept
- introduce a permanent sidebar
- add a giant text input permanently beneath the Core
- make chat bubbles the dominant visual language
- copy ChatGPT/Claude/Gemini layouts
- use cyan as the primary accent
- use random bright colors
- put every backend metric on Home
- use fake terminal text for aesthetics
- use meaningless animated graphs
- render fake AI activity
- show fabricated task progress
- expose hidden reasoning
- add features unsupported by the backend and pretend they work
- replace working STONIC functionality with mocks
- remove tests to make builds pass
- suppress errors instead of fixing them
- hard-code user-specific paths
- hard-code API keys
- reintroduce a wake-word requirement, push-to-talk requirement, or Home microphone toggle
- use fake timed startup progress
- scale the entire UI down as one transformed canvas to force it to fit
- make hover the only way to access native window commands
- break existing backend contracts unnecessarily

---

# 51. COMPLETION DEFINITION

STONIC V2 UI is **not complete** merely when it looks good.

It is complete only when:

- the finalized visual system is implemented
- the compact real-stage startup splash and clean main-window handoff work
- the Core represents real STONIC state
- STONIC is continuously ready for speech after startup without wake word or push-to-talk, and `MIC` is not a toggle
- floating panels work reliably
- the quick-access grid and schema-backed `CONFIG` panel work reliably
- major existing backend domains are integrated
- voice interaction works end-to-end with real Nemotron STT and Supertonic TTS events
- commands can open/control relevant UI
- autonomous actions are visible and controllable
- errors/degraded states are handled
- accessibility basics work
- UI remains responsive
- every required display/DPI/window-state case fits without clipping or unusably small UI
- top-right hover/focus window controls preserve native reliability
- existing tests still pass
- new UI tests pass
- Windows behavior is validated
- no critical mock data remains
- no known critical integration errors remain
- the complete application launches and shuts down cleanly

---

# 52. EXECUTION PROTOCOL FOR THE CODING AGENT

When this prompt is provided inside the existing STONIC V2 development conversation/project:

1. **Read the existing project and current status first.**
2. Do not assume a feature is missing until you inspect it.
3. Preserve previously completed phases.
4. Create/update a UI implementation checklist.
5. Work phase-by-phase.
6. After each phase, run relevant tests.
7. Fix regressions immediately.
8. Keep changes modular.
9. Do not stop after producing mockups.
10. Continue through real backend integration.
11. Do not declare completion while known critical failures remain.
12. At the end, provide:
   - implemented UI domains
   - files/components changed
   - tests executed
   - test results
   - remaining warnings/limitations
   - exact run instructions

If an ambiguity arises, choose the solution most consistent with:

**Minimal Home + STONIC Core + purple/obsidian visual identity + on-demand glass panels + real backend integration + transparency for autonomous actions.**

---

# 53. FINAL DIRECTIVE

Build the complete STONIC V2 UI according to this locked specification.

The final experience must center around the living **S.T.O.N.I.C Core**, with functionality materializing around it only when needed.

Do not create another dashboard.

Do not create another chatbot.

Create a coherent desktop intelligence interface that feels like **STONIC**.

---

# PART III — UNIFIED FINAL RELEASE DIRECTIVE

STONIC V2 is complete only as the **combined product** described by Part I and Part II.

The coding agent must finish the backend/core phases, the locked voice stack, the locked UI phases, integration testing, Windows validation, and release hardening before declaring completion.

The release build must therefore be all of the following at once:

- a real clean-rebuild STONIC backend;
- a real low-latency local voice assistant using Nemotron + Silero VAD + Supertonic;
- a real always-listening voice lifecycle with no wake-word or push-to-talk requirement and no Home microphone toggle;
- a real Windows computer-capable assistant with security/verification;
- a real context, memory, vision, web, task, event, plugin, personalization, diagnostics, gaming, and developer system;
- the locked purple/obsidian **S.T.O.N.I.C Core** desktop experience with on-demand floating glass panels;
- the compact real-progress `INITIALIZING STONIC` splash, transient quick-access grid with `CONFIG`, complete schema-backed Configuration panel, adaptive display/DPI layout, bottom capability actions, and hover-reveal top-right window controls;
- fully integrated rather than two disconnected projects;
- testable, diagnosable, recoverable, maintainable, and honest about degraded capabilities;
- free of production stubs, fake success responses, fake telemetry, fake task progress, and hidden fallback substitutions.

Do not stop at architecture notes. Do not stop at backend completion. Do not stop at a visual mockup. Do not stop while a known critical integration failure remains.

**Build → test → fix → verify → integrate → test again → release-ready.**
