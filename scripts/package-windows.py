"""Assemble an unsigned, offline-capable Windows folder from verified local assets.

Uses an explicit allowlist. User records, credentials, browser profiles and caches are never copied.
"""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads((ROOT / "package.json").read_text())["version"]
RELEASE_ROOT = ROOT / "release"
DEST = RELEASE_ROOT / f"Stonic-V2-{VERSION}-win-x64"


def copy_tree(source, destination, ignore=None):
    shutil.copytree(
        source,
        destination,
        dirs_exist_ok=True,
        ignore=ignore
        or shutil.ignore_patterns(
            "__pycache__",
            "*.pyc",
            ".git",
            "*.log",
        ),
    )


def copy_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def build():
    if os.name != "nt" or sys.version_info[:2] != (3, 12):
        raise SystemExit(
            "Package with the project Python 3.12 environment on Windows."
        )

    machine = platform.machine().lower()
    pointer_bits = 8 * __import__("struct").calcsize("P")

    if machine not in {"amd64", "x86_64", "amd64t"} or pointer_bits != 64:
        raise SystemExit(
            f"Expected a 64-bit Windows Python build; "
            f"got {platform.machine()} / {pointer_bits} bits."
        )

    final_dest = DEST

    if final_dest.exists():
        raise SystemExit(
            f"Output already exists: {final_dest}. "
            "Preserve it or choose a new version before rebuilding."
        )

    RELEASE_ROOT.mkdir(parents=True, exist_ok=True)

    staging = RELEASE_ROOT / (final_dest.name + ".staging")

    if staging.exists():
        shutil.rmtree(staging)

    dest = staging
    app = dest / "resources" / "app"

    if shutil.disk_usage(ROOT).free < 5_000_000_000:
        raise SystemExit(
            "At least 5 GB free disk space is required to assemble the portable folder."
        )

    if not (ROOT / "dist" / "index.html").is_file():
        raise SystemExit("Run npm run build before packaging.")

    # Allow package-time project imports.
    sys.path.insert(0, str(ROOT))

    print("Copying the Electron desktop runtime.", flush=True)

    electron_dist = ROOT / "node_modules" / "electron" / "dist"

    if not electron_dist.is_dir():
        raise SystemExit(
            f"Electron runtime is missing: {electron_dist}"
        )

    copy_tree(electron_dist, dest)

    electron_exe = dest / "electron.exe"

    if not electron_exe.is_file():
        raise SystemExit(
            f"Electron executable is missing: {electron_exe}"
        )

    electron_exe.rename(dest / "Stonic.exe")

    # Explicit application allowlist.
    for name in ["desktop", "dist", "stonic", "docs"]:
        source = ROOT / name

        if not source.exists():
            raise SystemExit(
                f"Required project directory is missing: {source}"
            )

        copy_tree(source, app / name)

    # Runtime helper scripts.
    for name in ["runtime.cjs", "browser-worker.mjs"]:
        source = ROOT / "scripts" / name

        if not source.is_file():
            raise SystemExit(
                f"Required runtime script is missing: {source}"
            )

        copy_file(source, app / "scripts" / name)

    # Project metadata.
    for name in [
        "package.json",
        "pyproject.toml",
        "uv.lock",
        "package-lock.json",
        "README.md",
    ]:
        source = ROOT / name

        if not source.is_file():
            raise SystemExit(
                f"Required project file is missing: {source}"
            )

        copy_file(source, app / name)

    print(
        "Copying the private Python runtime and locked packages.",
        flush=True,
    )

    base = Path(sys.base_prefix)
    python = app / "runtime" / "python"

    if not base.is_dir():
        raise SystemExit(
            f"Python base runtime directory is missing: {base}"
        )

    # Copy the Python standard library and DLLs,
    # but do not copy the environment's site-packages here.
    for name in ["Lib", "DLLs"]:
        source = base / name

        if not source.is_dir():
            raise SystemExit(
                f"Required Python directory is missing: {source}"
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

    # Copy Python executables and DLLs required by the private runtime.
    for file in base.iterdir():
        if file.is_file() and (
            file.suffix.lower() in {".exe", ".dll"}
            or file.name == "LICENSE.txt"
        ):
            copy_file(file, python / file.name)

    # Copy locked third-party packages from the project's venv.
    site_packages = ROOT / ".venv" / "Lib" / "site-packages"

    if not site_packages.is_dir():
        raise SystemExit(
            f"Virtualenv site-packages directory is missing: {site_packages}"
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

    # IMPORTANT:
    # Keep the actual STONIC package at:
    #
    #   resources/app/stonic
    #
    # rather than copying it into site-packages.
    #
    # The bundled Python is isolated by python312._pth, so resources/app
    # must explicitly be placed on sys.path.
    #
    # From:
    #
    #   resources/app/runtime/python
    #
    # ../.. resolves to:
    #
    #   resources/app
    #
    # This is required because the STONIC backend also serves:
    #
    #   resources/app/dist/index.html
    #
    # and resolves paths relative to the application root.

    python_pth = python / "python312._pth"

    python_pth.write_text(
        ".\n"
        "DLLs\n"
        "Lib\n"
        "Lib/site-packages\n"
        "import site\n",
        encoding="utf-8",
    )

# Explicitly add resources/app to the bundled Python path.
# site-packages -> app requires four parent levels.
    app_root_pth = python / "Lib" / "site-packages" / "stonic-app-root.pth"
    app_root_pth.write_text(
        "../../../../\n",
        encoding="ascii",
    )

    print(
        "Copying the owned browser helper and Node runtime.",
        flush=True,
    )

    node_path = shutil.which("node")

    if not node_path:
        raise SystemExit("Node.js is missing.")

    node = Path(node_path)

    if not node.is_file():
        raise SystemExit(
            f"Node.js executable is missing: {node}"
        )

    bundled_node = app / "runtime" / "node"

    copy_file(
        node,
        bundled_node / "node.exe",
    )

    for file in node.parent.iterdir():
        if file.is_file() and file.name.lower().startswith(
            ("license", "npm", "npx")
        ):
            copy_file(
                file,
                bundled_node / file.name,
            )

    npm_source = node.parent / "node_modules" / "npm"

    if not npm_source.is_dir():
        raise SystemExit(
            f"Bundled npm runtime is missing: {npm_source}"
        )

    copy_tree(
        npm_source,
        bundled_node / "node_modules" / "npm",
    )

    for package in ["playwright", "playwright-core"]:
        source = ROOT / "node_modules" / package

        if not source.is_dir():
            raise SystemExit(
                f"Required Node package is missing: {source}"
            )

        copy_tree(
            source,
            app / "node_modules" / package,
        )

    # Optional PresentMon integration.
    if (ROOT / "integrations" / "presentmon").is_dir():
        copy_tree(
            ROOT / "integrations" / "presentmon",
            app / "integrations" / "presentmon",
        )

    # Local OCR runtime.
    tesseract = Path(
        shutil.which("tesseract")
        or r"C:\Program Files\Tesseract-OCR\tesseract.exe"
    ).parent

    if (tesseract / "tesseract.exe").is_file():
        print(
            "Copying local OCR runtime and notices.",
            flush=True,
        )

        copy_tree(
            tesseract,
            app / "integrations" / "tesseract",
            shutil.ignore_patterns(
                "unins*",
                "Uninstall*",
                "*.log",
            ),
        )

    print(
        "Checking imports using only the bundled Python.",
        flush=True,
    )

    # Prevent host/environment secrets and external Python paths from leaking
    # into the portable package test.
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(
            secret in key.upper()
            for secret in (
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
        )
    }

    bundled_python = python / "python.exe"

    if not bundled_python.is_file():
        raise SystemExit(
            f"Bundled Python executable was not created: {bundled_python}"
        )

    result = subprocess.run(
        [
            str(bundled_python),
            "-I",
            "-c",
            (
                "import sys; "
                "import fastapi, uvicorn, httpx, psutil, pydantic, PIL; "
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

    if result.returncode:
        output = "\n".join(
            part
            for part in [result.stdout, result.stderr]
            if part
        )

        raise SystemExit(
            "Portable imports failed:\n"
            + output[-5000:]
        )

    print(result.stdout.strip(), flush=True)

    # Human-readable package notice.
    (dest / "READ-ME-FIRST.txt").write_text(
        "STONIC V2 "
        + VERSION
        + " — Windows portable build\n\n"
        "Open Stonic.exe from this extracted folder. "
        "Keep all bundled folders together.\n"
        "Python, Node and local OCR are included. "
        "xKiro needs your own key and Internet access.\n"
        "Configure xKiro inside Configuration. "
        "User data is stored in the Windows user-data directory, "
        "not the install folder.\n"
        "This package contains no saved API key or user records.\n\n"
        "This is an unsigned development build. Hardware acceptance "
        "and measured latency limits are documented\n"
        "in resources/app/docs/BUILD_STATUS.md; it is not certified "
        "as meeting every specification gate.\n",
        encoding="utf-8",
    )

    files = []

    print(
        "Recording the package file inventory and checksums.",
        flush=True,
    )

    for path in sorted(dest.rglob("*")):
        if path.is_file():
            with path.open("rb") as source:
                digest = hashlib.file_digest(
                    source,
                    "sha256",
                ).hexdigest()

            files.append(
                {
                    "path": path.relative_to(dest).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": digest,
                }
            )

    inventory = {
        "version": VERSION,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "python": sys.version.split()[0],
        "user_data_included": False,
        "signed": False,
        "files": files,
    }

    (dest / "package-manifest.json").write_text(
        json.dumps(inventory, indent=2),
        encoding="utf-8",
    )

    if final_dest.exists():
        raise SystemExit(
            f"Output appeared during build: {final_dest}"
        )

    dest.rename(final_dest)

    total_size_gb = (
        sum(file_info["bytes"] for file_info in files) / 1e9
    )

    print(
        f"Portable folder ready: {final_dest}",
        flush=True,
    )

    print(
        f"{len(files)} files; "
        f"{total_size_gb:.2f} GB. "
        "No user data included.",
        flush=True,
    )


if __name__ == "__main__":
    build()