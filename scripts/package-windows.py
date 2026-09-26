"""
Assemble an unsigned, portable, offline-capable Windows folder
from verified local assets.

Security / release guarantees:
- Explicit source allowlist only.
- User records, credentials, databases, browser profiles and caches
  are never copied.
- Python runtime and locked site-packages are bundled.
- Node runtime is bundled.
- Playwright + local Chromium browser runtime are bundled.
- Tesseract is bundled when installed locally.
- Packaged runtime is configured to use the bundled Playwright browser.
- Obvious secrets are scanned before finalization.
- Bundled Python imports are verified.
- Stonic.exe is launched as a smoke test.
- Final package receives a SHA-256 file manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import struct
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]

PACKAGE_JSON = ROOT / "package.json"
VERSION = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))["version"]

RELEASE_ROOT = ROOT / "release"
DEST = RELEASE_ROOT / f"Stonic-V2-{VERSION}-win-x64"
STAGING = RELEASE_ROOT / f"{DEST.name}.staging"

MIN_FREE_BYTES = 5_000_000_000
SMOKE_TEST_SECONDS = 8

# STONIC currently uses Chromium-based browser automation.
PLAYWRIGHT_BROWSER = os.environ.get(
    "STONIC_PLAYWRIGHT_BROWSER",
    "chromium",
).lower()

# Optional:
#   $env:STONIC_SMOKE_HEALTH_URL = "http://127.0.0.1:8000/health"
#
# When supplied, the package smoke test will also poll this endpoint.
SMOKE_HEALTH_URL = os.environ.get("STONIC_SMOKE_HEALTH_URL", "").strip()


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------

def copy_tree(
    source: Path,
    destination: Path,
    ignore=None,
) -> None:
    """
    Copy a directory while excluding transient/development artifacts.
    """
    shutil.copytree(
        source,
        destination,
        dirs_exist_ok=True,
        ignore=(
            ignore
            or shutil.ignore_patterns(
                "__pycache__",
                "*.pyc",
                ".git",
                "*.log",
            )
        ),
    )


def copy_file(
    source: Path,
    destination: Path,
) -> None:
    """
    Copy one file and create the destination parent directory.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def run_checked(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 60,
    description: str,
) -> subprocess.CompletedProcess[str]:
    """
    Run a command and raise a clear packaging error when it fails.
    """
    result = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )

    if result.returncode != 0:
        output = "\n".join(
            part.strip()
            for part in (result.stdout, result.stderr)
            if part and part.strip()
        )

        raise SystemExit(
            f"{description} failed with exit code "
            f"{result.returncode}.\n\n{output[-8000:]}"
        )

    return result


def ensure_file(
    path: Path,
    description: str,
) -> None:
    if not path.is_file():
        raise SystemExit(
            f"{description} is missing:\n{path}"
        )


def ensure_directory(
    path: Path,
    description: str,
) -> None:
    if not path.is_dir():
        raise SystemExit(
            f"{description} is missing:\n{path}"
        )


# ---------------------------------------------------------------------------
# Source validation
# ---------------------------------------------------------------------------

def validate_build_environment() -> None:
    if os.name != "nt":
        raise SystemExit(
            "This packaging script must run on Windows."
        )

    if sys.version_info[:2] != (3, 12):
        raise SystemExit(
            "Package with the project's Python 3.12 environment.\n"
            f"Current Python: {sys.version.split()[0]}"
        )

    machine = platform.machine().lower()
    pointer_bits = struct.calcsize("P") * 8

    if machine not in {
        "amd64",
        "x86_64",
        "amd64t",
    } or pointer_bits != 64:
        raise SystemExit(
            "Expected a 64-bit Windows Python build.\n"
            f"Detected: {platform.machine()} / {pointer_bits}-bit"
        )

    if shutil.disk_usage(ROOT).free < MIN_FREE_BYTES:
        raise SystemExit(
            "At least 5 GB of free disk space is required "
            "to assemble the portable folder."
        )

    ensure_file(
        PACKAGE_JSON,
        "package.json",
    )

    ensure_file(
        ROOT / "dist" / "index.html",
        "Frontend production build",
    )


def validate_required_source_tree() -> None:
    required_directories = [
        "desktop",
        "dist",
        "stonic",
        "docs",
    ]

    for name in required_directories:
        ensure_directory(
            ROOT / name,
            f"Required project directory '{name}'",
        )

    required_files = [
        "package.json",
        "pyproject.toml",
        "uv.lock",
        "package-lock.json",
        "README.md",
    ]

    for name in required_files:
        ensure_file(
            ROOT / name,
            f"Required project file '{name}'",
        )


# ---------------------------------------------------------------------------
# Electron packaging
# ---------------------------------------------------------------------------

def copy_electron_runtime(
    dest: Path,
) -> None:
    print(
        "Copying Electron desktop runtime...",
        flush=True,
    )

    electron_dist = ROOT / "node_modules" / "electron" / "dist"

    ensure_directory(
        electron_dist,
        "Electron runtime",
    )

    copy_tree(
        electron_dist,
        dest,
    )

    electron_exe = dest / "electron.exe"

    ensure_file(
        electron_exe,
        "Electron executable",
    )

    target = dest / "Stonic.exe"

    if target.exists():
        target.unlink()

    electron_exe.rename(target)

    ensure_file(
        target,
        "STONIC executable",
    )


# ---------------------------------------------------------------------------
# Application allowlist
# ---------------------------------------------------------------------------

def copy_application_allowlist(
    app: Path,
) -> None:
    print(
        "Copying application allowlist...",
        flush=True,
    )

    for name in [
        "desktop",
        "dist",
        "stonic",
        "docs",
    ]:
        source = ROOT / name
        destination = app / name

        copy_tree(
            source,
            destination,
        )

    # Runtime helper scripts.
    runtime_scripts = [
        "runtime.cjs",
        "browser-worker.mjs",
    ]

    for name in runtime_scripts:
        source = ROOT / "scripts" / name

        ensure_file(
            source,
            f"Runtime script '{name}'",
        )

        copy_file(
            source,
            app / "scripts" / name,
        )

    # Project metadata required at runtime / for diagnostics.
    metadata_files = [
        "package.json",
        "pyproject.toml",
        "uv.lock",
        "package-lock.json",
        "README.md",
    ]

    for name in metadata_files:
        source = ROOT / name

        ensure_file(
            source,
            f"Project metadata '{name}'",
        )

        copy_file(
            source,
            app / name,
        )


# ---------------------------------------------------------------------------
# Python runtime
# ---------------------------------------------------------------------------

def copy_python_runtime(
    app: Path,
) -> Path:
    print(
        "Copying bundled Python runtime and locked packages...",
        flush=True,
    )

    base = Path(sys.base_prefix)

    ensure_directory(
        base,
        "Python base runtime",
    )

    python = app / "runtime" / "python"

    # Standard library + DLLs.
    for name in [
        "Lib",
        "DLLs",
    ]:
        source = base / name

        ensure_directory(
            source,
            f"Python directory '{name}'",
        )

        copy_tree(
            source,
            python / name,
            shutil.ignore_patterns(
                "site-packages",
                "__pycache__",
                "*.pyc",
                "test",
                "tests",
                "idlelib",
                "tkinter",
                "turtledemo",
            ),
        )

    # Python executables / root DLLs / license.
    for file in base.iterdir():
        if not file.is_file():
            continue

        if (
            file.suffix.lower() in {
                ".exe",
                ".dll",
            }
            or file.name.lower() == "license.txt"
        ):
            copy_file(
                file,
                python / file.name,
            )

    site_packages = (
        ROOT
        / ".venv"
        / "Lib"
        / "site-packages"
    )

    ensure_directory(
        site_packages,
        "Virtualenv site-packages",
    )

    copy_tree(
        site_packages,
        python / "Lib" / "site-packages",
        shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            "*.pth",
            "_virtualenv.py",
            "*.egg-link",
        ),
    )

    # Bundled Python isolation.
    python_pth = python / "python312._pth"

    python_pth.write_text(
        ".\n"
        "DLLs\n"
        "Lib\n"
        "Lib/site-packages\n"
        "import site\n",
        encoding="utf-8",
    )

    # Make the real application root importable:
    #
    # resources/app/runtime/python/Lib/site-packages
    #   -> ../../../../
    #   -> resources/app
    #
    # This keeps:
    #   resources/app/stonic
    #
    # as the canonical application package.
    app_root_pth = (
        python
        / "Lib"
        / "site-packages"
        / "stonic-app-root.pth"
    )

    app_root_pth.write_text(
        "../../../../\n",
        encoding="ascii",
    )

    # Prevent host paths from being accidentally imported.
    sitecustomize = (
        python
        / "Lib"
        / "site-packages"
        / "sitecustomize.py"
    )

    sitecustomize.write_text(
        "# STONIC portable runtime isolation.\n"
        "import os\n"
        "os.environ.pop('PYTHONPATH', None)\n"
        "os.environ.pop('PYTHONHOME', None)\n",
        encoding="utf-8",
    )

    bundled_python = python / "python.exe"

    ensure_file(
        bundled_python,
        "Bundled Python executable",
    )

    return python


# ---------------------------------------------------------------------------
# Node runtime
# ---------------------------------------------------------------------------

def locate_node() -> Path:
    node_path = shutil.which("node")

    if not node_path:
        raise SystemExit(
            "Node.js is missing from PATH."
        )

    node = Path(node_path)

    ensure_file(
        node,
        "Node.js executable",
    )

    return node


def copy_node_runtime(
    app: Path,
) -> Path:
    print(
        "Copying bundled Node runtime...",
        flush=True,
    )

    node = locate_node()

    bundled_node = (
        app
        / "runtime"
        / "node"
    )

    copy_file(
        node,
        bundled_node / "node.exe",
    )

    # Keep useful npm/npx runtime files.
    for file in node.parent.iterdir():
        if not file.is_file():
            continue

        lower_name = file.name.lower()

        if lower_name.startswith(
            (
                "license",
                "npm",
                "npx",
            )
        ):
            copy_file(
                file,
                bundled_node / file.name,
            )

    npm_source = (
        node.parent
        / "node_modules"
        / "npm"
    )

    ensure_directory(
        npm_source,
        "Bundled npm runtime",
    )

    copy_tree(
        npm_source,
        bundled_node
        / "node_modules"
        / "npm",
    )

    return node


# ---------------------------------------------------------------------------
# Playwright browser runtime
# ---------------------------------------------------------------------------

def probe_playwright_browser(
    node: Path,
) -> Path:
    """
    Ask the locally installed Playwright package for its browser executable.

    We intentionally do not download browsers here.
    Packaging uses only an already-installed local browser asset.
    """

    if PLAYWRIGHT_BROWSER not in {
        "chromium",
        "firefox",
        "webkit",
    }:
        raise SystemExit(
            "Unsupported STONIC_PLAYWRIGHT_BROWSER value: "
            f"{PLAYWRIGHT_BROWSER}"
        )

    probe = f"""
const pw = require("playwright");
const browser = pw.{PLAYWRIGHT_BROWSER};

if (!browser || typeof browser.executablePath !== "function") {{
    process.stderr.write(
        "Playwright browser API is unavailable.\\n"
    );
    process.exit(2);
}}

process.stdout.write(
    browser.executablePath()
);
"""

    result = subprocess.run(
        [
            str(node),
            "-e",
            probe,
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )

    if result.returncode != 0:
        output = "\n".join(
            part.strip()
            for part in (
                result.stdout,
                result.stderr,
            )
            if part and part.strip()
        )

        raise SystemExit(
            "Could not determine the installed Playwright "
            f"{PLAYWRIGHT_BROWSER} executable.\n\n"
            f"{output}"
        )

    executable = Path(
        result.stdout.strip()
    )

    ensure_file(
        executable,
        (
            f"Installed Playwright {PLAYWRIGHT_BROWSER} "
            "browser executable"
        ),
    )

    return executable


def copy_playwright_runtime(
    app: Path,
    node: Path,
) -> None:
    print(
        f"Copying Playwright {PLAYWRIGHT_BROWSER} runtime...",
        flush=True,
    )

    for package in [
        "playwright",
        "playwright-core",
    ]:
        source = (
            ROOT
            / "node_modules"
            / package
        )

        ensure_directory(
            source,
            f"Node package '{package}'",
        )

        copy_tree(
            source,
            app / "node_modules" / package,
        )

    browser_executable = probe_playwright_browser(node)

    # Example:
    #
    #   ...\ms-playwright\
    #       chromium-XXXX\
    #           chrome-win\
    #               chrome.exe
    #
    # or:
    #
    #   ...\playwright-core\
    #       .local-browsers\
    #           chromium-XXXX\
    #
    # The parent of chrome-win is the browser revision directory.
    browser_revision_root = (
        browser_executable
        .parent
        .parent
    )

    ensure_directory(
        browser_revision_root,
        "Playwright browser revision directory",
    )

    packaged_browser_root = (
        app
        / "node_modules"
        / "playwright-core"
        / ".local-browsers"
    )

    packaged_browser_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = (
        packaged_browser_root
        / browser_revision_root.name
    )

    if destination.exists():
        shutil.rmtree(destination)

    copy_tree(
        browser_revision_root,
        destination,
    )

    packaged_executable = (
        destination
        / browser_executable.parent.name
        / browser_executable.name
    )

    ensure_file(
        packaged_executable,
        "Packaged Playwright browser executable",
    )

    # Some environments install additional Playwright runtime components
    # beside Chromium. Copy ffmpeg if it is locally available.
    source_browser_parent = browser_revision_root.parent

    for candidate in sorted(
        source_browser_parent.glob("ffmpeg-*")
    ):
        if candidate.is_dir():
            ffmpeg_dest = (
                packaged_browser_root
                / candidate.name
            )

            if not ffmpeg_dest.exists():
                copy_tree(
                    candidate,
                    ffmpeg_dest,
                )

    print(
        f"Bundled browser: {packaged_executable}",
        flush=True,
    )


# ---------------------------------------------------------------------------
# Portable Playwright configuration
# ---------------------------------------------------------------------------

PORTABLE_PLAYWRIGHT_MARKER = (
    "__STONIC_PORTABLE_PLAYWRIGHT__"
)


def patch_node_runtime_for_portability(
    path: Path,
) -> None:
    """
    Make packaged Node entrypoints force Playwright to use:

      node_modules/playwright-core/.local-browsers

    rather than a developer's %LOCALAPPDATA%\\ms-playwright directory.
    """

    ensure_file(
        path,
        f"Packaged Node entrypoint '{path.name}'",
    )

    original = path.read_text(
        encoding="utf-8"
    )

    if PORTABLE_PLAYWRIGHT_MARKER in original:
        return

    bootstrap = (
        f"/* {PORTABLE_PLAYWRIGHT_MARKER} */\n"
        "process.env.PLAYWRIGHT_BROWSERS_PATH = \"0\";\n"
        "process.env.PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD = \"1\";\n"
    )

    lines = original.splitlines(
        keepends=True
    )

    if lines and lines[0].startswith("#!"):
        updated = (
            lines[0]
            + bootstrap
            + "".join(lines[1:])
        )
    else:
        updated = (
            bootstrap
            + original
        )

    path.write_text(
        updated,
        encoding="utf-8",
        newline="",
    )


def configure_portable_node_entrypoints(
    app: Path,
) -> None:
    print(
        "Configuring packaged Node entrypoints for "
        "portable Playwright...",
        flush=True,
    )

    patch_targets = [
        app / "scripts" / "runtime.cjs",
        app / "desktop" / "main.cjs",
    ]

    for path in patch_targets:
        if path.is_file():
            patch_node_runtime_for_portability(
                path
            )


# ---------------------------------------------------------------------------
# Optional integrations
# ---------------------------------------------------------------------------

def copy_optional_integrations(
    app: Path,
) -> None:
    # PresentMon.
    presentmon = (
        ROOT
        / "integrations"
        / "presentmon"
    )

    if presentmon.is_dir():
        print(
            "Copying local PresentMon integration...",
            flush=True,
        )

        copy_tree(
            presentmon,
            app / "integrations" / "presentmon",
        )

    # Tesseract.
    tesseract_command = shutil.which(
        "tesseract"
    )

    if tesseract_command:
        tesseract_dir = Path(
            tesseract_command
        ).parent
    else:
        tesseract_dir = Path(
            r"C:\Program Files\Tesseract-OCR"
        )

    tesseract_exe = (
        tesseract_dir
        / "tesseract.exe"
    )

    if tesseract_exe.is_file():
        print(
            "Copying local OCR runtime...",
            flush=True,
        )

        copy_tree(
            tesseract_dir,
            app
            / "integrations"
            / "tesseract",
            shutil.ignore_patterns(
                "unins*",
                "Uninstall*",
                "*.log",
            ),
        )


# ---------------------------------------------------------------------------
# Secret / private-data verification
# ---------------------------------------------------------------------------

SECRET_PATTERNS = [
    re.compile(
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
    ),
    re.compile(
        rb"\bAKIA[0-9A-Z]{16}\b"
    ),
    re.compile(
        rb"\b(?:sk|rk)-[A-Za-z0-9_-]{20,}\b"
    ),
    re.compile(
        rb"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{24,}\b"
    ),
    re.compile(
        rb"(?i)(?:api[_-]?key|access[_-]?token|secret[_-]?key)"
        rb"\s*[:=]\s*['\"][A-Za-z0-9._~+/=-]{20,}['\"]"
    ),
]

BLOCKED_FILE_SUFFIXES = {
    ".db",
    ".sqlite",
    ".sqlite3",
    ".dpapi",
    ".p12",
    ".pfx",
    ".key",
}

BLOCKED_EXACT_NAMES = {
    ".env",
    "credentials.dpapi",
}

TEXT_SCAN_EXTENSIONS = {
    ".c",
    ".cc",
    ".cpp",
    ".cjs",
    ".css",
    ".h",
    ".html",
    ".js",
    ".json",
    ".mjs",
    ".md",
    ".py",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".yaml",
    ".yml",
}


def verify_no_private_files(
    dest: Path,
) -> None:
    print(
        "Checking packaged files for private/local data...",
        flush=True,
    )

    violations: list[str] = []

    for path in dest.rglob("*"):
        if not path.is_file():
            continue

        name = path.name.lower()

        if name in BLOCKED_EXACT_NAMES:
            violations.append(
                f"blocked private file: "
                f"{path.relative_to(dest)}"
            )
            continue

        if path.suffix.lower() in BLOCKED_FILE_SUFFIXES:
            violations.append(
                f"blocked private/database file: "
                f"{path.relative_to(dest)}"
            )

    if violations:
        raise SystemExit(
            "Private/local files were detected in the package:\n"
            + "\n".join(
                f"- {item}"
                for item in violations
            )
        )


def verify_no_embedded_secrets(
    dest: Path,
) -> None:
    print(
        "Scanning STONIC-owned source/assets for obvious embedded secrets...",
        flush=True,
    )

    app = dest / "resources" / "app"

    # Scan only files owned by STONIC.
    #
    # Do NOT scan:
    #   - resources/app/node_modules
    #   - resources/app/runtime/python/Lib/site-packages
    #   - resources/app/runtime/node/node_modules
    #
    # These directories contain third-party libraries, documentation,
    # tests, examples, and security-related source code that can produce
    # false positives for generic secret/token/key patterns.

    scan_roots = [
        app / "desktop",
        app / "dist",
        app / "stonic",
        app / "docs",
        app / "scripts",
        app / "package.json",
        app / "pyproject.toml",
    ]

    violations: list[str] = []

    for root in scan_roots:
        if root.is_file():
            candidates = [root]
        elif root.is_dir():
            candidates = root.rglob("*")
        else:
            continue

        for path in candidates:
            if not path.is_file():
                continue

            if path.suffix.lower() not in TEXT_SCAN_EXTENSIONS:
                continue

            try:
                data = path.read_bytes()
            except OSError:
                continue

            for pattern in SECRET_PATTERNS:
                if pattern.search(data):
                    violations.append(
                        str(path.relative_to(dest))
                    )
                    break

    # Remove duplicates while preserving order.
    violations = list(dict.fromkeys(violations))

    if violations:
        raise SystemExit(
            "Potential embedded credentials were detected in "
            "STONIC-owned files:\n"
            + "\n".join(
                f"- {item}"
                for item in violations
            )
            + "\n\n"
            "Remove the credential before packaging."
        )

    print(
        "No obvious embedded credentials detected.",
        flush=True,
    )


# ---------------------------------------------------------------------------
# Bundled Python verification
# ---------------------------------------------------------------------------

def create_clean_runtime_environment() -> dict[str, str]:
    blocked_fragments = (
        "PYTHONPATH",
        "PYTHONHOME",
        "STONIC",
        "XKIRO",
        "API_KEY",
        "TOKEN",
        "SECRET",
        "PASSWORD",
        "CREDENTIAL",
    )

    env = {
        key: value
        for key, value in os.environ.items()
        if not any(
            fragment in key.upper()
            for fragment in blocked_fragments
        )
    }

    return env


def verify_bundled_python(
    dest: Path,
) -> None:
    print(
        "Checking imports using only the bundled Python...",
        flush=True,
    )

    bundled_python = (
        dest
        / "resources"
        / "app"
        / "runtime"
        / "python"
        / "python.exe"
    )

    ensure_file(
        bundled_python,
        "Bundled Python executable",
    )

    env = create_clean_runtime_environment()

    result = subprocess.run(
        [
            str(bundled_python),
            "-I",
            "-c",
            (
                "import sys; "
                "import fastapi, uvicorn, httpx, psutil, "
                "pydantic, PIL; "
                "import stonic; "
                "import stonic.app.api; "
                "print('Bundled Python:', sys.executable); "
                "print('STONIC package:', stonic.__file__); "
                "print('Portable imports passed')"
            ),
        ],
        cwd=dest,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        output = "\n".join(
            part
            for part in (
                result.stdout,
                result.stderr,
            )
            if part
        )

        raise SystemExit(
            "Portable Python import verification failed:\n"
            + output[-8000:]
        )

    print(
        result.stdout.strip(),
        flush=True,
    )


# ---------------------------------------------------------------------------
# Packaged Playwright verification
# ---------------------------------------------------------------------------

def verify_packaged_playwright(
    dest: Path,
) -> None:
    print(
        "Verifying packaged Playwright browser...",
        flush=True,
    )

    node = (
        dest
        / "resources"
        / "app"
        / "runtime"
        / "node"
        / "node.exe"
    )

    playwright_core = (
        dest
        / "resources"
        / "app"
        / "node_modules"
        / "playwright-core"
    )

    browser_root = (
        playwright_core
        / ".local-browsers"
    )

    ensure_file(
        node,
        "Bundled Node executable",
    )

    ensure_directory(
        playwright_core,
        "Packaged playwright-core",
    )

    ensure_directory(
        browser_root,
        "Packaged Playwright browser directory",
    )

    env = create_clean_runtime_environment()

    env["PLAYWRIGHT_BROWSERS_PATH"] = "0"
    env["PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"] = "1"

    probe = f"""
const pw = require("./node_modules/playwright");
const browser = pw.{PLAYWRIGHT_BROWSER};

if (!browser) process.exit(2);

const executable = browser.executablePath();
console.log("Packaged executable:", executable);
"""

    result = subprocess.run(
        [
            str(node),
            "-e",
            probe,
        ],
        cwd=(
            dest
            / "resources"
            / "app"
        ),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode != 0:
        output = "\n".join(
            part
            for part in (
                result.stdout,
                result.stderr,
            )
            if part
        )

        raise SystemExit(
            "Packaged Playwright verification failed:\n"
            + output[-8000:]
        )

    output = result.stdout.strip()

    if not output:
        raise SystemExit(
            "Packaged Playwright verification produced no output."
        )

    print(
        output,
        flush=True,
    )


# ---------------------------------------------------------------------------
# Application smoke test
# ---------------------------------------------------------------------------

def poll_health_endpoint(
    url: str,
    timeout_seconds: float,
) -> bool:
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": "STONIC-Portable-Smoke-Test"
                },
            )

            with urlopen(
                request,
                timeout=2,
            ) as response:
                if 200 <= response.status < 500:
                    return True

        except (
            OSError,
            URLError,
            TimeoutError,
        ):
            time.sleep(0.25)

    return False


def terminate_process_tree(
    pid: int,
) -> None:
    if os.name != "nt":
        return

    subprocess.run(
        [
            "taskkill",
            "/PID",
            str(pid),
            "/T",
            "/F",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )


def smoke_test_portable_app(
    dest: Path,
) -> None:
    print(
        "Launching Stonic.exe for portable smoke test...",
        flush=True,
    )

    executable = dest / "Stonic.exe"

    ensure_file(
        executable,
        "Packaged Stonic.exe",
    )

    env = create_clean_runtime_environment()

    app_root = (
        dest
        / "resources"
        / "app"
    )

    # Force Playwright to the packaged local browser.
    env["PLAYWRIGHT_BROWSERS_PATH"] = "0"
    env["PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"] = "1"

    process = subprocess.Popen(
        [str(executable)],
        cwd=dest,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )

    try:
        deadline = (
            time.monotonic()
            + SMOKE_TEST_SECONDS
        )

        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise SystemExit(
                    "Stonic.exe exited during the portable "
                    "smoke test.\n"
                    f"Exit code: {process.returncode}"
                )

            time.sleep(0.25)

        if process.poll() is not None:
            raise SystemExit(
                "Stonic.exe exited unexpectedly during "
                "the smoke test."
            )

        print(
            "Stonic.exe remained running successfully.",
            flush=True,
        )

        if SMOKE_HEALTH_URL:
            print(
                f"Checking health endpoint: {SMOKE_HEALTH_URL}",
                flush=True,
            )

            if not poll_health_endpoint(
                SMOKE_HEALTH_URL,
                timeout_seconds=10,
            ):
                raise SystemExit(
                    "Portable health endpoint did not become ready:\n"
                    f"{SMOKE_HEALTH_URL}"
                )

            print(
                "Portable health endpoint passed.",
                flush=True,
            )

    finally:
        if process.poll() is None:
            print(
                "Stopping smoke-test STONIC process...",
                flush=True,
            )
            terminate_process_tree(
                process.pid
            )


# ---------------------------------------------------------------------------
# Package metadata
# ---------------------------------------------------------------------------

def write_readme_first(
    dest: Path,
) -> None:
    text = (
        f"STONIC V2 {VERSION} - Windows portable build\n"
        "\n"
        "Open Stonic.exe from this extracted folder.\n"
        "Keep the bundled folders together.\n"
        "\n"
        "Bundled:\n"
        "- Python runtime\n"
        "- Python dependencies\n"
        "- Node runtime\n"
        "- Playwright runtime\n"
        f"- Playwright {PLAYWRIGHT_BROWSER} browser runtime\n"
        "- Local OCR runtime when available\n"
        "\n"
        "Network requirements:\n"
        "- Local application features can run without Internet access.\n"
        "- Cloud AI providers and web-research features require Internet access.\n"
        "- xKiro requires your own API key and Internet access.\n"
        "\n"
        "User data:\n"
        "- No saved API key is included.\n"
        "- No user records are included.\n"
        "- No browser profile is included.\n"
        "- No local application database is included.\n"
        "\n"
        "Release status:\n"
        "- Unsigned Windows build.\n"
        "- Package contents were assembled from an explicit allowlist.\n"
        "- Bundled Python import verification passed.\n"
        "- Bundled Playwright verification passed.\n"
        "- Stonic.exe portable smoke test passed.\n"
    )

    (dest / "READ-ME-FIRST.txt").write_text(
        text,
        encoding="utf-8",
    )


def build_inventory(
    dest: Path,
) -> list[dict]:
    files: list[dict] = []

    print(
        "Recording package file inventory and SHA-256 checksums...",
        flush=True,
    )

    for path in sorted(
        dest.rglob("*")
    ):
        if not path.is_file():
            continue

        with path.open("rb") as source:
            digest = hashlib.file_digest(
                source,
                "sha256",
            ).hexdigest()

        files.append(
            {
                "path": path.relative_to(
                    dest
                ).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": digest,
            }
        )

    return files


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def build() -> None:
    validate_build_environment()
    validate_required_source_tree()

    if DEST.exists():
        raise SystemExit(
            f"Output already exists:\n{DEST}\n\n"
            "Preserve it or remove/rename it before rebuilding."
        )

    if STAGING.exists():
        shutil.rmtree(STAGING)

    RELEASE_ROOT.mkdir(
        parents=True,
        exist_ok=True,
    )

    dest = STAGING
    app = dest / "resources" / "app"

    try:
        # ---------------------------------------------------------------
        # Electron
        # ---------------------------------------------------------------
        copy_electron_runtime(dest)

        # ---------------------------------------------------------------
        # App source
        # ---------------------------------------------------------------
        copy_application_allowlist(app)

        # ---------------------------------------------------------------
        # Python
        # ---------------------------------------------------------------
        copy_python_runtime(app)

        # ---------------------------------------------------------------
        # Node
        # ---------------------------------------------------------------
        node = copy_node_runtime(app)

        # ---------------------------------------------------------------
        # Playwright + local browser
        # ---------------------------------------------------------------
        copy_playwright_runtime(
            app,
            node,
        )

        # ---------------------------------------------------------------
        # Portable runtime configuration
        # ---------------------------------------------------------------
        configure_portable_node_entrypoints(app)

        # ---------------------------------------------------------------
        # Optional local integrations
        # ---------------------------------------------------------------
        copy_optional_integrations(app)

        # ---------------------------------------------------------------
        # Package notice
        # ---------------------------------------------------------------
        write_readme_first(dest)

        # ---------------------------------------------------------------
        # Static privacy/security checks
        # ---------------------------------------------------------------
        verify_no_private_files(dest)
        verify_no_embedded_secrets(dest)

        # ---------------------------------------------------------------
        # Runtime checks
        # ---------------------------------------------------------------
        verify_bundled_python(dest)
        verify_packaged_playwright(dest)

        # ---------------------------------------------------------------
        # Actual executable smoke test
        # ---------------------------------------------------------------
        smoke_test_portable_app(dest)

        # ---------------------------------------------------------------
        # Final package inventory
        # ---------------------------------------------------------------
        files = build_inventory(dest)

        inventory = {
            "version": VERSION,
            "built_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "builder_python": sys.version.split()[0],
            "platform": platform.platform(),
            "architecture": platform.machine(),
            "playwright_browser": PLAYWRIGHT_BROWSER,
            "user_data_included": False,
            "credentials_included": False,
            "browser_profiles_included": False,
            "signed": False,
            "manifest_excludes_itself": True,
            "files": files,
        }

        (dest / "package-manifest.json").write_text(
            json.dumps(
                inventory,
                indent=2,
            ),
            encoding="utf-8",
        )

        if DEST.exists():
            raise SystemExit(
                f"Output appeared during build:\n{DEST}"
            )

        dest.rename(DEST)

        total_size_gb = (
            sum(
                item["bytes"]
                for item in files
            )
            / 1_000_000_000
        )

        print()
        print("=" * 72)
        print("STONIC PORTABLE PACKAGE READY")
        print("=" * 72)
        print(
            f"Version:       {VERSION}"
        )
        print(
            f"Output:        {DEST}"
        )
        print(
            f"Files:         {len(files)}"
        )
        print(
            f"Size:          {total_size_gb:.2f} GB"
        )
        print(
            f"Playwright:    {PLAYWRIGHT_BROWSER}"
        )
        print(
            "User data:     NOT INCLUDED"
        )
        print(
            "Credentials:   NOT INCLUDED"
        )
        print(
            "Signed:        NO"
        )
        print("=" * 72)

    except BaseException:
        if STAGING.exists():
            print(
                f"Packaging failed; removing staging folder:\n"
                f"{STAGING}",
                flush=True,
            )

            shutil.rmtree(
                STAGING,
                ignore_errors=True,
            )

        raise


if __name__ == "__main__":
    build()
