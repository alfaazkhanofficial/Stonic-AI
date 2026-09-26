"""system_control: full-disk file operations, app uninstall matching, undo journal, registry/shell/service tools.

OS-facing calls (winget subprocess, SHFileOperationW, winreg, powershell) are monkeypatched at the small seam methods
(``_winget_list``, ``_winget_uninstall``, ``_recycle``, ``_run``), matching how the rest of the codebase tests
Windows-only code. The file/undo logic underneath runs for real, cross-platform, against tmp_path.
"""
import asyncio
import subprocess
from pathlib import Path

import pytest

from stonic.agent.store import AgentStore
from stonic.core.models import ActionResult, PermissionLevel
from stonic.storage.database import Database
from stonic.tools.system_control import (AppQuery, CreateFolder, DeletePath, MoveOrCopy, OrganizeFolder, RunShell, SystemControl,
                                         UndoLast, best_app_match, is_system_critical, normalize_path)


def build(tmp_path):
    db = Database(Path(tmp_path) / "s.db")
    control = SystemControl(AgentStore(db), Path(tmp_path) / "workspace")
    control.trash = Path(tmp_path) / "trash"
    return control, db


# -- pure logic: matching, path safety --------------------------------------------------------------------------------

def test_is_system_critical_flags_windows_root_and_drive_root():
    assert is_system_critical(r"C:\Windows\System32") is True
    assert is_system_critical(r"C:\\") is True
    assert is_system_critical(r"C:\Users\alfaaz\Desktop\Altrex") is False


def test_normalize_path_requires_absolute():
    normalize_path(r"C:\Users\alfaaz\Desktop\Altrex")
    with pytest.raises(ValueError):
        normalize_path("Desktop/Altrex")


def test_best_app_match_resolves_fuzzy_and_substring_names():
    installed = [{"name": "Zoom Workplace"}, {"name": "Discord"}, {"name": "7-Zip"}]
    assert best_app_match("zoom", installed)["name"] == "Zoom Workplace"
    assert best_app_match("discrod", installed)["name"] == "Discord"
    assert best_app_match("completely unrelated app xyz", installed) is None


# -- files: create, delete-with-recycle, move, undo --------------------------------------------------------------------

def test_create_folder_creates_absolute_path(tmp_path):
    control, db = build(tmp_path)
    target = tmp_path / "Desktop" / "Altrex"
    result = control.create_folder(CreateFolder(path=str(target)))
    assert result.success and target.is_dir()
    db.close()


def test_delete_path_falls_back_to_staging_and_records_undo(tmp_path, monkeypatch):
    control, db = build(tmp_path)
    monkeypatch.setattr("os.name", "posix")            # force the non-Windows fallback path deterministically
    target = tmp_path / "Jarvis"
    target.mkdir()
    (target / "file.txt").write_text("x")
    result = control.delete_path(DeletePath(path=str(target)))
    assert result.success and not target.exists()
    assert "recovery folder" in result.message
    entries = control.store.undo_entries()
    assert entries and entries[0]["op"] == "delete" and entries[0]["payload"]["recycled"] is False
    db.close()


def test_delete_missing_path_fails_cleanly(tmp_path):
    control, db = build(tmp_path)
    result = control.delete_path(DeletePath(path=str(tmp_path / "nope")))
    assert not result.success
    db.close()


def test_move_path_records_undo_and_undo_last_reverses_it(tmp_path):
    control, db = build(tmp_path)
    source = tmp_path / "a.txt"; source.write_text("hi")
    destination = tmp_path / "b.txt"
    moved = control.move_or_copy(MoveOrCopy(source=str(source), destination=str(destination)), copy=False)
    assert moved.success and destination.exists() and not source.exists()
    undone = control.undo_last(UndoLast(entry_id=""))
    assert undone.success and source.exists() and not destination.exists()
    db.close()


def test_undo_of_recycled_delete_explains_it_cannot_reach_the_recycle_bin(tmp_path, monkeypatch):
    control, db = build(tmp_path)
    control.store.add_undo("delete", {"path": str(tmp_path / "x"), "recycled": True}, "Deleted x")
    result = control.undo_last(UndoLast(entry_id=""))
    assert not result.success and "Recycle Bin" in result.message
    db.close()


def test_copy_does_not_remove_the_source(tmp_path):
    control, db = build(tmp_path)
    source = tmp_path / "a.txt"; source.write_text("hi")
    destination = tmp_path / "copy.txt"
    result = control.move_or_copy(MoveOrCopy(source=str(source), destination=str(destination)), copy=True)
    assert result.success and source.exists() and destination.exists()
    db.close()


def test_move_refuses_to_overwrite_without_explicit_flag(tmp_path):
    control, db = build(tmp_path)
    source = tmp_path / "a.txt"; source.write_text("1")
    destination = tmp_path / "b.txt"; destination.write_text("2")
    result = control.move_or_copy(MoveOrCopy(source=str(source), destination=str(destination), overwrite=False), copy=False)
    assert not result.success and destination.read_text() == "2"
    db.close()


# -- apps: uninstall orchestration (winget mocked) -----------------------------------------------------------------------

def test_uninstall_app_matches_and_calls_winget(tmp_path, monkeypatch):
    control, db = build(tmp_path)
    control._winget_list = lambda: [{"name": "Zoom Workplace", "id": "Zoom.Zoom"}]
    control._restore_point = lambda desc: None
    calls = []
    control._winget_uninstall = lambda app_id: calls.append(app_id) or subprocess.CompletedProcess(["winget"], 0, "", "")
    result = control.uninstall_app(AppQuery(name="the zoom app"))
    assert result.success and calls == ["Zoom.Zoom"]
    db.close()


def test_uninstall_app_reports_no_match_with_suggestions(tmp_path):
    control, db = build(tmp_path)
    control._winget_list = lambda: [{"name": "Discord", "id": "Discord.Discord"}]
    result = control.uninstall_app(AppQuery(name="something totally unrelated"))
    assert not result.success and "Discord" in result.message
    db.close()


def test_uninstall_app_without_winget_fails_clearly(tmp_path):
    control, db = build(tmp_path)
    control._winget_list = lambda: []
    result = control.uninstall_app(AppQuery(name="anything"))
    assert not result.success and "winget" in result.message
    db.close()


def test_uninstall_failure_surfaces_winget_stderr(tmp_path):
    control, db = build(tmp_path)
    control._winget_list = lambda: [{"name": "X App", "id": "Vendor.X"}]
    control._restore_point = lambda desc: None
    control._winget_uninstall = lambda app_id: subprocess.CompletedProcess(["winget"], 1, "", "access denied")
    result = control.uninstall_app(AppQuery(name="x app"))
    assert not result.success and "access denied" in result.message
    db.close()


# -- shell -------------------------------------------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_run_shell_reports_exit_code_and_output(tmp_path):
    control, db = build(tmp_path)
    result = await control.run_shell(RunShell(command="echo hello", timeout_seconds=10))
    assert result.success and "hello" in result.data["output"]
    db.close()


@pytest.mark.asyncio
async def test_run_shell_reports_nonzero_exit(tmp_path):
    control, db = build(tmp_path)
    result = await control.run_shell(RunShell(command="exit 3", timeout_seconds=10))
    assert not result.success and result.data["exit_code"] == 3
    db.close()


@pytest.mark.asyncio
async def test_run_shell_times_out_cleanly(tmp_path):
    control, db = build(tmp_path)
    result = await control.run_shell(RunShell(command="sleep 5", timeout_seconds=1))
    assert not result.success and "did not finish" in result.message
    await asyncio.sleep(0.05)          # let asyncio finish reaping the killed child before the loop closes
    db.close()


# -- registration & permission levels ------------------------------------------------------------------------------------

def test_registers_every_tool_with_the_intended_permission_level(tmp_path):
    from stonic.security.permissions import PermissionGate
    from stonic.tools.registry import ToolRegistry
    control, db = build(tmp_path)
    registry = ToolRegistry(PermissionGate())
    control.register(registry)
    levels = {t.name: t.level for t in registry.tools.values()}
    assert levels["system.delete_path"] == PermissionLevel.SENSITIVE
    assert levels["system.uninstall_app"] == PermissionLevel.SENSITIVE
    assert levels["system.registry_write"] == PermissionLevel.CRITICAL
    assert levels["system.list_apps"] == PermissionLevel.SAFE
    assert levels["system.create_folder"] == PermissionLevel.NORMAL
    db.close()


def test_registry_and_service_tools_report_windows_only_off_windows(tmp_path, monkeypatch):
    control, db = build(tmp_path)
    monkeypatch.setattr("os.name", "posix")
    from stonic.tools.system_control import RegistryValue, ServiceControl
    assert not control.registry_read(RegistryValue(hive="HKCU", path="Software")).success
    assert not control.service_control(ServiceControl(name="Spooler", action="status")).success
    db.close()


# -- organize folder: dry-run, apply, undo -----------------------------------------------------------------------------

def test_organize_folder_dry_run_previews_without_moving_anything(tmp_path):
    control, db = build(tmp_path)
    folder = tmp_path / "Downloads"; folder.mkdir()
    (folder / "a.pdf").write_text("1"); (folder / "b.pdf").write_text("2"); (folder / "c.jpg").write_text("3")
    result = control.organize_folder(OrganizeFolder(path=str(folder), dry_run=True))
    assert result.success and result.data["dry_run"] is True
    assert set(result.data["plan"]["pdf"]) == {"a.pdf", "b.pdf"} and result.data["plan"]["jpg"] == ["c.jpg"]
    assert (folder / "a.pdf").exists() and not (folder / "pdf").exists()
    db.close()


def test_organize_folder_apply_moves_files_and_records_undo(tmp_path):
    control, db = build(tmp_path)
    folder = tmp_path / "Downloads"; folder.mkdir()
    (folder / "a.pdf").write_text("1"); (folder / "notes").write_text("2")  # no extension
    result = control.organize_folder(OrganizeFolder(path=str(folder), dry_run=False))
    assert result.success and result.data["moved"] == 2
    assert (folder / "pdf" / "a.pdf").exists() and (folder / "no-extension" / "notes").exists()
    for entry_id in result.data["undo_ids"]:
        control.undo_last(UndoLast(entry_id=entry_id))
    assert (folder / "a.pdf").exists() and (folder / "notes").exists()
    db.close()


def test_organize_folder_rejects_a_non_folder(tmp_path):
    control, db = build(tmp_path)
    result = control.organize_folder(OrganizeFolder(path=str(tmp_path / "missing"), dry_run=True))
    assert not result.success
    db.close()


def test_organize_folder_skips_existing_destination_names(tmp_path):
    control, db = build(tmp_path)
    folder = tmp_path / "Downloads"; folder.mkdir()
    (folder / "pdf").mkdir()
    (folder / "pdf" / "a.pdf").write_text("existing")
    (folder / "a.pdf").write_text("new")
    result = control.organize_folder(OrganizeFolder(path=str(folder), dry_run=False))
    assert result.success and result.data["moved"] == 0
    assert (folder / "a.pdf").read_text() == "new"     # left alone rather than overwritten
    db.close()
