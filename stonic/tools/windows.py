"""Narrow Windows adapters: observed handles, explicit targets, no spoken shell commands."""
import asyncio
import ctypes
import os
from ctypes import wintypes
from pathlib import Path
from typing import Literal
from pydantic import Field
from stonic.core.models import Contract, PermissionLevel as Level, ActionResult
from stonic.tools.registry import Tool
from stonic.tools.workspace import success
from stonic.security.process import sanitized_environment


class NoArguments(Contract):
    pass


class WindowTarget(Contract):
    hwnd: int = Field(ge=1)
    expected_pid: int = Field(ge=1)
    expected_title: str = Field(max_length=1000)


class WindowAction(WindowTarget):
    action: Literal["focus", "minimize", "maximize", "restore", "close"]


class TypeText(WindowTarget):
    text: str = Field(min_length=1, max_length=10000)


class Hotkey(WindowTarget):
    keys: list[str] = Field(min_length=1, max_length=4)


class MouseClick(WindowTarget):
    x: int = Field(ge=-32000, le=32000)
    y: int = Field(ge=-32000, le=32000)
    button: Literal["left", "right", "double"] = "left"


class LaunchApp(Contract):
    app: str = Field(min_length=1, max_length=120, description=(
        "Shortcuts (any wording matches): chrome/google chrome, edge/microsoft edge, notepad, calculator, explorer/file explorer. "
        "For anything else, first call computer.applications and pass one of the returned names."))


class ClipboardText(Contract):
    text: str = Field(max_length=100000)


class SettingsPage(Contract):
    page: Literal["display", "sound", "privacy-microphone", "network-status", "bluetooth", "appsfeatures"]


# Common ways people and models refer to these apps, mapped to the shortcut keys in WindowsTools.launch.
# The registry's own names for them ("msedge.exe", "chrome.exe") rarely match how they are asked for.
APP_ALIASES = {
    "chrome": "chrome", "google chrome": "chrome", "chrome browser": "chrome", "googlechrome": "chrome",
    "edge": "edge", "microsoft edge": "edge", "msedge": "edge", "edge browser": "edge",
    "notepad": "notepad", "windows notepad": "notepad",
    "calculator": "calculator", "calc": "calculator", "windows calculator": "calculator",
    "explorer": "explorer", "file explorer": "explorer", "windows explorer": "explorer", "my computer": "explorer",
}
_APP_STOPWORDS = {"microsoft", "google", "app", "application", "browser", "the", "windows"}


def _normalize_app_name(raw: str) -> str:
    return " ".join(raw.casefold().removesuffix(".exe").replace("-", " ").split())


def resolve_application(requested_raw: str, candidates: list[dict], choices: dict[str, list]):
    """Find the executable for a requested app name.

    Tries, in order: a known alias or shortcut key; an exact match against a registered application's
    name; and finally a same-meaning match that ignores generic words like "Microsoft" or "browser" so
    "Google Chrome" and "chrome.exe" resolve to the same thing. Raises ValueError, with the closest
    registered names when there are any, if nothing said the same thing plainly enough to act on.
    """
    normalized = _normalize_app_name(requested_raw)
    key = APP_ALIASES.get(normalized)
    if key:
        registered = [Path(a["path"]) for a in candidates if _normalize_app_name(a["name"]) == key]
        executable = next((p for p in registered + choices[key] if p.is_file()), None)
        if executable is not None:
            return executable
        raise ValueError(f"'{requested_raw}' is not installed at a known Windows location.")

    exact = [a for a in candidates if _normalize_app_name(a["name"]) == normalized]
    if len(exact) == 1:
        return Path(exact[0]["path"])

    words = set(normalized.split()) - _APP_STOPWORDS
    if words:
        # The request may add descriptive words ("Visual Studio Code" for "Code.exe", "Slack Messenger" for
        # "Slack.exe"): a unique candidate whose OWN meaningful words are fully contained in the request's is
        # a safe match. The reverse is not checked, so a bare "notepad" never matches "Notepad++".
        same_meaning = [a for a in candidates
                        if (candidate_words := set(_normalize_app_name(a["name"]).split()) - _APP_STOPWORDS) and candidate_words <= words]
        if len(same_meaning) == 1:
            return Path(same_meaning[0]["path"])

    close = sorted({a["name"] for a in candidates if words & (set(_normalize_app_name(a["name"]).split()) - _APP_STOPWORDS)})[:5]
    hint = f" Close matches from installed applications: {', '.join(close)}." if close else " Call computer.applications to see exact registered names."
    raise ValueError(f"'{requested_raw}' is not a recognized shortcut or a registered application name.{hint}")


class WindowsTools:
    def __init__(self, config):
        self.config = config
        self.user = None
        if os.name == "nt":
            self.user = ctypes.WinDLL("user32", use_last_error=True)
            signatures = {
                "GetForegroundWindow": ([], wintypes.HWND),
                "IsWindow": ([wintypes.HWND], wintypes.BOOL),
                "IsWindowVisible": ([wintypes.HWND], wintypes.BOOL),
                "IsIconic": ([wintypes.HWND], wintypes.BOOL),
                "IsZoomed": ([wintypes.HWND], wintypes.BOOL),
                "WindowFromPoint": ([wintypes.POINT], wintypes.HWND),
                "GetAncestor": ([wintypes.HWND, wintypes.UINT], wintypes.HWND),
                "GetWindowTextLengthW": ([wintypes.HWND], ctypes.c_int),
                "GetWindowTextW": ([wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
                "GetWindowThreadProcessId": ([wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
                "SetForegroundWindow": ([wintypes.HWND], wintypes.BOOL),
                "ShowWindow": ([wintypes.HWND, ctypes.c_int], wintypes.BOOL),
                "PostMessageW": ([wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], wintypes.BOOL),
                "GetWindowRect": ([wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
                "SetCursorPos": ([ctypes.c_int, ctypes.c_int], wintypes.BOOL),
            }
            for name, (args, result) in signatures.items():
                function = getattr(self.user, name)
                function.argtypes, function.restype = args, result

    def require(self):
        if self.user is None:
            raise ValueError("Windows desktop control is unavailable on this platform")

    def info(self, hwnd):
        self.require()
        if not self.user.IsWindow(hwnd):
            raise ValueError("Window no longer exists")
        title = ctypes.create_unicode_buffer(min(1000, self.user.GetWindowTextLengthW(hwnd)) + 1)
        self.user.GetWindowTextW(hwnd, title, len(title))
        pid = wintypes.DWORD()
        self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        rect = wintypes.RECT()
        self.user.GetWindowRect(hwnd, ctypes.byref(rect))
        return {"hwnd": hwnd, "pid": pid.value, "title": title.value,
                "minimized":bool(self.user.IsIconic(hwnd)), "maximized":bool(self.user.IsZoomed(hwnd)),
                "bounds": {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom}}

    def windows(self, _=None):
        self.require()
        rows = []
        callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visit(hwnd, _):
            if self.user.IsWindowVisible(hwnd):
                try:
                    info = self.info(hwnd)
                    if info["title"]:
                        rows.append(info)
                except ValueError:
                    pass
            return True
        callback = callback_type(visit)
        self.user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
        self.user.EnumWindows(callback, 0)
        return success("Visible windows inspected.", {"windows": rows}, "Windows enumerated through user32")

    def context(self):
        if not self.config.values.context_enabled or self.user is None:
            return {"enabled": False}
        hwnd = self.user.GetForegroundWindow()
        return {"enabled": True, "foreground": self.info(hwnd)} if hwnd else {"enabled": True, "foreground": None}

    def target(self, args, focus=False):
        info = self.info(args.hwnd)
        if info["pid"] != args.expected_pid or info["title"] != args.expected_title:
            raise ValueError("Window changed since inspection; inspect again before acting")
        if focus:
            self.user.ShowWindow(args.hwnd, 9)
            self.user.SetForegroundWindow(args.hwnd)
            if self.user.GetForegroundWindow() != args.hwnd:
                raise ValueError("Windows did not grant focus to the requested window")
        return info

    async def action(self, args):
        self.target(args)
        if args.action == "close":
            if not self.user.PostMessageW(args.hwnd, 0x0010, 0, 0):
                raise ValueError("Window did not accept the close request")
            await asyncio.sleep(.3)
            if self.user.IsWindow(args.hwnd):
                return ActionResult(success=False, status="failed", message="The window remains open, possibly waiting to save changes. Inspect it before continuing.")
            return success("Window closed.", {"hwnd": args.hwnd}, "The targeted window handle no longer exists")
        if args.action == "focus":
            self.target(args, True)
        else:
            self.user.ShowWindow(args.hwnd, {"minimize": 6, "maximize": 3, "restore": 9}[args.action])
            info = self.info(args.hwnd)
            if args.action == "minimize" and not info["minimized"] or args.action == "maximize" and not info["maximized"] or args.action == "restore" and (info["minimized"] or info["maximized"]):
                raise ValueError("The requested window state was not observed")
        return success("Window action applied.", {"window": self.info(args.hwnd)}, "Window state re-read after user32 action")

    def keyboard(self, events):
        class Keyboard(ctypes.Structure):
            _fields_ = [("vk", wintypes.WORD), ("scan", wintypes.WORD), ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]
        class Mouse(ctypes.Structure):
            _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("data", wintypes.DWORD), ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]
        class Union(ctypes.Union):
            _fields_ = [("keyboard", Keyboard), ("mouse", Mouse)]
        class Input(ctypes.Structure):
            _fields_ = [("type", wintypes.DWORD), ("value", Union)]
        inputs = (Input * len(events))(*[Input(1, Union(keyboard=Keyboard(vk, scan, flags, 0, 0))) for vk, scan, flags in events])
        self.user.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(Input), ctypes.c_int]
        if self.user.SendInput(len(inputs), inputs, ctypes.sizeof(Input)) != len(inputs):
            raise ValueError("Windows blocked some input events")

    async def type_text(self, args):
        self.target(args, True)
        units = args.text.encode("utf-16-le")
        for start in range(0, len(units), 200):
            if self.user.GetForegroundWindow() != args.hwnd:
                raise ValueError("Focus changed; typing stopped")
            sequence = []
            for index in range(start, min(start + 200, len(units)), 2):
                code = int.from_bytes(units[index:index + 2], "little")
                sequence.extend([(0, code, 4), (0, code, 6)])
            self.keyboard(sequence)
            await asyncio.sleep(.01)
        return success("Text input was delivered.", {"characters": len(args.text), "window": self.info(args.hwnd)},
                       "Windows accepted all Unicode input events; inspect the destination to verify application content")

    def hotkey(self, args):
        self.target(args, True)
        codes = {"CTRL": 0x11, "ALT": 0x12, "SHIFT": 0x10, "WIN": 0x5b, "ENTER": 13, "ESC": 27,
                 "TAB": 9, "SPACE": 32, "BACKSPACE": 8, "DELETE": 46, "LEFT": 37, "UP": 38, "RIGHT": 39, "DOWN": 40,
                 **{chr(i): i for i in range(65, 91)}, **{str(i): 48+i for i in range(10)}}
        keys = [key.upper() for key in args.keys]
        if any(key not in codes for key in keys) or len(set(keys)) != len(keys):
            raise ValueError("Unsupported or duplicate hotkey")
        self.keyboard([(codes[key], 0, 0) for key in keys] + [(codes[key], 0, 2) for key in reversed(keys)])
        return success("Hotkey delivered.", {"keys": keys}, "Windows accepted the key events; inspect the application result")

    def click(self, args):
        info = self.target(args, True)
        bounds = info["bounds"]
        if not bounds["left"] <= args.x < bounds["right"] or not bounds["top"] <= args.y < bounds["bottom"]:
            raise ValueError("Click position is outside the target window")
        if not self.user.SetCursorPos(args.x, args.y):
            raise ValueError("Cursor could not be positioned")
        at_point = self.user.WindowFromPoint(wintypes.POINT(args.x, args.y))
        if self.user.GetAncestor(at_point, 2) != args.hwnd:
            raise ValueError("Another window covers the requested click position")
        down, up = (8, 16) if args.button == "right" else (2, 4)
        for _ in range(2 if args.button == "double" else 1):
            self.user.mouse_event(down, 0, 0, 0, 0)
            self.user.mouse_event(up, 0, 0, 0, 0)
        return success("Mouse input delivered.", {"x": args.x, "y": args.y, "window": self.info(args.hwnd)},
                       "Target bounds and foreground verified before sending mouse input; inspect the resulting UI")

    async def launch(self, args):
        self.require()
        system = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32"
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        local_app = Path(os.environ.get("LOCALAPPDATA", ""))
        choices = {
            "notepad": [system / "notepad.exe"],
            "calculator": [system / "calc.exe"],
            "explorer": [system.parent / "explorer.exe"],
            "edge": [program_files_x86 / "Microsoft/Edge/Application/msedge.exe", program_files / "Microsoft/Edge/Application/msedge.exe", local_app / "Microsoft/Edge/Application/msedge.exe"],
            "chrome": [program_files / "Google/Chrome/Application/chrome.exe", program_files_x86 / "Google/Chrome/Application/chrome.exe", local_app / "Google/Chrome/Application/chrome.exe"],
        }
        candidates = self.applications().data["applications"]
        executable = resolve_application(args.app, candidates, choices)
        if not executable.is_file():
            raise ValueError("This application is not installed at its registered location")
        process = await asyncio.create_subprocess_exec(str(executable), env=sanitized_environment(), creationflags=0x08000000 if os.name == "nt" else 0)
        await asyncio.sleep(.5)
        return success("Application launch requested.", {"pid": process.pid, "windows": self.windows().data["windows"]},
                       "Process creation succeeded and visible windows were re-enumerated; choose the matching window before interaction")

    def applications(self, _=None):
        self.require()
        import winreg
        found = {}
        views = [0]
        if hasattr(winreg, "KEY_WOW64_64KEY") and hasattr(winreg, "KEY_WOW64_32KEY"):
            views = [winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY]
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for view in views:
                try:
                    with winreg.OpenKey(hive, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths", 0, winreg.KEY_READ | view) as parent:
                        for i in range(min(500, winreg.QueryInfoKey(parent)[0])):
                            name = winreg.EnumKey(parent, i)
                            try:
                                with winreg.OpenKey(parent, name, 0, winreg.KEY_READ | view) as key:
                                    value = winreg.QueryValueEx(key, "")[0]
                                    path = Path(os.path.expandvars(value.strip('"')))
                                    if path.suffix.lower() == ".exe" and path.is_file():
                                        found[name.casefold()] = {"name":name, "path":str(path.resolve())}
                            except (OSError, TypeError):
                                continue
                except OSError:
                    continue
        return success("Application registrations read.", {"applications":list(found.values())}, "Read existing Windows App Paths registrations and verified executable paths")

    def clipboard(self, args=None):
        self.require()
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        for name, params, result in [
            ("GlobalAlloc",[wintypes.UINT,ctypes.c_size_t],wintypes.HGLOBAL), ("GlobalLock",[wintypes.HGLOBAL],ctypes.c_void_p),
            ("GlobalUnlock",[wintypes.HGLOBAL],wintypes.BOOL), ("GlobalFree",[wintypes.HGLOBAL],wintypes.HGLOBAL),
            ("GlobalSize",[wintypes.HGLOBAL],ctypes.c_size_t)]:
            function=getattr(kernel,name);function.argtypes, function.restype=params,result
        self.user.OpenClipboard.argtypes=[wintypes.HWND]
        self.user.GetClipboardData.argtypes=[wintypes.UINT];self.user.GetClipboardData.restype=wintypes.HANDLE
        self.user.SetClipboardData.argtypes=[wintypes.UINT,wintypes.HANDLE];self.user.SetClipboardData.restype=wintypes.HANDLE
        self.user.CreateWindowExW.argtypes=[wintypes.DWORD,wintypes.LPCWSTR,wintypes.LPCWSTR,wintypes.DWORD,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,wintypes.HWND,wintypes.HMENU,wintypes.HINSTANCE,ctypes.c_void_p]
        self.user.CreateWindowExW.restype=wintypes.HWND
        self.user.DestroyWindow.argtypes=[wintypes.HWND]
        owner=self.user.CreateWindowExW(0,"STATIC","Stonic clipboard",0,0,0,0,0,None,None,None,None)
        if not owner:
            raise ValueError("Clipboard owner window could not be created")
        opened=False
        try:
            if not self.user.OpenClipboard(owner):
                raise ValueError("Another application is using the clipboard; try again")
            opened=True
            if args is not None:
                raw=(args.text+"\0").encode("utf-16-le")
                handle=kernel.GlobalAlloc(0x0002,len(raw))
                if not handle:
                    raise MemoryError("Clipboard allocation failed")
                transferred=False
                try:
                    pointer=kernel.GlobalLock(handle)
                    if not pointer:
                        raise ValueError("Clipboard memory could not be locked")
                    ctypes.memmove(pointer,raw,len(raw));kernel.GlobalUnlock(handle)
                    if not self.user.EmptyClipboard() or not self.user.SetClipboardData(13,handle):
                        raise ValueError("Windows rejected the clipboard write")
                    transferred=True
                finally:
                    if not transferred:
                        kernel.GlobalFree(handle)
            handle=self.user.GetClipboardData(13)
            if not handle:
                return success("Clipboard has no Unicode text.", {"text":""}, "Windows returned no CF_UNICODETEXT data")
            size=kernel.GlobalSize(handle)
            if size>200002:
                raise ValueError("Clipboard text exceeds the 100,000 character limit")
            pointer=kernel.GlobalLock(handle)
            if not pointer:
                raise ValueError("Clipboard memory could not be read")
            try:
                text=ctypes.string_at(pointer,size).decode("utf-16-le",errors="replace").split("\0",1)[0]
            finally:
                kernel.GlobalUnlock(handle)
            if args is not None and text != args.text:
                raise ValueError("Clipboard readback did not match the requested text")
            return success("Clipboard text copied." if args is not None else "Clipboard text read.", {"characters":len(text)} if args is not None else {"text":text}, "Read back bounded CF_UNICODETEXT while owning the clipboard lock")
        finally:
            if opened:self.user.CloseClipboard()
            self.user.DestroyWindow(owner)

    def settings_page(self, args):
        self.require()
        os.startfile("ms-settings:" + args.page)
        return success("Windows settings page requested.", {"page":args.page}, "Windows accepted the fixed Settings URI; inspect the page before changing values")

    def register(self, registry):
        for name, description, arguments, level, run in [
            ("computer.windows", "Inspect visible window titles, handles, process ids and bounds", NoArguments, Level.SAFE, self.windows),
            ("computer.window", "Focus, minimize, maximize, restore or gracefully close an observed window", WindowAction, Level.SENSITIVE, self.action),
            ("computer.launch", "Launch a known installed desktop application without shell commands. Shortcuts: chrome, edge, notepad, calculator, explorer.", LaunchApp, Level.NORMAL, self.launch),
            ("computer.applications", "Inspect installed Windows application registrations", NoArguments, Level.SAFE, self.applications),
            ("computer.clipboard_read", "Read current clipboard text; it may contain private information", NoArguments, Level.SENSITIVE, lambda _: self.clipboard()),
            ("computer.clipboard_write", "Replace the clipboard with approved text and verify its contents", ClipboardText, Level.SENSITIVE, self.clipboard),
            ("computer.settings", "Open a known Windows settings page for inspection; does not change settings", SettingsPage, Level.NORMAL, self.settings_page),
            ("computer.type", "Type text into an observed window; requires exact current title and process id", TypeText, Level.SENSITIVE, self.type_text),
            ("computer.hotkey", "Send a bounded key combination to an observed target window", Hotkey, Level.SENSITIVE, self.hotkey),
            ("computer.click", "Click inside an observed target window using verified screen coordinates", MouseClick, Level.SENSITIVE, self.click),
        ]:
            registry.register(Tool(name, description, arguments, level, run, name == "computer.windows"))
