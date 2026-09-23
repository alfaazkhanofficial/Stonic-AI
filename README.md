# STONIC

**A JARVIS-style AI assistant for Windows** — voice-first, always-listening, fully software-based. No hardware or IoT control — STONIC lives entirely on your PC.

![Status](https://img.shields.io/badge/status-v1.0.0-brightgreen)
![Platform](https://img.shields.io/badge/platform-Windows-blue)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

---

## ✨ Features

- **13-domain core architecture** — typed contracts, versioned config, explicit state machine, permission-gated actions, full audit logging
- **6-stage reasoning pipeline** — Understanding → Planning → Execution → Verification → Response
- **Voice** — real-time speech-to-speech (Gemini Live-based), echo guard, push-to-talk, barge-in interruption
- **Computer control** — sandboxed file operations, permission-gated command execution, window/input/clipboard control, browser automation
- **Memory & context** — persistent long-term memory (SQLite), corruption detection & recovery, relevance-ranked recall, follow-up resolution
- **Autonomous tasks** — dependency-graph task engine with bounded retries, survives restarts mid-task
- **Productivity suite** — reminders, timers, todos, notes, recurring tasks, deterministic daily briefing
- **Proactive behavior** — quiet hours, notification throttling, smart detectors (disk space, task completion, stuck patterns)
- **Personalization** — learns from repeated behavior via a propose → approve/reject → forget lifecycle; never auto-applies unconfirmed patterns
- **Desktop UI** — cyan/obsidian interface with a central core orb, domain nodes, activity feed, and a live chat/tasks/notes panel

---

## 📦 Installation

1. Download the latest installer from [Releases](../../releases)
2. Run `STONIC-Setup-v1.0.0.exe`
3. Launch STONIC and complete first-run setup (microphone + permissions)

### Requirements

- Windows 10/11
- Microphone (for voice interaction)
- Internet connection (for voice + web intelligence features)

---

## 🛠 Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI |
| Voice | Gemini Live (speech-to-speech), echo cancellation |
| Storage | SQLite (separate memory + personalization stores) |
| Frontend | Single-page web UI (cyan/obsidian theme) |
| Automation | Playwright, native Windows APIs |

---

## 🚀 Quick Start (from source)

```bash
git clone https://github.com/alfaazkhanofficial/Stonic-AI.git
cd stonic
.\Setup-Stonic.cmd
.\Start-Stonic.cmd
```


---

## 📁 Project Structure

```
stonic/
├── stonic/
│   ├── api/           # FastAPI backend, REST/WebSocket endpoints
│   ├── core/          # State machine, permission gate, orchestrator
│   ├── voice/         # Voice pipeline (STT/TTS, VAD, echo guard)
│   ├── memory/         # Long-term memory + personalization stores
│   └── tasks/          # Autonomous task engine
├── web/
│   └── index.html      # Desktop UI frontend
├── scripts/             # Launcher and smoke-test scripts
└── tests/                # Test suite
```

---

## ⚠️ Known Limitations

- Calendar integration is a stubbed provider — not yet connected to a real calendar service
- Voice stack was recently rebuilt on Gemini Live — validate mic input/output on first run

---

## 🤝 Contributing

This is currently a solo project. Issues and suggestions are welcome — feel free to open an issue.

## 📄 License

MIT — see [LICENSE](LICENSE) for details.
