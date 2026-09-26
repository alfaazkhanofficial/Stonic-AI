# STONIC V3.0 — Agentic Assistant Spec

Status: DRAFT for approval. Builds on the finished V2 codebase (stonic_v2/). Nothing in V2 is thrown away; V3 upgrades it.

## 1. Vision

**This is an upgrade of the existing STONIC, not a scratch project.** V3 is built on top of the current, working codebase. No rewrite, no new project root, no re-planning of what already works. Every phase adds to or improves existing modules and keeps the whole existing test suite green.

STONIC V2 is a capable assistant that answers commands. STONIC V3 is an **agent**: you give it a goal ("prepare my Beyond Evidence upload folder", "find and fix why my build fails"), and it plans, acts on the PC, checks its own results, recovers from failures, and reports back — by voice or text — without you micromanaging steps.

**Success test:** a multi-step goal that V2 could not finish without hand-holding is finished by V3 in one request, and STONIC can explain what it did and why.

**Hard constraints (unchanged):**
- Software only. Controls the PC, nothing else — no hardware/IoT.
- **Full PC authority.** No folder, drive, app, or setting is off-limits by design. Compound requests must work in one go, e.g. *"make a folder on my desktop named Altrex, delete the Jarvis folder in C drive, and uninstall the X app."* STONIC runs elevated when a task needs it.
- Windows, voice-first, cyan/obsidian UI.
- Runs on a Ryzen 5 5500U, no dedicated GPU → all heavy inference is cloud; local code must be CPU-light.
- Honest degradation everywhere: never fake a capability that isn't connected.

Codebase reality check: see `docs/V3_AUDIT.md` (P0). Key facts: files are confined to a workspace, no shell/uninstall/registry/elevation exist, routing is regex-based, and approvals are per step. V3 changes each of these deliberately.

## 2. Workstreams

### A. Agent Core (the biggest change)
Replace the fixed 6-stage pipeline with a real **goal loop**:

`Goal → Plan → Act → Observe → Verify → Reflect → (re-plan | finish)`

- **Model-driven routing** replaces the regex router (`needs_planner` / `is_live_web_request`) in `CoreService.chat`: the model decides whether to answer, ask, or act. Uses the existing `OpenAICompatibleProvider` (xKiro endpoint, DPAPI-stored key); the router picks a fast model for simple steps and a stronger one for planning/reflection from whatever the endpoint offers, and adds native tool calling next to the existing JSON `Decision` path (kept as fallback).
- **Native tool calling**: tools expose JSON schemas; the model chooses tools, parallel calls allowed when independent.
- **Plan object**: explicit, editable, persisted. Steps have dependencies, success checks, and status. Re-planning keeps completed work.
- **Verification is mandatory**: every step that changes state needs a check (file exists, window title changed, page contains text). No "done" without evidence.
- **Reflection**: on failure, classify the error (bad args / missing precondition / permission / environment), choose retry, alternative tool, ask-the-user, or abort. Bounded retries.
- **Budgets**: max steps, max wall-clock, max tokens per goal. Exceeding a budget stops cleanly with a summary of progress.
- **Checkpoint/resume**: goal state persists after every step (reuse Phase 6 TaskEngine discipline); survives restart; cancellable via the existing CancellationToken.
- **Background goals**: long tasks run while the user keeps talking; progress streams to the activity feed and voice ("still working on X — 3 of 5 steps done").
- **Autonomy levels** per goal: `ask-every-step` / `ask-on-risk` (default) / `autonomous-within-scope`. All levels go through PermissionGate.

### B. Reasoning & Memory
- **Working memory**: per-goal scratchpad (facts found, decisions, open questions) injected into each step, size-bounded.
- **Episodic memory**: every finished goal stores outcome, steps that worked, failures, and lessons.
- **Semantic memory**: vector store (ChromaDB, cloud-embedding or lightweight local embedding — decide in build for CPU cost) for documents/notes/past conversations.
- **Procedural memory (skills)**: successful multi-step routines can be saved as named skills the agent reuses ("upload prep", "clean downloads"). Saving a skill needs user approval; same rule as Personalization.
- **Retrieval discipline**: bounded, relevance-ranked, keyword+vector hybrid; keep the Phase 4 regression test (recency must not rescue an irrelevant memory).
- **Consolidation**: nightly/idle job merges duplicates, decays stale memories, never deletes without user-visible rules.
- **Personalization** stays approval-gated and in its own database (unchanged).
- **"Feels smart" targets:** resolves follow-ups ("do that again but for yesterday's file"), asks at most one clarifying question and only when truly ambiguous, remembers corrections permanently.

### C. Voice & Live Conversation
- **Already built** (`stonic/voicelive/`): Gemini Live speech-to-speech, echo guard, push-to-talk, barge-in, routed through `CoreService.chat` via one `ask_stonic` tool. V3 keeps it and deepens it (below) instead of rebuilding.
- **Voice is a front-end to the agent core**, not a separate brain: Live-session tool calls bridge into the same goal loop, permission gate, and audit log.
- Barge-in and interruption map onto the existing InterruptionController/state machine.
- **Spoken progress and confirmations**: short, natural ("Deleting 14 files in Downloads — say yes to confirm").
- **Proactive speech** respects quiet hours and the throttle from Phase 7.
- Modes: push-to-talk (default), open-mic conversation, text-only fallback when the Live connection is down (honest status in the UI).
- Latency budget tracked and shown in diagnostics.

### D. PC Control (new capabilities)
- **Full-system control layer (no Windows limitations):**
  - **Elevation:** STONIC runs with a one-time admin install and a persistent elevated helper service, so it can act on `C:\`, Program Files, system folders, registry, services, and startup entries without a UAC prompt each time. Handles locked/in-use files (kill the owning process, schedule delete-on-reboot as fallback), long paths, and permission/ownership fixes (takeown/icacls).
  - **Apps:** install/uninstall/update via winget, registry uninstall strings (silent switches), MSI, and Store/UWP (Appx) packages; leftover cleanup (folders, registry keys) after uninstall. Fuzzy-match app names ("x app") against the installed list and confirm the match when ambiguous.
  - **System:** processes, services, scheduled tasks, startup items, environment variables, registry, network/Wi-Fi/firewall settings, display/audio/power settings, Windows features, drivers, disk cleanup.
  - **Files:** create/move/copy/delete/rename anywhere, on any drive, including bulk operations, with the compound-request planner splitting one sentence into ordered steps.
  - **Shell:** PowerShell/cmd execution as a first-class tool for anything not covered by a dedicated tool.
  - **Fallback:** if no API or command exists, the computer-use loop (UIA → vision) drives the GUI.
- **Screen awareness**: prefer the Windows UI Automation tree (pywinauto/uiautomation) for reading and clicking controls; fall back to screenshot + vision model; OCR as last resort.
- **Computer-use loop**: observe screen → decide action → act → re-observe, for apps without APIs. Every action verified.
- **App skills**: reliable recipes for common apps (browser, Explorer, VS Code, Discord, OBS, video editors as feasible). Recipes are data files, not hard-coded.
- **File intelligence**: search by content, batch rename/organize with a dry-run preview.
- **Browser agent**: multi-tab research with cited findings (search engine access on the real machine, not the sandbox).
- **Undo journal**: reversible actions (moves, renames, writes) are logged so "undo that" works.
- **Kill switch**: global hotkey immediately stops all agent action.

### E. Reliability & Polish (real-machine work)
- Full validation pass on a real Windows machine for every "real code, untestable in sandbox" backend (Windows automation, pywin32, audio).
- AudioRingBuffer pre-roll and mic latency tuning on real hardware.
- Electron/Windows packaging hardened: installer, auto-start, tray, clean uninstall, auto-update channel.
- Structured logging + one-click diagnostic bundle; crash recovery restores the last goal state.
- **Performance budgets** on the 5500U: idle CPU under 3%, cold start under 8 s, UI stays at 60 fps while a goal runs.
- Error taxonomy with human-readable messages; no silent failures.

### F. Signature Agentic Features (what makes it feel like JARVIS, not a command box)
- **Sub-agents:** the main agent delegates to focused workers (Operator for PC actions, Researcher for web/docs, Coder for scripts and fixes) that run in parallel with their own budgets and report back. One supervisor keeps the user-facing thread simple.
- **Screen context:** "what's this error?", "summarize this page", "reply to this" work on whatever is on screen right now (UIA text first, screenshot+vision if needed), on request only, never passive recording.
- **Proactive suggestions:** from observed patterns and context, STONIC offers help ("you've opened these 4 files together every morning — save as a workspace?"), always throttled, dismissible, and approval-gated to save anything.
- **Explainability:** "why did you do that?" and "what did you change today?" answered from the audit log in plain language. Every goal ends with a short, honest report: done, not done, and what to check.
- **Self-improvement loop:** after failures STONIC drafts a lesson or a skill fix, shows it, and applies it only when approved. The benchmark suite re-runs to prove it helped.
- **Offline-lite mode:** if the cloud is unreachable, fall back to a small local model and deterministic tools for basic commands (files, apps, timers, notes), clearly labeled as reduced capability. No pretending.
- **Creator workflow skill pack (optional):** ready-made skills for video-project folder setup, asset organization, upload prep, and batch file renaming, as shipped examples of the skill system.

## 3. Safety & Permissions
- Authority is full-system by default; safety is about **confirmation and recovery, not restriction**.
- Risk tiers: `read` (auto) / `create-reversible` (auto) / `delete-or-uninstall` (one spoken/typed confirmation showing the exact resolved targets, e.g. "Delete C:\Jarvis (412 files, 1.2 GB) and uninstall X — yes?") / `system-critical` (Windows folder, boot files, drivers, disk formatting: double confirmation with the resolved path read back).
- Compound requests get **one combined confirmation** for all destructive steps, not one per step. A "don't ask again for this kind of action" toggle is available per user.
- **Recovery net:** deletes go to the Recycle Bin when possible; a System Restore point is created before uninstalls and system changes; the undo journal covers everything else.
- Optional user-defined **protected paths** (default: only Windows core and STONIC's own files) that require double confirmation; the user can edit or clear the list.
- Every action audited (who/what/why/result); audit log fails closed.
- Prompt-injection defense: content read from web pages/files/screens is data, never instructions; injected instructions are flagged, not followed.
- No secrets on disk in plaintext; keys via OS credential store.

## 4. Evaluation ("smartness" suite)
A scripted benchmark of 30+ realistic goals across the four workstreams, run against a deterministic fake LLM (for logic) and optionally a live model (for quality).

Tracked per goal: success, steps taken, retries, time, user interruptions needed, verification passed. A regression in the suite blocks a phase from being called done.

Sample goals: organize a messy folder with dry-run then apply; research a topic and save a cited note; fix a failing script by reading errors and editing; multi-app workflow (open → copy → paste → save); recover after a mid-task failure and resume after restart.

## 5. Build Phases

| Phase | Deliverable |
|---|---|
| V3-P0 | Ingest the current STONIC codebase (uploaded by you), audit it, map modules to V3 workstreams, run the existing tests, add the eval harness. No behavior changes |
| V3-P1 | Real LLM provider layer + model router + native tool calling |
| V3-P2 | Goal loop: plan / act / observe / verify / reflect, budgets, checkpoint/resume |
| V3-P3 | Working + episodic memory, hybrid retrieval, consolidation |
| V3-P4 | Skills (procedural memory), sub-agents (Operator/Researcher/Coder), approval flow |
| V3-P5 | Deepen existing Gemini Live voice: spoken progress and confirmations from the goal loop, richer tool bridge than the single `ask_stonic`, latency metrics |
| V3-P6 | Full-system control layer (elevated helper, app install/uninstall, registry/services/shell) + UIA-first screen awareness + computer-use loop |
| V3-P7 | App recipes, file intelligence, browser agent, undo journal |
| V3-P8 | Safety hardening: tiers, injection defense, kill switch, explainability, offline-lite mode |
| V3-P9 | UI upgrades: goal view, plan timeline, live progress, diagnostics; screen context and proactive suggestions |
| V3-P10 | Real-machine validation (validate_windows.py loop), self-improvement loop, packaging, performance, release |

## 6. Build Rules (carried over from V2)
- **Upgrade in place.** Extend existing modules and interfaces; replace a component only when it can't meet the V3 spec, and say why. Reuse existing code, tests, config, and UI.
- Work from the codebase as it exists now (including any changes made outside my sessions, such as the voice removal), not from an older snapshot.
- Real code and real tests each phase; honest degradation instead of stubs.
- Fresh-extraction test run before every delivery; delivered as an updated zip plus a smoke script.
- After every bug fix or feature: a quick performance pass on that change (blocking calls, needless sequential awaits, heavy imports that could be lazy, redundant polling or work that could be cached).
- Backward compatibility: verify zero pre-existing test breakage before widening any interface.
- Anything needing real hardware or Windows is labeled clearly and listed in a validation checklist rather than claimed as tested.
- **Real-machine validation kit.** The build sandbox is Linux, so every Windows-only backend ships behind an interface with a fake backend for tests, plus a `validate_windows.py` you run on your PC. It exercises each capability on safe temporary targets (temp folders, a dummy installer, test registry keys) and writes a report you paste back to me, so fixes are driven by real results.
- Minimal-file bias where reasonable; Claude makes open technical decisions and records them in a DECISIONS section.

## 7. Open Decisions (Claude will decide during build unless overridden)
- Strong planning model choice via the router.
- Embedding approach (cloud vs light local) given CPU limits.
- UIA library (pywinauto vs uiautomation) after a real-machine comparison.
- Skill file format (YAML recipes).

## 8. Definition of Done for V3.0
1. All 30+ benchmark goals pass on the fake LLM; at least 80% pass on a live model.
2. A voice-only session completes a multi-step goal end to end, including a spoken confirmation and a barge-in.
3. The compound command "make a folder named Altrex on my desktop, delete the Jarvis folder in C drive, and uninstall the X app" completes from a single request on a real Windows machine, with one combined confirmation.
3b. A goal interrupted by a restart resumes at the exact step.
4. Windows validation checklist fully ticked on a real machine.
5. Installer builds, installs, updates, and uninstalls cleanly.
