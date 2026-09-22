from pathlib import Path
from pydantic import Field
from stonic.core.models import Contract, PermissionLevel as Level, ActionResult
from stonic.tools.registry import Tool
from stonic.tools.workspace import success
from stonic.security.process import sanitized_environment


class GameQuery(Contract):
    query: str = Field(default="", max_length=200)


class GameLaunch(Contract):
    app_id: str = Field(pattern=r"^[0-9]{1,12}$")
    expected_name: str = Field(min_length=1, max_length=200)


class GamingMode(Contract):
    enabled: bool


class FpsSample(Contract):
    pid: int = Field(ge=1)
    expected_start_time: float = Field(gt=0)
    seconds: int = Field(default=5, ge=3, le=30)




def parse_vdf(text: str) -> dict:
    """Parse Steam's simple quoted-key/quoted-value VDF structures safely.

    Supports nested objects, quoted escape sequences, and ignores // comments.
    Repeated keys overwrite earlier entries, matching Steam's practical usage.
    """
    tokens=[]; i=0; n=len(text)
    while i<n:
        while i<n and text[i].isspace(): i+=1
        if i+1<n and text[i:i+2]=='//':
            i=text.find('\n',i+2)
            if i<0: break
            continue
        if i>=n: break
        if text[i] in '{}':
            tokens.append(text[i]); i+=1; continue
        if text[i] != '"':
            j=i
            while j<n and not text[j].isspace() and text[j] not in '{}': j+=1
            tokens.append(text[i:j]); i=j; continue
        i+=1; out=[]
        while i<n:
            c=text[i]
            if c=='"': i+=1; break
            if c=='\\' and i+1<n:
                out.append(text[i+1]); i+=2; continue
            out.append(c); i+=1
        tokens.append(''.join(out))
    def parse_obj(pos):
        obj={}
        while pos<len(tokens):
            tok=tokens[pos]
            if tok=='}': return obj,pos+1
            if tok=='{': pos+=1; continue
            key=tok; pos+=1
            if pos>=len(tokens): obj[key]=''; break
            value=tokens[pos]; pos+=1
            if value=='{': value,pos=parse_obj(pos)
            obj[key]=value
        return obj,pos
    result,_=parse_obj(0)
    return result


class Gaming:
    def __init__(self, computer, diagnostics):
        self.computer, self.diagnostics = computer, diagnostics

    def steam_root(self):
        import os
        if os.name != "nt":
            return None
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
                return Path(winreg.QueryValueEx(key, "SteamPath")[0])
        except OSError:
            return None

    def installed(self, args):
        root = self.steam_root()
        libraries = {root} if root else set()
        if root and (root / "steamapps/libraryfolders.vdf").is_file():
            contents = (root / "steamapps/libraryfolders.vdf").read_text(encoding="utf-8", errors="replace")
            parsed = parse_vdf(contents)
            libraries_node = parsed.get("libraryfolders", parsed) if isinstance(parsed, dict) else {}
            if isinstance(libraries_node, dict):
                for value in libraries_node.values():
                    if isinstance(value, dict) and isinstance(value.get("path"), str):
                        candidate = Path(value["path"])
                        if candidate.is_dir(): libraries.add(candidate)
        games = []
        for library in libraries:
            for manifest in (library / "steamapps").glob("appmanifest_*.acf"):
                if manifest.stat().st_size > 100000:
                    continue
                parsed = parse_vdf(manifest.read_text(encoding="utf-8", errors="replace"))
                values = parsed.get("AppState", parsed) if isinstance(parsed, dict) else {}
                if isinstance(values, dict) and values.get("appid", "").isdigit() and values.get("name") and args.query.casefold() in str(values["name"]).casefold():
                    install_dir = str(values.get("installdir", ""))
                    games.append({"app_id": str(values["appid"]), "name": str(values["name"]), "install_directory": str((library / "steamapps/common" / install_dir).resolve())})
        return success("Installed Steam library inspected.", {"games": games, "steam_installed": root is not None}, "Read installed Steam manifests; no game files modified")

    async def launch(self, args):
        import asyncio
        import os
        games = self.installed(GameQuery()).data["games"]
        if not any(g["app_id"] == args.app_id and g["name"] == args.expected_name for g in games):
            raise ValueError("Game no longer matches the installed library entry")
        executable = self.steam_root() / "steam.exe"
        if not executable.is_file():
            raise ValueError("Steam executable is unavailable")
        process = await asyncio.create_subprocess_exec(str(executable), "-applaunch", args.app_id,
            env=sanitized_environment(), creationflags=0x08000000 if os.name == "nt" else 0)
        await asyncio.sleep(.5)
        return success("Steam launch requested.", {"game": args.expected_name, "pid": process.pid}, "Installed app id was verified and Steam accepted process creation; game startup may take longer")

    def _fps_integration_valid(self):
        import hashlib, json
        directory = Path(__file__).resolve().parents[2] / "integrations/presentmon"
        manifest = directory / "manifest.json"
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            executable = (directory / data["executable"]).resolve()
            return executable.is_relative_to(directory.resolve()) and executable.is_file() and hashlib.sha256(executable.read_bytes()).hexdigest() == data.get("sha256")
        except (OSError, ValueError, KeyError, TypeError):
            return False

    def performance(self, _):
        import psutil
        root = self.steam_root()
        processes = []
        games = self.installed(GameQuery()).data["games"] if root else []
        for process in psutil.process_iter(["pid", "name", "exe", "memory_info"]):
            try:
                executable = process.info.get("exe")
                if executable and any(Path(executable).is_relative_to(g["install_directory"]) for g in games):
                    processes.append({"pid": process.pid, "name": process.info["name"], "start_time": process.create_time(), "memory_mb": round(process.info["memory_info"].rss / 1048576, 1)})
            except (OSError, psutil.Error, ValueError):
                continue
        return success("Game performance context sampled.", {"system": self.diagnostics.metrics(), "game_processes": processes,
            "gaming_mode": self.computer.config.values.gaming_mode,
            "fps_available": self._fps_integration_valid(),
            "fps": None, "fps_detail": "Select a running game to measure actual presentation intervals."}, "Matched running executables to installed game directories and sampled process memory")

    def mode(self, args):
        self.computer.config.update({"gaming_mode":args.enabled})
        return success("Gaming mode updated.", {"gaming_mode":args.enabled}, "Setting persisted; proactive notices are quiet while enabled")

    async def measure(self, args):
        import asyncio
        import csv
        import hashlib
        import json
        import math
        import os
        import tempfile
        from uuid import uuid4
        import psutil
        process = psutil.Process(args.pid)
        if abs(process.create_time() - args.expected_start_time) > .01:
            raise ValueError("Process changed; inspect the running application again")
        directory = Path(__file__).resolve().parents[2] / "integrations/presentmon"
        if not self._fps_integration_valid():
            return ActionResult(success=False,status="unavailable",message="Install or repair the verified PresentMon integration using Setup-Stonic.cmd before measuring FPS.")
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
        executable = (directory / manifest["executable"]).resolve()
        if not executable.is_relative_to(directory.resolve()) or hashlib.sha256(executable.read_bytes()).hexdigest() != manifest["sha256"]:
            raise ValueError("FPS reader changed; reinstall the verified integration")
        with tempfile.TemporaryDirectory(prefix="stonic-fps-") as temporary:
            output = Path(temporary) / "frames.csv"
            child = await asyncio.create_subprocess_exec(str(executable), "--process_id", str(args.pid), "--timed", str(args.seconds),
                "--terminate_after_timed", "--output_file", str(output), "--no_console_stats", "--v1_metrics", "--no_track_input",
                "--session_name", "Stonic-" + str(uuid4()), env=sanitized_environment(), stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                creationflags=0x08000000 if os.name == "nt" else 0)
            try:
                await asyncio.wait_for(child.wait(), args.seconds + 15)
            finally:
                if child.returncode is None:
                    child.kill()
                    await child.wait()
            if child.returncode != 0 or not output.is_file():
                return ActionResult(success=False,status="unavailable",message="Windows did not provide frame telemetry. Check ETW access and that the selected graphics application is running.")
            chains = {}
            with output.open(encoding="utf-8-sig",newline="") as source:
                for row in csv.DictReader(source):
                    try:
                        value = float(row["MsBetweenPresents"])
                        if int(row["ProcessID"]) == args.pid and math.isfinite(value) and 0 < value < 10000:
                            chains.setdefault(row.get("SwapChainAddress", "main"), []).append(value)
                    except (ValueError, KeyError):
                        continue
            intervals = max(chains.values(), key=len, default=[])
            if len(intervals) < 10:
                return ActionResult(success=False,status="unavailable",message="Too few presented frames were observed for a reliable FPS sample. Keep the game visible and try again.")
            slow = sorted(intervals,reverse=True)[:max(1, math.ceil(len(intervals)*.01))]
            return success("Frame presentation measured.", {"pid":args.pid, "frames":len(intervals), "fps":round(1000*len(intervals)/sum(intervals),1),
                "one_percent_low_fps":round(1000*len(slow)/sum(slow),1), "sample_seconds":args.seconds, "basis":"application presents from the busiest swap chain"},
                "PresentMon ETW samples from the observed process; temporary trace CSV removed")

    def register(self, registry):
        registry.register(Tool("gaming.library", "Find installed Steam games by name", GameQuery, Level.SAFE, self.installed, True))
        registry.register(Tool("gaming.launch", "Launch a verified installed Steam game by observed app id and name", GameLaunch, Level.NORMAL, self.launch))
        registry.register(Tool("gaming.performance", "Inspect running game processes and real system metrics; report FPS only when measured", GameQuery, Level.SAFE, self.performance, True))
        registry.register(Tool("gaming.mode", "Enable or disable quiet gaming mode without changing game files or system performance settings", GamingMode, Level.NORMAL, self.mode))
        registry.register(Tool("gaming.fps", "Measure real frame presentation for an observed process using PresentMon", FpsSample, Level.NORMAL, self.measure, timeout=50))
