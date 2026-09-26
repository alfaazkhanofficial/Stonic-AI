# STONIC V3 — P0 audit (2026-09-24)

Baseline before any V3 change: **265 passed, 2 skipped** (`pytest --ignore=tests/e2e`, Linux sandbox, Python 3.12.3).
After P0 (eval harness added, no behavior change): **272 passed, 2 skipped**. UI/Electron suites (`npm run test:ui`, `verify-desktop.mjs`) were not run here and remain Windows-side checks.

## What exists (and is kept)
| Area | Module | State |
|---|---|---|
| Provider | `providers/llm.py` `OpenAICompatibleProvider` (xKiro, default model `minimax/minimax-m3:free`) | Solid: retries, SSE error frames, DPAPI key. `decide()` returns a JSON `Decision` (answer/clarify/plan). **No native tool calling.** |
| Orchestration | `core/service.py` `CoreService.chat`, `advance` | Regex router (`needs_planner`, `is_live_web_request`) decides plan vs plain chat. Plan-then-continue loop capped at 5 stages. |
| Tasks | `tasks/engine.py`, `tasks/contracts.py` | Persisted jobs, `$step` references, exact-input approvals, cancel, uncertain-outcome protection. Good base for checkpoint/resume. |
| Permissions | `security/permissions.py`, `tools/registry.py` | 4 levels; approvals are single-use, 120 s TTL, bound to an exact argument fingerprint. Approval is per step. |
| Tools (45) | `tools/{workspace,windows,browser,gaming,knowledge}.py`, providers | See gaps below. |
| Memory | `tools/knowledge.py`, SQLite FTS5 in `storage/database.py` | Notes/tasks/memory + preferences. Keyword search only, no episodic/procedural memory. |
| Voice | `voicelive/*` (Gemini Live, echo guard, push-to-talk) | **Already built.** Bridges to the core through one `ask_stonic` tool -> `core.chat`. Docs still say voice is retired. |
| Events | `events/*` | Scheduler, triggers, quiet hours, throttling, SSE. |
| Skills | `skills/manager.py` | External skill bundles with trust lifecycle. Not procedural memory. |
| UI | `ui/*`, `desktop/*` (React + Electron) | Panels for chat, activity, skills, computer control, voice, settings. |

## Gaps against the V3 spec
1. **Files are confined to a workspace** (`WorkspaceTools.resolve` rejects anything outside it; excludes `.git`, `.ssh`, ...). No access to C:\ generally.
2. **No shell, app install/uninstall, registry, services, elevation.** `developer.run` only allows 5 fixed commands (`python_tests`, `npm_tests`, `npm_build`, `git_status`, `git_diff`).
3. **Routing by regex**, not by the model. Phrases the regex does not recognise fall through to plain chat and no tools are used. This is the biggest cause of "not smart".
4. **Loop is shallow:** plan -> run -> at most 4 continuations; no reflection/error classification beyond one repair and two replans; no budgets in tokens/time; no parallel tool calls.
5. **Approvals are per step**, so a compound request needs several separate approvals.
6. **Memory** has no working scratchpad, episodic lessons, vector/hybrid retrieval, consolidation, or procedural skills.
7. **Voice bridge is a single tool** (`ask_stonic`), so no spoken progress/confirmation flow from the goal loop.
8. **Screen awareness:** OCR + approved image upload only; no UI Automation tree, no computer-use loop.
9. **No undo journal** for moves/writes beyond the file recovery folder for deletes.

## Hygiene findings (fix in V3-P10, not changed in P0)
- `stonic/` contains stray patch artifacts: `APPLY-STONIC-FINAL-FIX.cmd`, `FINAL_PATCH_MANIFEST.json`, `FINAL_PATCH_README.txt`, `SELF_ECHO_FIX.txt`, `VOICE_LISTENER_REPLACEMENT.txt`. They describe the removed voice stack and should not ship.
- `README.md`, `docs/ARCHITECTURE.md`, `docs/BUILD_STATUS.md` say voice is retired, but `voicelive/` is present and `docs/VOICE.md` documents it.
- `pyproject.toml` name/version are `stonic-v2` / `0.2.0`; `.env.example` mentions only xKiro (Gemini key is stored via DPAPI).
- `RELEASE_VERIFICATION_2026-09-18.md` cites a 54-test baseline; actual is now 265.

## Module -> workstream map
| Workstream | Extend | New |
|---|---|---|
| A Agent core | `core/service.py`, `tasks/engine.py`, `providers/llm.py` | `agent/loop.py` (goal loop), model router, native tool-calling adapter |
| B Reasoning & memory | `tools/knowledge.py`, `storage/database.py` | working/episodic/procedural memory tables, hybrid retrieval, consolidation job |
| C Voice | `voicelive/service.py` | bridge for progress/confirmations; multiple tools instead of one |
| D PC control | `tools/windows.py`, `tools/workspace.py`, `security/permissions.py` | `system/` layer (elevated helper, apps, registry, services, shell), UIA backend, undo journal |
| E Reliability | `diagnostics/health.py`, `scripts/package-windows.py` | `scripts/validate_windows.py`, installer/update work |
| F Signature | `events/triggers.py`, `skills/manager.py` | sub-agents, screen-context, explainability report, offline-lite path |

## Eval harness (added in P0)
`tests/evals/{harness,scenarios}.py`, `tests/test_evals.py`, `scripts/run-evals.py`.
Runs scripted goals through the real CoreService/TaskEngine/PermissionGate. Currently **5 baseline scenarios pass**, **16 target scenarios are pending** (each names the V3 phase that must deliver it). Pending scenarios are reported, never faked.

## Final status of this build (all phases attempted in one pass)

| Phase | Status | Notes |
|---|---|---|
| P0 Baseline audit | Done | This document; eval harness scaffolding. |
| P1 Provider + router | Done | `providers/llm.py: act()`, `agent/router.py`. Provider is your configured agent endpoint (Gemini by default), not Groq. |
| P2 Goal loop | Done | `agent/loop.py`: plan/act/verify/reflect, budgets, checkpoint/resume, one combined confirmation per batch. |
| P3 Memory | Done | `agent/memory.py`: hybrid keyword+vector retrieval (dependency-free hashed embedder), episodes, consolidation scheduled every ~4h. |
| P4 Skills | Done | `agent/skills.py`: propose/approve/reject; `system.run_skill` replays a saved routine and still flags sensitive nested steps. |
| P5 Voice | Done | Existing Gemini Live (`voicelive/`) automatically routes through the agent via `ask_stonic`; added `confirm_pending_action` for spoken approve/deny, blocked for system-critical targets. |
| P6 Full-system control | Done | `tools/system_control.py`: files/folders anywhere, app uninstall (winget, fuzzy-matched), registry, services, shell. The Altrex/Jarvis/uninstall example is a passing end-to-end test. |
| P7 App skills / undo / organize | Partial | Undo journal and `system.organize_folder` (dry-run + apply) are done. A multi-tab browser research agent and a library of named per-app recipes (VS Code, OBS, etc.) are not built - see PENDING in `tests/evals/scenarios.py`. |
| P8 Safety hardening | Done | Risk tiers, system-critical auto-detection (Windows root/drive root, always confirmed), prompt-injection defense language, kill switch (`/api/agent/stop`). Offline-lite still means "falls back to the old deterministic path", not a bundled small local model. |
| P9 UI | Partial | `TaskActivity.tsx` now shows agent goals with approve/decline and a kill-switch button; `Skills.tsx` shows pending/active learned routines; a new "Agent" Settings category renders automatically from the schema. A dedicated plan-timeline/live-progress view was not built. `npm run typecheck` and `npm run build` both pass. |
| P10 Validation & packaging | Partial | `scripts/validate_windows.py` is new: run it on your PC for a real PASS/FAIL/SKIP report (file ops, winget, registry, shell, services, elevation, UI Automation libraries, audio devices, Gemini key). Electron packaging itself (`scripts/package-windows.py`) was not changed and was not run here (Linux sandbox). `npm run test:ui` (Playwright/msedge) must run on Windows.

**Test count:** 265 (V2 baseline) -> 352 passed, 2 skipped (this build), zero regressions. `npm run typecheck` and `npm run build` both pass.

**Hygiene:** removed the stray `APPLY-STONIC-FINAL-FIX.cmd`, `FINAL_PATCH_MANIFEST.json`, `FINAL_PATCH_README.txt`, `SELF_ECHO_FIX.txt`, `VOICE_LISTENER_REPLACEMENT.txt` files (all described a since-completed voice migration). Corrected `README.md` and `docs/BUILD_STATUS.md`, which still said voice was retired even though `voicelive/` is fully implemented. Bumped package/version to `stonic-v3` / `0.3.0`.

**A safety-relevant bug found and fixed during this build:** the first version of the agent's self-approval grant fingerprinted the model's raw tool-call arguments, but `PermissionGate.authorize` fingerprints the tool's *validated/normalized* arguments (Pydantic defaults included) - e.g. `files.write`'s `expected_sha256: None` default. The mismatch meant every SENSITIVE/CRITICAL tool call with an optional field was silently denied. Fixed in `agent/loop.py:_self_grant` and covered by the full-system compound test.

## Still open after this build
- Multi-tab browser research agent (currently one query in, one answer out).
- Named per-app recipe library (VS Code, OBS, Discord, etc.) beyond the generic full-system tools.
- A true offline-lite small local model; the current fallback is the pre-existing deterministic plan/answer path.
- A dedicated goal/plan-timeline UI view (progress currently surfaces via the extended Task Activity panel and the events feed).
- Everything in `scripts/validate_windows.py` needs to actually be run on your Windows machine - a Linux sandbox cannot see winget, the registry, real elevation, or real audio devices.
- Electron packaging (`scripts/package-windows.py`) and `npm run test:ui` need a Windows/msedge run.
