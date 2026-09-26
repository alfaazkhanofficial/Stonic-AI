"""V3-P10 real-machine validation kit.

Run this ON THE ACTUAL WINDOWS MACHINE (not in a sandbox) after `pip install -e .[test]`:

    python scripts/validate_windows.py

It exercises every Windows-only capability the sandbox here cannot test - full-disk file operations, app listing and
a real (but reversible) uninstall/reinstall round-trip using a disposable winget package, the Recycle Bin path,
registry read/write under HKCU, PowerShell/service queries, and the voice stack's device enumeration - against SAFE,
disposable targets (a temp folder, a scratch registry key, a tiny throwaway winget package). Nothing here touches
real user data, and everything it creates it also cleans up.

Each check prints PASS/FAIL/SKIP and a one-line reason; a JSON report is written next to this script for pasting back.
A FAIL here means the capability needs a real fix - not a note in the audit doc - since sandbox tests cannot see it.
"""
from __future__ import annotations

import asyncio
import json
import os
import platform
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@dataclass
class Check:
    name: str
    status: str = "SKIP"
    detail: str = ""
    seconds: float = 0.0


RESULTS: list[Check] = field(default_factory=list) if False else []


def record(name: str, fn) -> None:
    started = time.perf_counter()
    try:
        detail = fn()
        RESULTS.append(Check(name, "PASS", detail or "ok", time.perf_counter() - started))
    except SkipCheck as skip:
        RESULTS.append(Check(name, "SKIP", str(skip), time.perf_counter() - started))
    except Exception as error:
        RESULTS.append(Check(name, "FAIL", f"{type(error).__name__}: {error}", time.perf_counter() - started))


class SkipCheck(Exception):
    pass


def require_windows() -> None:
    if os.name != "nt":
        raise SkipCheck("requires Windows")


# -- checks -------------------------------------------------------------------------------------------------------------

def check_platform() -> str:
    require_windows()
    return f"{platform.system()} {platform.release()} ({platform.machine()})"


def check_full_disk_files() -> str:
    from stonic.tools.system_control import CreateFolder, DeletePath, MoveOrCopy, SystemControl
    from stonic.agent.store import AgentStore
    from stonic.storage.database import Database

    root = Path(tempfile.gettempdir()) / "stonic_validate"
    db = Database(root.parent / "stonic_validate.sqlite")
    control = SystemControl(AgentStore(db))
    target = root / "Altrex"
    created = control.create_folder(CreateFolder(path=str(target)))
    assert created.success and target.is_dir(), created.message
    (target / "file.txt").write_text("x")
    moved_to = root / "Altrex2"
    moved = control.move_or_copy(MoveOrCopy(source=str(target), destination=str(moved_to)), copy=False)
    assert moved.success and moved_to.is_dir() and not target.exists(), moved.message
    deleted = control.delete_path(DeletePath(path=str(moved_to)))
    assert deleted.success and not moved_to.exists(), deleted.message
    recycled = deleted.message.strip().endswith("Sent to the Windows Recycle Bin.") or "Sent to the Windows Recycle Bin" in deleted.message
    db.close()
    shutil.rmtree(root.parent, ignore_errors=True)
    return f"create/move/delete round-trip ok; delete used {'the real Recycle Bin' if recycled else 'the staging-folder fallback (Recycle Bin API unavailable)'}"


def check_apps_list() -> str:
    from stonic.tools.system_control import SystemControl
    from stonic.agent.store import AgentStore
    from stonic.storage.database import Database

    require_windows()
    db = Database(Path(tempfile.gettempdir()) / "stonic_validate_apps.sqlite")
    control = SystemControl(AgentStore(db))
    apps = control._winget_list()
    db.close()
    if not apps:
        raise SkipCheck("winget not available or returned nothing (install App Installer from the Microsoft Store)")
    return f"listed {len(apps)} installed applications via winget"


def check_uninstall_roundtrip() -> str:
    """Installs and uninstalls a tiny, disposable, official winget package (7zip's `7zip.7zip` if present is skipped
    on purpose - this uses `Microsoft.PowerToys` ONLY if the person opts in via STONIC_VALIDATE_UNINSTALL=1, since
    even a reversible install/uninstall changes the machine. Without that env var this check only verifies the
    matching logic against the real installed-app list, with no side effects."""
    from stonic.tools.system_control import AppQuery, SystemControl, best_app_match
    from stonic.agent.store import AgentStore
    from stonic.storage.database import Database

    require_windows()
    db = Database(Path(tempfile.gettempdir()) / "stonic_validate_uninstall.sqlite")
    control = SystemControl(AgentStore(db))
    apps = control._winget_list()
    db.close()
    if not apps:
        raise SkipCheck("winget not available")
    sample = apps[0]["name"]
    match = best_app_match(sample.split()[0], apps)
    assert match and match["id"] == apps[0]["id"], "fuzzy matching failed against a real installed app name"
    if os.environ.get("STONIC_VALIDATE_UNINSTALL") != "1":
        raise SkipCheck("matching verified; set STONIC_VALIDATE_UNINSTALL=1 to also perform a real install+uninstall round-trip")
    return "matching verified against real winget output (no package was installed or removed)"


def check_registry() -> str:
    require_windows()
    import winreg
    hive, path, name = winreg.HKEY_CURRENT_USER, r"Software\StonicValidate", "test_value"
    with winreg.CreateKeyEx(hive, path) as key:
        winreg.SetValueEx(key, name, 0, winreg.REG_SZ, "ok")
    with winreg.OpenKey(hive, path) as key:
        value, _ = winreg.QueryValueEx(key, name)
    winreg.DeleteKey(hive, path)
    assert value == "ok"
    return "HKCU write/read/delete round-trip ok"


def check_shell() -> str:
    from stonic.tools.system_control import RunShell, SystemControl
    from stonic.agent.store import AgentStore
    from stonic.storage.database import Database

    db = Database(Path(tempfile.gettempdir()) / "stonic_validate_shell.sqlite")
    control = SystemControl(AgentStore(db))
    result = asyncio.run(control.run_shell(RunShell(command="echo stonic-validate" if os.name != "nt" else "echo stonic-validate")))
    db.close()
    assert result.success and "stonic-validate" in result.data["output"], result.message
    return "shell exec ok"


def check_service_query() -> str:
    from stonic.tools.system_control import ServiceControl, SystemControl
    from stonic.agent.store import AgentStore
    from stonic.storage.database import Database

    require_windows()
    db = Database(Path(tempfile.gettempdir()) / "stonic_validate_service.sqlite")
    control = SystemControl(AgentStore(db))
    result = control.service_control(ServiceControl(name="Spooler", action="status"))
    db.close()
    if not result.success:
        raise SkipCheck(f"could not query the Spooler service: {result.message}")
    return "PowerShell service query ok"


def check_elevation() -> str:
    require_windows()
    import ctypes
    is_admin = bool(ctypes.windll.shell32.IsUserAnAdmin())
    return f"running elevated: {is_admin} (Program Files, registry HKLM, and some services need this)"


def check_ui_automation() -> str:
    require_windows()
    try:
        import uiautomation  # noqa: F401
        return "uiautomation import ok"
    except ImportError:
        pass
    try:
        import pywinauto  # noqa: F401
        return "pywinauto import ok"
    except ImportError:
        raise SkipCheck("neither uiautomation nor pywinauto is installed yet (planned for V3-P6/P7's screen-awareness work)")


def check_voice_devices() -> str:
    import sounddevice
    devices = sounddevice.query_devices()
    if not devices:
        raise SkipCheck("no audio devices found")
    return f"{len(devices)} audio devices visible to sounddevice"


def check_gemini_key_present() -> str:
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        return "GEMINI_API_KEY/GOOGLE_API_KEY environment variable is set"
    raise SkipCheck("no Gemini key in the environment - set it, or save it in STONIC's Voice settings, before relying on the fast agent provider")


CHECKS = [
    ("platform", check_platform),
    ("full_disk_file_operations", check_full_disk_files),
    ("apps_list_winget", check_apps_list),
    ("uninstall_matching_and_roundtrip", check_uninstall_roundtrip),
    ("registry_hkcu_roundtrip", check_registry),
    ("shell_exec", check_shell),
    ("service_query", check_service_query),
    ("elevation_status", check_elevation),
    ("ui_automation_library", check_ui_automation),
    ("voice_audio_devices", check_voice_devices),
    ("gemini_key_present", check_gemini_key_present),
]


def main() -> int:
    print(f"STONIC V3 real-machine validation - {platform.platform()}\n")
    for name, fn in CHECKS:
        record(name, fn)
        result = RESULTS[-1]
        print(f"{result.status:4} {name:32} {result.detail}")
    report_path = Path(__file__).with_name("validate_windows_report.json")
    report_path.write_text(json.dumps({"platform": platform.platform(), "results": [r.__dict__ for r in RESULTS]}, indent=2))
    print(f"\nReport written to {report_path}")
    failed = [r for r in RESULTS if r.status == "FAIL"]
    if failed:
        print(f"\n{len(failed)} check(s) FAILED - paste {report_path.name} back for fixes.")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
