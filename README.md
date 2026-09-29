# S.T.O.N.I.C V2

> **A personal AI assistant for Windows — built to interact with your computer, understand your requests, and evolve toward a more capable digital assistant.**

**STONIC** is a Windows-focused personal AI assistant project designed around natural interaction, computer assistance, modular capabilities, and a cinematic desktop experience.

V2 represents the **first public foundation of STONIC** — establishing the core architecture, interface, AI interaction layer, task system, voice foundations, and extensibility required for future generations.

---

## Overview

STONIC V2 is more than a traditional chatbot.

The goal is to create an assistant that can sit on your desktop and become a practical interface between you and your computer.

Instead of switching between multiple applications, tools, and interfaces, STONIC aims to provide a single conversational layer through which you can interact with your system.

### The V2 vision

STONIC V2 focuses on:

- AI-powered conversation
- Desktop interaction
- Task execution
- Web-assisted intelligence
- Voice interaction foundations
- System awareness
- Modular providers
- Persistent project architecture
- A dedicated cinematic desktop interface

V2 is intentionally designed as a foundation for the future STONIC roadmap rather than the final form of the assistant.

---

# ✨ Features

## 🤖 AI Conversation

STONIC provides a conversational interface for interacting with an AI model.

The architecture is designed around provider-based AI integration, allowing the underlying model/provider to be changed without rebuilding the entire application.

Typical interactions include:

- General questions
- Explanations
- Coding assistance
- Brainstorming
- Reasoning
- Information requests
- Conversational assistance

---

## 🖥️ Windows Desktop Integration

STONIC is designed specifically around the Windows desktop environment.

The long-term objective is to allow the assistant to interact with the computer rather than simply returning text.

This foundation allows future versions to expand into:

- Application interaction
- File operations
- System actions
- Computer control
- Automated workflows
- System information
- Multi-step tasks

---

## ⚙️ Task System

STONIC includes a task-oriented architecture intended to move beyond simple question-and-answer interaction.

Instead of only responding with text, the assistant can be extended toward workflows where it:

1. Understands a request
2. Determines what needs to happen
3. Performs the required operation
4. Reports the result

The task architecture is one of the foundations for STONIC's future autonomous capabilities.

---

## 🌐 Web Search Architecture

STONIC includes a dedicated web-search provider layer.

The purpose of this architecture is to allow the assistant to obtain information from the web when its built-in knowledge is insufficient or when current information is required.

The web-search system is provider-based so that search infrastructure can be changed independently from the rest of the application.

> **Current status:** Web search is still under development and may not work reliably in every configuration.

---

## 🎙️ Voice Interaction

STONIC V2 contains the foundations for voice interaction.

The project includes voice-related components for future natural interaction, including:

- Voice input
- Voice output
- Voice-live experimentation
- Calibration utilities
- Voice diagnostics

The voice architecture is intended to evolve toward a more natural assistant experience in future versions.

---

## 🧠 Modular Architecture

STONIC is built with modularity in mind.

AI providers, search providers, voice components, tasks, and other capabilities can be developed independently.

This allows the project to evolve without requiring the entire system to be rewritten whenever a provider or capability changes.

---

## 🎨 STONIC Interface

The V2 interface follows a dark, cinematic desktop-assistant aesthetic.

The UI is designed around a central STONIC identity and dedicated interaction areas.

Major interface concepts include:

- STONIC Core
- Core Chat
- Visual Hub
- Task area
- Assistant state
- System interaction
- Start AI / Stop AI controls

The interface is intentionally designed to feel like a dedicated assistant rather than a conventional web chatbot.

---

# 🏗️ Architecture

At a high level, STONIC can be viewed as several layers:

```text
┌─────────────────────────────────────────────┐
│                 STONIC UI                   │
│                                             │
│   Chat • Core • Tasks • Voice • Status      │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│              Assistant Core                 │
│                                             │
│   Conversation • Routing • State • Tasks    │
└──────────────────────┬──────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
┌──────────────┐ ┌──────────────┐ ┌───────────┐
│ AI Providers │ │ Web Search   │ │   Voice   │
│              │ │ Providers    │ │  System   │
└──────────────┘ └──────────────┘ └───────────┘
          │            │            │
          └────────────┼────────────┘
                       ▼
┌─────────────────────────────────────────────┐
│             Windows Environment             │
│                                             │
│ Files • Apps • System • Desktop • Network   │
└─────────────────────────────────────────────┘
```

The objective is to keep these layers sufficiently independent that individual components can evolve without destabilizing the entire application.

---

# 📁 Project Structure

The exact structure may evolve during development, but the major components are organized around the following responsibilities:

```text
STONIC/
│
├── stonic/
│   ├── providers/
│   │   ├── websearch.py
│   │   └── ...
│   │
│   ├── voicelive/
│   │   └── ...
│   │
│   └── ...
│
├── scripts/
│   ├── websearch-check.py
│   ├── voicelive-check.py
│   └── voicelive-calibrate.py
│
├── release/
│   └── ...
│
├── models/
│   └── ...
│
├── frontend/
│   └── ...
│
├── package.json
├── requirements.txt
├── README.md
└── ...
```

> The structure shown above represents the major V2 architecture and may change as the project develops.

---

# 💻 Requirements

STONIC V2 is primarily developed and tested on Windows.

### Recommended environment

| Component | Version |
|---|---|
| Operating System | Windows 11 |
| Python | 3.12.x |
| Node.js | 22.x |
| npm | 10.x |
| Tesseract OCR | 5.5.x |
| RAM | 8 GB+ recommended |
| Storage | Depends on installed runtime/models |

The development environment used for V2 includes:

```text
Windows 11
Python 3.12.10
Node.js 22.23.2
npm 10.9.8
Tesseract 5.5.3
```

---

# 🚀 Getting Started

## 1. Clone the repository

```powershell
git clone https://github.com/alfaazkhanofficial/Stonic-AI.git
cd Stonic-AI
```

---

## 2. Create a Python environment

Using Python 3.12:

```powershell
py -3.12 -m venv .venv
```

Activate it:

```powershell
.venv\Scripts\activate
```

---

## 3. Install Python dependencies

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

If the project uses a package configuration instead of a requirements file in a particular checkout, follow the dependency instructions provided by that release.

---

## 4. Install frontend dependencies

```powershell
npm ci
```

For development environments where a clean lockfile installation is not required:

```powershell
npm install
```

---

## 5. Configure environment variables

STONIC may require API credentials depending on which providers are enabled.

Create a local environment configuration file where required:

```text
.env
```

Example:

```env
AI_API_KEY=your_api_key_here
WEB_SEARCH_API_KEY=your_api_key_here
```

**Never commit API keys, tokens, passwords, or other secrets to Git.**

Use environment variables or local configuration files instead.

---

# 🔑 AI Provider Configuration

STONIC uses a provider-oriented architecture.

This allows the AI backend to be changed without redesigning the entire application.

A provider configuration may contain:

```text
Provider
Endpoint
Model
API Key
Request Configuration
```

For example, a compatible OpenAI-style endpoint can be configured around:

```text
Base URL
Model
API Key
```

The exact provider configuration depends on the version and local setup.

---

# 🌐 Web Search Configuration

STONIC V2 contains a dedicated web-search provider.

The provider is intended to be independent from the main AI system.

Conceptually:

```text
User Request
     │
     ▼
STONIC
     │
     ▼
Does this require current information?
     │
     ▼
Web Search Provider
     │
     ▼
Search Results
     │
     ▼
AI Processing
     │
     ▼
Response
```

### Diagnostics

The repository includes:

```powershell
python scripts/websearch-check.py
```

This can be used to diagnose the web-search subsystem.

> Web search is currently one of the areas still undergoing development and stabilization.

---

# 🎙️ Voice System

Voice functionality is separated into its own components.

The repository contains voice-live related tooling and diagnostics.

### Voice diagnostics

```powershell
python scripts/voicelive-check.py
```

### Voice calibration

```powershell
python scripts/voicelive-calibrate.py
```

The exact voice provider and configuration depend on the current V2 build.

---

# 🧪 Testing

STONIC is intended to be tested at multiple levels.

Typical testing areas include:

- Core functionality
- AI provider connectivity
- Web search
- Voice systems
- UI functionality
- Task execution
- Windows integration
- Build/package validation

Run the project's available test suite using the configured Python environment:

```powershell
pytest
```

For targeted diagnostics, use the scripts provided under:

```text
scripts/
```

---

# 🛠️ Development

For active development, use the development environment rather than the packaged release.

A typical workflow is:

```powershell
cd Stonic

.venv\Scripts\activate

npm ci

pytest
```

Then start the appropriate development process defined by the project configuration.

The exact development command may vary depending on the current frontend/runtime configuration.

---

# 📦 Release Builds

STONIC V2 is packaged for Windows.

The V2 release executable is expected to be located within the packaged release directory:

```text
release\
└── Stonic-V2-0.2.0-win-x64\
    └── Stonic.exe
```

Package version:

```text
stonic-v2==0.2.0
```

The release build is intended to provide a self-contained Windows application environment.

---

# 🪟 Windows Installer

The Windows release can be distributed using an installer generated with Inno Setup.

The installer is intended to install STONIC under the Windows Program Files directory.

A typical installed layout may resemble:

```text
C:\Program Files\
└── STONIC\
    ├── Stonic.exe
    ├── resources\
    ├── runtime\
    └── ...
```

The exact installer structure can change between releases.

---

# 🔒 Security

STONIC can interact with external services and potentially with the local computer.

Users should therefore treat configuration files and API credentials as sensitive.

### Never commit:

```text
.env
API keys
Access tokens
Passwords
Private credentials
Personal secrets
```

Before publishing a release:

- Check for exposed API keys
- Review environment files
- Review build artifacts
- Review logs
- Review generated configuration files

GitHub recommends enabling security features such as secret scanning and push protection for repositories where appropriate.

---

# ⚠️ Current Status

## STONIC V2

**Status: Public development/release build**

V2 establishes the first major public foundation of the STONIC project.

The core conversational experience is functional, while several advanced subsystems continue to receive testing, debugging, stabilization, and refinement.

### Current areas

| Area | Status |
|---|---|
| Core UI | 🟢 Active |
| Text Chat | 🟢 Working |
| AI Provider System | 🟢 Active |
| Task System | 🟡 Developing |
| Web Search | 🟡 Developing |
| Voice | 🟡 Developing |
| Windows Integration | 🟡 Developing |
| Packaging | 🟢 Active |
| Installer | 🟢 Active |

Status can change as development continues.

---

# 🐛 Known Limitations

STONIC V2 is not intended to represent the final STONIC architecture.

Known areas that may require additional work include:

### Web Search

Web-search functionality may fail depending on provider availability, configuration, or connectivity.

### Task Execution

Some tasks may not execute reliably in every situation.

### Workspace Initialization

Certain builds may experience workspace initialization delays or startup failures.

### Voice

Voice functionality is still being refined toward the more natural interaction model planned for later versions.

### System Integration

Not every Windows operation is currently exposed through STONIC.

These limitations are part of the V2 development stage and are expected to be addressed through future releases.

---

# 🗺️ STONIC Evolution

STONIC is being developed as a multi-generation project.

| Version | Direction |
|---|---|
| **V2** | Foundation + first public release |
| **V3** | 🔥 Wild-fire leap — major capability jump |
| **V4** | 🧠 Deeper intelligence + context |
| **V5** | 🤖 More autonomous task execution |
| **V6** | 🗣️ Next-level voice + natural interaction |
| **V7** | 🖥️ Advanced computer control |
| **V8** | 🌐 Connected ecosystem + powerful tools |
| **V9** | 🧩 Modular and extensible |
| **V10** | 🚀 Mature V-series |
| **Gen 1** | 🧬 Fundamentally new architecture |

The versions are intended to represent stages in STONIC's evolution rather than simple feature updates.

---

# 🧭 Philosophy

STONIC is built around a simple idea:

> **The computer should adapt to the user — not the other way around.**

Traditional software requires users to learn where features are located, which buttons to press, and which application they need.

STONIC explores another approach:

```text
User
 │
 │ Natural request
 ▼
STONIC
 │
 ├── Understand
 ├── Reason
 ├── Search
 ├── Plan
 ├── Execute
 └── Respond
 │
 ▼
User
```

The ultimate goal is to make interaction with a computer feel more direct and natural.

---

# 🧩 Why V2 Matters

V2 is not simply another release.

It establishes the architecture from which later STONIC generations can evolve.

The project introduces the foundations for:

- AI provider abstraction
- Web intelligence
- Voice interaction
- Task execution
- Desktop integration
- Modular capabilities
- Dedicated assistant UI
- Windows packaging
- Future agentic workflows

Future versions can build upon these concepts while replacing or redesigning individual subsystems where necessary.

---

# 📸 Screenshots & Demo

Screenshots and demonstration videos should be added here as the project evolves.

Recommended structure:

```text
docs/
└── media/
    ├── stonic-v2-ui.png
    ├── stonic-v2-chat.png
    └── stonic-v2-demo.gif
```

Example:

```markdown
![STONIC V2 Interface](docs/media/stonic-v2-ui.png)
```

---

# 🎥 STONIC V2 Demo

A complete setup and demonstration video can be linked here once published.

```text
YouTube:
https://youtube.com/
```

Replace the placeholder with the official STONIC V2 video when available.

---

# 📚 Documentation

As the project grows, detailed documentation should be separated into dedicated files rather than turning the README into an enormous technical manual.

Recommended documentation structure:

```text
docs/
├── architecture.md
├── installation.md
├── configuration.md
├── providers.md
├── voice.md
├── web-search.md
├── tasks.md
├── troubleshooting.md
└── development.md
```

The README remains the entry point, while detailed documentation can live separately.

GitHub itself recommends keeping a README focused on helping users understand and get started, with longer documentation placed elsewhere.

---

# ❓ Troubleshooting

## STONIC does not start

Check:

```text
Python version
Node.js version
Dependencies
Environment variables
Provider configuration
Windows permissions
```

Then run the project from a terminal so startup errors are visible.

---

## AI provider is not responding

Check:

1. API key configuration
2. Endpoint URL
3. Model name
4. Internet connectivity
5. Provider availability
6. Request limits

---

## Web search is not working

Run:

```powershell
python scripts/websearch-check.py
```

Verify the configured search provider and credentials.

---

## Voice is not working

Run:

```powershell
python scripts/voicelive-check.py
```

Then use:

```powershell
python scripts/voicelive-calibrate.py
```

if calibration is required.

---

# 🤝 Contributing

STONIC is an evolving project.

Contributions, bug reports, ideas, and technical improvements can help improve the project.

Before contributing:

1. Read the repository documentation.
2. Create a development environment.
3. Test your changes locally.
4. Keep changes focused.
5. Avoid committing secrets.
6. Document significant architectural changes.

For larger changes, open an issue first so the direction can be discussed before implementation.

---

# 🐞 Reporting Issues

If you discover a bug, include as much useful information as possible:

```text
Operating System:
STONIC Version:
Python Version:
Node Version:
What happened:
What was expected:
Steps to reproduce:
Relevant logs:
```

Avoid including API keys, passwords, tokens, or other private information in issue reports.

---

# 📜 License

Add the project's actual license here.

For example:

```text
This project is licensed under the MIT License.
See LICENSE for details.
```

**Important:** Replace this section with the actual license used by the repository. Do not claim a license that has not been added to the project.

---

# 🙏 Acknowledgements

STONIC is built using and inspired by the work of the wider open-source and AI developer community.

The project relies on a variety of technologies and libraries across:

- Python
- JavaScript / TypeScript
- Electron
- Vite
- FastAPI
- Uvicorn
- Pillow
- psutil
- pytest
- Tesseract OCR
- AI model providers
- Web technologies

Each dependency remains subject to its respective license.

---

# 👤 Maintainer

**Alfaaz Khan**

Creator and developer of STONIC.

GitHub:

```text
https://github.com/alfaazkhanofficial
```

Project:

```text
https://github.com/alfaazkhanofficial/Stonic-AI
```

---

# 🚀 Final Note

STONIC V2 is the beginning of the public STONIC journey.

It is not designed to be the endpoint.

It is the foundation.

The architecture, interface, provider system, task layer, voice experiments, and Windows integration created in V2 establish the groundwork for increasingly capable versions of STONIC.

```text
V2
Foundation
   ↓
V3
Capability Leap
   ↓
V4+
Intelligence
   ↓
Future
A truly adaptive personal computer assistant
```

**Built with curiosity.  
Designed for interaction.  
Engineered to evolve.**

---

## STONIC

**S.T.O.N.I.C — Personal AI Assistant for Windows**
