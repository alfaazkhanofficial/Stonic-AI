# S.T.O.N.I.C.

### Personal AI Assistant for Windows

**S.T.O.N.I.C.** is a Windows-first personal AI assistant designed to bring conversational AI, computer control, browser automation, web research, productivity tools, vision, and voice interaction into a single desktop application.

The project is built around a simple idea:

> **Make interacting with your computer feel more natural, direct, and assistant-like.**

---

## Overview

STONIC combines a modern desktop interface with a modular AI backend and an extensible tool system.

The current architecture includes:

* AI conversation
* Windows computer control
* Browser automation
* Web research
* Vision support
* Voice interaction
* Task execution
* Productivity features
* Skills and tools
* Local application state
* Security and permission layers
* Automated testing

The project is designed primarily for **Windows 11**.

---

## Core Features

### AI Assistant

* Conversational AI
* Multi-turn conversations
* Context-aware interactions
* Tool-assisted responses
* Task-oriented workflows
* Provider-based AI architecture

### Computer Control

STONIC can interact with the Windows environment through dedicated tools and services.

Examples include:

* Opening applications
* Windows interaction
* Workspace operations
* Computer-oriented tasks
* Multi-step actions

### Browser Automation

The browser subsystem supports:

* Browser launching
* Search workflows
* Navigation
* Element interaction
* Multi-step browser tasks
* Selector-based interaction
* Replanning when page state changes

### Web Research

STONIC includes a dedicated web research layer for tasks requiring current online information.

The architecture separates web retrieval from normal conversational reasoning.

### Vision

A dedicated vision provider layer is included for image-aware AI workflows and future visual computer interaction.

### Voice

STONIC includes a dedicated voice subsystem with support for:

* Audio processing
* Voice controls
* Echo handling
* Live voice processing
* Voice routing
* Voice service management
* Voice-specific testing

### Productivity

The application includes infrastructure for:

* Events
* Scheduling
* Triggers
* Briefings
* Task activity
* Records
* System monitoring

### Skills & Tools

STONIC uses an extensible tool architecture with dedicated modules for:

* Browser
* Windows
* Workspace
* Knowledge
* Gaming
* Tool registration and management

---

## Architecture

```text
                    ┌──────────────────────┐
                    │      STONIC UI       │
                    │ React + TypeScript   │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │    Desktop Shell     │
                    │ Electron + Preload   │
                    └──────────┬───────────┘
                               │
                               ▼
                    ┌──────────────────────┐
                    │     Python API       │
                    │       FastAPI        │
                    └──────────┬───────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
    ┌───────────┐       ┌────────────┐      ┌────────────┐
    │   Core    │       │ Providers  │      │   Tasks    │
    │ Services  │       │ LLM/Vision │      │ Execution  │
    └─────┬─────┘       └─────┬──────┘      └─────┬──────┘
          │                    │                    │
          └────────────────────┼────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          │                    │                    │
          ▼                    ▼                    ▼
    ┌───────────┐       ┌────────────┐      ┌────────────┐
    │   Skills  │       │  Browser   │      │  Windows   │
    │   & Tools │       │ Automation │      │   Tools    │
    └───────────┘       └────────────┘      └────────────┘
```

---

## Tech Stack

### Frontend

* React
* TypeScript
* Vite
* CSS

### Desktop

* Electron
* Electron Preload Bridge
* Windows startup/packaging scripts

### Backend

* Python
* FastAPI
* Uvicorn

### Testing

* Pytest
* Playwright
* Browser verification
* Desktop verification
* Voice subsystem tests
* Integration and hardening tests

### Package Management

* npm
* Python virtual environment
* `uv.lock`
* `package-lock.json`

---

## Project Structure

```text
STONIC
│
├── desktop/              # Electron desktop shell
├── docs/                 # Technical documentation
├── scripts/              # Setup, verification and build scripts
├── stonic/               # Python backend
│   ├── app/
│   ├── config/
│   ├── core/
│   ├── diagnostics/
│   ├── events/
│   ├── providers/
│   ├── security/
│   ├── skills/
│   ├── state/
│   ├── storage/
│   ├── tasks/
│   ├── tools/
│   └── voicelive/
│
├── tests/                # Automated tests
├── ui/                   # React frontend
│   └── components/
│
├── .env.example
├── package.json
├── package-lock.json
├── pyproject.toml
├── uv.lock
├── playwright.config.ts
├── tsconfig.json
└── vite.config.ts
```

---

## Requirements

Recommended development environment:

* **Windows 11**
* **Python 3.12+**
* **Node.js 22+**
* **npm**
* **Git**

---

## Installation

### Clone the repository

```powershell
git clone https://github.com/alfaazkhanofficial/Stonic-AI.git
cd Stonic-AI
```

### Create Python environment

```powershell
py -3.12 -m venv .venv
```

Activate it:

```powershell
.\.venv\Scripts\Activate.ps1
```

### Install dependencies

```powershell
python -m pip install --upgrade pip
pip install -e .
npm install
```

### Environment configuration

Create a local environment file:

```powershell
Copy-Item .env.example .env
```

Configure the required settings locally.

**Never commit API keys, credentials, `.env`, databases, or other private runtime data.**

---

## Running STONIC

### Windows

```powershell
.\Start-Stonic.cmd
```

### Development

```powershell
npm run dev
```

The exact development workflow may depend on the current desktop/backend configuration.

---

## Testing

### Python tests

```powershell
pytest
```

### Playwright tests

```powershell
npx playwright test
```

### Browser verification

```powershell
python scripts/verify-browser.py
```

### Desktop verification

```powershell
node scripts/verify-desktop.mjs
```

Additional verification scripts are available in:

```text
scripts/
```

---

## Security

STONIC uses a dedicated security layer for controlled system interaction.

Major areas include:

* Permissions
* Process handling
* Network controls
* Secret management
* Tool execution controls

The intended execution flow is:

```text
User Request
     ↓
AI Reasoning
     ↓
Task Selection
     ↓
Permission / Security Checks
     ↓
Tool Execution
     ↓
Result
     ↓
Assistant Response
```

---

## Privacy

STONIC is designed as a personal desktop assistant.

Depending on configuration, the application may store local:

* Application state
* Preferences
* Conversation-related data
* Task information
* Runtime information

Machine-specific and sensitive files must remain outside the public repository.

---

## Documentation

Detailed technical documentation is available in [`docs/`](docs/).

Important documents include:

* [`ARCHITECTURE.md`](docs/ARCHITECTURE.md)
* [`BUILD_STATUS.md`](docs/BUILD_STATUS.md)
* [`MASTER_SPEC_REFERENCE.md`](docs/MASTER_SPEC_REFERENCE.md)
* [`VOICE.md`](docs/VOICE.md)
* [`BROWSER_AND_APPS.md`](docs/BROWSER_AND_APPS.md)
* [`WEB_RESEARCH.md`](docs/WEB_RESEARCH.md)

---

## Development Principles

STONIC is built around several principles:

**Modularity**
Subsystems should remain independently replaceable.

**Controlled execution**
System actions should go through explicit tools and services.

**Testability**
Important functionality should be covered by automated verification.

**Windows-first design**
The primary target is a polished Windows desktop experience.

**Maintainability**
UI, backend, providers, tools, and platform-specific logic should remain separated.

---

## Roadmap

Future development may include:

* More natural computer interaction
* Better browser autonomy
* Improved multi-step task execution
* Stronger personal memory
* More reliable voice interaction
* Smarter daily briefings
* Deeper Windows integration
* Expanded automation skills
* Additional AI providers
* More human-like assistant workflows

The roadmap will evolve alongside the project.

---

## Project Status

**STONIC V2** is the current development/release codebase.

This repository contains the source of truth for:

* Backend
* Frontend
* Desktop application
* AI providers
* Tools
* Skills
* Voice subsystem
* Browser automation
* Tests
* Documentation

---

## Contributing

STONIC is currently maintained as a personal project.

When modifying the codebase:

1. Preserve the existing architecture.
2. Test the affected subsystem.
3. Run broader verification where appropriate.
4. Review the final diff before committing.

---

## License

This project is currently maintained as a personal project. Licensing and redistribution terms are determined by the repository owner.
