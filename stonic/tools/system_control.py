"""V3-P6: full-system control - files anywhere on disk, app install/uninstall, registry, services, shell.

Design mirrors ``WindowsTools``: OS-facing calls sit behind small, injectable methods (``self.user is None`` there,
``self._winget``/``self._registry_apps``/``self._recycle`` here) so the matching, planning and safety logic underneath
is pure and testable on any platform, while the real Windows behaviour runs unchanged when ``os.name == "nt"``.

Every destructive action here is SENSITIVE or CRITICAL, so ``AgentLoop`` always confirms it (or a real, fingerprinted
grant is required) before ``run`` is called - this module trusts that gate and focuses on doing the action safely:
recycle-bin-first deletes, an undo journal entry for every reversible change, and a restore point before uninstalls.
"""
from __future__ import annotations

import asyncio
import ctypes
import difflib
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import Field

from stonic.core.models import ActionResult, Contract, PermissionLevel
from stonic.tools.registry import Tool

WINDOWS_ROOT_SEGMENTS = {"windows", "$recycle.bin", "system volume information", "programdata\\microsoft\\windows"}


def is_system_critical(path: str) -> bool:
    """True for paths under the Windows install itself or other OS-critical locations - always double-confirmed,
    never covered by autonomous mode, regardless of the user's protected-paths list."""
    normalized = path.replace("/", "\\").casefold()
    windir = os.environ.get("WINDIR", r"C:\Windows").replace("/", "\\").casefold()
    if normalized.startswith(windir):
        return True
    drive_root = re.match(r"^[a-z]:\\*$", normalized)
    return bool(drive_root)


def normalize_path(raw: str) -> Path:
    from pathlib import PurePosixPath, PureWindowsPath
    raw = raw.strip().strip('"')
    if not (PureWindowsPath(raw).is_absolute() or PurePosixPath(raw).is_absolute()):
        raise ValueError("Give a full path (for example C:\\Users\\you\\Desktop\\Altrex or ~/Desktop/Altrex).")
    return Path(raw)


FILLER_WORDS = {"the", "app", "application", "program", "software", "please", "my"}


def _key(text: str) -> str:
    words = [w for w in re.findall(r"[a-z0-9]+", text.casefold()) if w not in FILLER_WORDS]
    return "".join(words) or re.sub(r"[^a-z0-9]+", "", text.casefold())


def best_app_match(query: str, installed: list[dict], threshold: float = 0.45) -> dict | None:
    """Fuzzy-match a spoken/typed app name ("the x app") against installed app display names."""
    query_norm = _key(query)
    if not query_norm:
        return None
    best, best_score = None, 0.0
    for app in installed:
        name_norm = _key(str(app.get("name", "")))
        if not name_norm:
            continue
        if query_norm in name_norm or name_norm in query_norm:
            score = 0.6 + 0.4 * (min(len(query_norm), len(name_norm)) / max(len(query_norm), len(name_norm)))
        else:
            score = difflib.SequenceMatcher(None, query_norm, name_norm).ratio()
        if score > best_score:
            best, best_score = app, score
    return best if best_score >= threshold else None


class FullPath(Contract):
    path: str = Field(min_length=1, max_length=1000)


class CreateFolder(FullPath):
    pass


class DeletePath(FullPath):
    reason: str = Field(default="", max_length=300, description="Optional short note for the audit log.")


class MoveOrCopy(Contract):
    source: str = Field(min_length=1, max_length=1000)
    destination: str = Field(min_length=1, max_length=1000)
    overwrite: bool = False


class AppQuery(Contract):
    name: str = Field(min_length=1, max_length=200, description="The app as the user named it, e.g. 'x app' or 'Zoom'.")


class RunShell(Contract):
    command: str = Field(min_length=1, max_length=4000)
    working_directory: str = ""
    timeout_seconds: int = Field(default=60, ge=1, le=600)


class RegistryValue(Contract):
    hive: Literal["HKCU", "HKLM"]
    path: str = Field(min_length=1, max_length=500)
    name: str = Field(default="", max_length=200)


class RegistryWrite(RegistryValue):
    value: str = Field(max_length=4000)
    value_type: Literal["REG_SZ", "REG_DWORD"] = "REG_SZ"


class ServiceControl(Contract):
    name: str = Field(min_length=1, max_length=200)
    action: Literal["start", "stop", "status"]


class UndoLast(Contract):
    entry_id: str = Field(default="", max_length=64, description="Blank undoes the most recent reversible action.")


class OrganizeFolder(Contract):
    path: str = Field(min_length=1, max_length=1000, description="Absolute folder to organize, e.g. Downloads.")
    dry_run: bool = Field(default=True, description="True previews the plan without moving anything; call again with false to apply it.")
    group_by: Literal["extension"] = "extension"


def evidence(message: str, data: dict | None = None, verification: str = "") -> ActionResult:
    return ActionResult(success=True, status="completed", message=message, data=data or {}, verification=verification or message)


class SystemControl:
    """Registers full-system tools onto the shared ``ToolRegistry``. ``agent_store`` (an ``AgentStore``) records
    every reversible change so ``system.undo_last`` can reverse it; pass the same instance ``CoreService`` uses."""

    def __init__(self, agent_store, workspace_root: Path | None = None) -> None:
        self.store = agent_store
        self.trash = (workspace_root or Path.home() / ".stonic") / "recycle_staging"

    # -- OS-facing seams (real on Windows; overridden by tests elsewhere) --------------------------------------------
    @staticmethod
    def _run(command: list[str], *, timeout: int = 30, cwd: str | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(command, capture_output=True, text=True, timeout=timeout, cwd=cwd or None,
                              creationflags=0x08000000 if os.name == "nt" else 0)

    def _recycle(self, path: Path) -> tuple[bool, str]:
        """True Windows Recycle Bin via SHFileOperationW when possible; otherwise a recoverable staging folder so the
        action is never a bare permanent delete without at least one safety net."""
        if os.name == "nt":
            try:
                class SHFILEOPSTRUCT(ctypes.Structure):
                    _fields_ = [("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint), ("pFrom", ctypes.c_wchar_p),
                                ("pTo", ctypes.c_wchar_p), ("fFlags", ctypes.c_uint16), ("fAnyOperationsAborted", ctypes.c_int),
                                ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_wchar_p)]
                FO_DELETE, FOF_ALLOWUNDO, FOF_NOCONFIRMATION, FOF_SILENT = 3, 0x40, 0x10, 0x04
                op = SHFILEOPSTRUCT(pFrom=str(path) + "\0\0", wFunc=FO_DELETE, fFlags=FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT)
                result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
                if result == 0 and not op.fAnyOperationsAborted:
                    return True, "Sent to the Windows Recycle Bin."
            except OSError:
                pass
        self.trash.mkdir(parents=True, exist_ok=True)
        destination = self.trash / f"{path.name}.{os.urandom(4).hex()}"
        shutil.move(str(path), str(destination))
        return False, f"Windows Recycle Bin unavailable here; moved to STONIC's recovery folder ({destination})."

    def _restore_point(self, description: str) -> None:
        if os.name == "nt":
            try:
                self._run(["powershell", "-NoProfile", "-Command", f"Checkpoint-Computer -Description '{description}' -RestorePointType MODIFY_SETTINGS"], timeout=60)
            except Exception:
                pass    # best-effort: a missing restore point must never block the uninstall itself

    def _winget_list(self) -> list[dict]:
        if os.name != "nt" or not shutil.which("winget"):
            return []
        try:
            process = self._run(["winget", "list", "--accept-source-agreements"], timeout=30)
        except Exception:
            return []
        apps = []
        for line in process.stdout.splitlines()[2:]:
            parts = re.split(r"\s{2,}", line.strip())
            if len(parts) >= 2 and parts[0]:
                apps.append({"name": parts[0], "id": parts[1] if len(parts) > 1 else "", "source": "winget"})
        return apps

    def _winget_uninstall(self, app_id: str) -> subprocess.CompletedProcess:
        return self._run(["winget", "uninstall", "--id", app_id, "--silent", "--accept-source-agreements"], timeout=180)

    # -- files -------------------------------------------------------------------------------------------------------
    def create_folder(self, args: CreateFolder) -> ActionResult:
        path = normalize_path(args.path)
        path.mkdir(parents=True, exist_ok=True)
        return evidence(f"Created {path}.", {"path": str(path)}, f"Directory now exists: {path.is_dir()}")

    def delete_path(self, args: DeletePath) -> ActionResult:
        path = normalize_path(args.path)
        if not path.exists():
            return ActionResult(success=False, status="failed", message=f"{path} does not exist.")
        recycled, note = self._recycle(path)
        entry_id = self.store.add_undo("delete", {"path": str(path), "recycled": recycled}, f"Deleted {path}")
        return evidence(f"Deleted {path}. {note}", {"path": str(path), "recycled": recycled, "undo_id": entry_id}, note)

    def move_or_copy(self, args: MoveOrCopy, *, copy: bool) -> ActionResult:
        source, destination = normalize_path(args.source), normalize_path(args.destination)
        if not source.exists():
            return ActionResult(success=False, status="failed", message=f"{source} does not exist.")
        if destination.exists() and not args.overwrite:
            return ActionResult(success=False, status="failed", message=f"{destination} already exists (set overwrite to replace it).")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if copy:
            (shutil.copytree if source.is_dir() else shutil.copy2)(source, destination, dirs_exist_ok=True) if source.is_dir() else shutil.copy2(source, destination)
        else:
            shutil.move(str(source), str(destination))
            self.store.add_undo("move", {"from": str(destination), "to": str(source)}, f"Moved {source} to {destination}")
        return evidence(f"{'Copied' if copy else 'Moved'} {source} to {destination}.", {"destination": str(destination)},
                        f"Exists at destination: {destination.exists()}")

    def undo_last(self, args: UndoLast) -> ActionResult:
        entries = self.store.undo_entries(limit=1) if not args.entry_id else \
            [e for e in self.store.undo_entries(limit=50) if e["id"] == args.entry_id]
        if not entries:
            return ActionResult(success=False, status="failed", message="Nothing to undo.")
        entry = entries[0]
        try:
            if entry["op"] == "move":
                shutil.move(entry["payload"]["from"], entry["payload"]["to"])
            elif entry["op"] == "delete":
                if entry["payload"].get("recycled"):
                    return ActionResult(success=False, status="failed",
                        message="That delete went to the Windows Recycle Bin; restore it from there (STONIC cannot reach the Recycle Bin's own undo API).")
                raise ValueError("Recovery copy location was not recorded.")
            else:
                return ActionResult(success=False, status="failed", message=f"Undo isn't implemented for '{entry['op']}' yet.")
        except OSError as error:
            return ActionResult(success=False, status="failed", message=f"Could not undo: {error}")
        self.store.mark_undone(entry["id"])
        return evidence(f"Undid: {entry['description']}", {"id": entry["id"]}, "Reversal applied")

    def organize_folder(self, args: OrganizeFolder) -> ActionResult:
        folder = normalize_path(args.path)
        if not folder.is_dir():
            return ActionResult(success=False, status="failed", message=f"{folder} is not a folder.")
        plan: dict[str, list[Path]] = {}
        for item in folder.iterdir():
            if item.is_file():
                key = (item.suffix.lstrip(".") or "no-extension").casefold()
                plan.setdefault(key, []).append(item)
        summary = {group: [f.name for f in files] for group, files in plan.items()}
        if args.dry_run:
            total = sum(len(files) for files in plan.values())
            return evidence(f"Would move {total} files into {len(plan)} folders (by {args.group_by}). Nothing has changed yet.",
                            {"plan": summary, "dry_run": True}, "Plan computed, no files touched")
        moved, undo_ids = 0, []
        for group, files in plan.items():
            destination_dir = folder / group
            destination_dir.mkdir(exist_ok=True)
            for file in files:
                destination = destination_dir / file.name
                if destination.exists():
                    continue
                shutil.move(str(file), str(destination))
                undo_ids.append(self.store.add_undo("move", {"from": str(destination), "to": str(file)}, f"Organized {file.name} into {group}/"))
                moved += 1
        return evidence(f"Moved {moved} files into {len(plan)} folders under {folder}.",
                        {"plan": summary, "dry_run": False, "moved": moved, "undo_ids": undo_ids},
                        f"{moved} files relocated on disk")

    # -- apps ----------------------------------------------------------------------------------------------------------
    def list_apps(self, _args: Contract | None = None) -> ActionResult:
        apps = self._winget_list()
        return evidence(f"Found {len(apps)} installed applications." if apps else
                        "No installed-application list is available on this platform (requires Windows with winget).",
                        {"applications": apps}, f"{len(apps)} entries read")

    def uninstall_app(self, args: AppQuery) -> ActionResult:
        apps = self._winget_list()
        if not apps:
            return ActionResult(success=False, status="failed",
                message="Could not list installed applications (requires Windows with winget available).")
        match = best_app_match(args.name, apps)
        if not match:
            names = ", ".join(a["name"] for a in apps[:8])
            return ActionResult(success=False, status="failed", message=f"No installed app matched '{args.name}'. Closest options: {names}.")
        self._restore_point(f"Before uninstalling {match['name']}")
        process = self._winget_uninstall(match["id"])
        ok = process.returncode == 0
        return ActionResult(success=ok, status="completed" if ok else "failed",
            message=(f"Uninstalled {match['name']}." if ok else f"winget could not uninstall {match['name']}: {process.stderr.strip()[:300]}"),
            data={"app": match["name"], "id": match["id"]}, verification=f"winget exit code {process.returncode}" if ok else None)

    # -- shell / registry / services -------------------------------------------------------------------------------------
    async def run_shell(self, args: RunShell) -> ActionResult:
        process = await asyncio.create_subprocess_shell(
            args.command, cwd=args.working_directory or None, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=args.timeout_seconds)
        except TimeoutError:
            process.kill()
            await process.wait()             # reap the child so its transport does not outlive this event loop
            return ActionResult(success=False, status="failed", message=f"Command did not finish within {args.timeout_seconds}s.")
        ok = process.returncode == 0
        output = (stdout or b"").decode(errors="replace")[-4000:]
        return ActionResult(success=ok, status="completed" if ok else "failed",
            message=(f"Command exited 0." if ok else f"Command exited {process.returncode}: {(stderr or b'').decode(errors='replace')[:300]}"),
            data={"exit_code": process.returncode, "output": output}, verification=f"exit code {process.returncode}" if ok else None)

    def registry_read(self, args: RegistryValue) -> ActionResult:
        if os.name != "nt":
            return ActionResult(success=False, status="failed", message="Registry access requires Windows.")
        import winreg
        hive = winreg.HKEY_CURRENT_USER if args.hive == "HKCU" else winreg.HKEY_LOCAL_MACHINE
        try:
            with winreg.OpenKey(hive, args.path) as key:
                value, kind = winreg.QueryValueEx(key, args.name or None)
        except OSError as error:
            return ActionResult(success=False, status="failed", message=f"Could not read {args.hive}\\{args.path}: {error}")
        return evidence(f"Read {args.hive}\\{args.path}.", {"value": value, "type": kind}, "Registry value read")

    def registry_write(self, args: RegistryWrite) -> ActionResult:
        if os.name != "nt":
            return ActionResult(success=False, status="failed", message="Registry access requires Windows.")
        import winreg
        hive = winreg.HKEY_CURRENT_USER if args.hive == "HKCU" else winreg.HKEY_LOCAL_MACHINE
        kind = winreg.REG_DWORD if args.value_type == "REG_DWORD" else winreg.REG_SZ
        value = int(args.value) if kind == winreg.REG_DWORD else args.value
        try:
            with winreg.CreateKeyEx(hive, args.path) as key:
                winreg.SetValueEx(key, args.name or None, 0, kind, value)
        except OSError as error:
            return ActionResult(success=False, status="failed", message=f"Could not write {args.hive}\\{args.path}: {error}")
        self.store.add_undo("registry", {"hive": args.hive, "path": args.path, "name": args.name}, f"Set {args.hive}\\{args.path}\\{args.name}")
        return evidence(f"Set {args.hive}\\{args.path}\\{args.name}.", {}, "Registry value written and key opened for confirmation")

    def service_control(self, args: ServiceControl) -> ActionResult:
        if os.name != "nt":
            return ActionResult(success=False, status="failed", message="Service control requires Windows.")
        verb = {"start": "Start-Service", "stop": "Stop-Service", "status": "Get-Service"}[args.action]
        process = self._run(["powershell", "-NoProfile", "-Command", f"{verb} -Name '{args.name}' | Format-List"], timeout=30)
        ok = process.returncode == 0
        return ActionResult(success=ok, status="completed" if ok else "failed",
            message=process.stdout.strip()[:500] if ok else process.stderr.strip()[:300],
            data={"output": process.stdout}, verification=f"exit code {process.returncode}" if ok else None)

    # -- registration --------------------------------------------------------------------------------------------------
    def register(self, registry) -> None:
        items = [
            ("system.create_folder", "Create a folder anywhere on disk (not limited to the workspace)", CreateFolder, PermissionLevel.NORMAL, self.create_folder),
            ("system.delete_path", "Delete a file or folder anywhere on disk; goes to the Recycle Bin when possible", DeletePath, PermissionLevel.SENSITIVE, self.delete_path),
            ("system.move_path", "Move a file or folder anywhere on disk", MoveOrCopy, PermissionLevel.NORMAL, lambda a: self.move_or_copy(a, copy=False)),
            ("system.copy_path", "Copy a file or folder anywhere on disk", MoveOrCopy, PermissionLevel.NORMAL, lambda a: self.move_or_copy(a, copy=True)),
            ("system.undo_last", "Reverse the most recent reversible file action, or a specific one by id", UndoLast, PermissionLevel.NORMAL, self.undo_last),
            ("system.organize_folder", "Preview (dry_run=true, default) or apply (dry_run=false) organizing a folder's files into subfolders by extension", OrganizeFolder, PermissionLevel.NORMAL, self.organize_folder),
            ("system.list_apps", "List installed applications (winget)", Contract, PermissionLevel.SAFE, self.list_apps),
            ("system.uninstall_app", "Uninstall an application by name (fuzzy-matched against installed apps)", AppQuery, PermissionLevel.SENSITIVE, self.uninstall_app),
            ("system.run_shell", "Run a shell command (PowerShell/cmd) for anything with no dedicated tool", RunShell, PermissionLevel.SENSITIVE, self.run_shell),
            ("system.registry_read", "Read a Windows registry value", RegistryValue, PermissionLevel.SAFE, self.registry_read),
            ("system.registry_write", "Write a Windows registry value", RegistryWrite, PermissionLevel.CRITICAL, self.registry_write),
            ("system.service_control", "Start, stop, or query a Windows service", ServiceControl, PermissionLevel.SENSITIVE, self.service_control),
        ]
        for name, description, args_type, level, run in items:
            registry.register(Tool(name, description, args_type, level, run))
