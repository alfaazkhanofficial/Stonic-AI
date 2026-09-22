import asyncio,hashlib,json,os,shutil,time
from pathlib import Path
from typing import Literal
from uuid import uuid4
from pydantic import Field
from stonic.core.models import ActionResult,Contract,PermissionLevel as Level
from stonic.tools.registry import Tool
from stonic.security.process import sanitized_environment
class FilePath(Contract):path:str=Field(max_length=1000)
class FileWrite(FilePath):content:str=Field(max_length=200000);expected_sha256:str|None=Field(default=None,pattern=r"^[a-f0-9]{64}$")
class FileMove(FilePath):destination:str=Field(max_length=1000)
class FileSearch(Contract):query:str=Field(min_length=1,max_length=200);path:str="."
class DeveloperRun(Contract):path:str=".";command:Literal["python_tests","npm_tests","npm_build","git_status","git_diff"]
class RecoveryItem(Contract):id:str=Field(pattern=r"^[a-f0-9]{32}$")
def success(message,data,verification):return ActionResult(success=True,status="completed",message=message,data=data,verification=verification)
class WorkspaceTools:
    RECOVERY_DEFAULT_RETENTION_DAYS=30
    def __init__(self,config,data_dir):
        self.config,self.data_dir=config,Path(data_dir);(self.data_dir/"documents").mkdir(parents=True,exist_ok=True);self.recovery_dir=self.data_dir/"recovery";self.recovery_dir.mkdir(parents=True,exist_ok=True);self.cleanup_recovery()
    def prepare(self,args):
        values=args.model_dump()
        for field in ("path","destination"):
            if field in values:values[field]=str(self.resolve(values[field],False))
        return type(args).model_validate(values)
    @property
    def root(self):return Path(self.config.values.workspace_root or self.data_dir/"documents").resolve()
    def resolve(self,path,must_exist=True):
        root=self.root;root.mkdir(parents=True,exist_ok=True);candidate=(root/path).resolve()
        if not candidate.is_relative_to(root):raise ValueError("Path is outside the configured workspace")
        relative=candidate.relative_to(root);excluded={".git",".venv","node_modules","__pycache__",".ssh",".aws"}
        if any(p.lower() in excluded or p.lower().startswith(".env") or p.lower().startswith("credentials.") for p in relative.parts):raise ValueError("Private or generated paths are excluded from workspace tools")
        if must_exist and not candidate.exists():raise ValueError("Path does not exist")
        return candidate
    def read(self,args):
        path=self.resolve(args.path)
        if not path.is_file() or path.stat().st_size>2000000:raise ValueError("Choose a text file no larger than 2 MB")
        raw=path.read_bytes();return success("File read.",{"path":str(path),"content":raw.decode("utf-8-sig"),"sha256":hashlib.sha256(raw).hexdigest()},"Read bytes from the resolved file")
    def tree(self,args):
        root=self.resolve(args.path)
        if not root.is_dir():raise ValueError("Choose a folder")
        entries=[]
        for path in sorted(root.iterdir(),key=lambda p:(p.is_file(),p.name.lower())):
            try:
                path=self.resolve(str(path));entries.append({"name":path.name,"path":str(path.relative_to(self.root)),"directory":path.is_dir(),"bytes":path.stat().st_size if path.is_file() else None})
            except (ValueError,OSError):continue
            if len(entries)>=500:break
        return success("Folder inspected.",{"entries":entries,"limit":500,"truncated":len(entries)>=500},"Directory entries read from disk")
    def write(self,args):
        path=self.resolve(args.path,False)
        if path.exists():
            if not path.is_file() or path.stat().st_size>2000000:raise ValueError("Choose a text file no larger than 2 MB")
            if args.expected_sha256 is None:raise ValueError("An expected SHA-256 is required before editing an existing file")
            if hashlib.sha256(path.read_bytes()).hexdigest()!=args.expected_sha256:raise ValueError("File changed; read it again before editing")
        elif args.expected_sha256 is not None:raise ValueError("Expected file no longer exists")
        path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_name(f".{path.name}.{uuid4().hex}.tmp")
        try:
            with temporary.open("w",encoding="utf-8",newline="") as handle:handle.write(args.content);handle.flush();os.fsync(handle.fileno())
            if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()!=args.expected_sha256:raise ValueError("File changed while the replacement was prepared")
            temporary.replace(path)
        finally:temporary.unlink(missing_ok=True)
        raw=path.read_bytes();return success("File saved.",{"path":str(path),"sha256":hashlib.sha256(raw).hexdigest()},"Re-read saved bytes and computed SHA-256")
    def move(self,args):
        source,target=self.resolve(args.path),self.resolve(args.destination,False)
        if not source.is_file() or target.exists():raise ValueError("Only a single file can be moved, and the destination must not exist")
        target.parent.mkdir(parents=True,exist_ok=True);source.rename(target)
        if source.exists() or not target.is_file():raise ValueError("Move verification failed")
        return success("File moved.",{"path":str(target)},"Source absent and destination exists")
    def _recovery_metadata(self,folder):
        try:
            value=json.loads((folder/"manifest.json").read_text(encoding="utf-8"));return value if isinstance(value,dict) else None
        except (OSError,ValueError):return None
    def cleanup_recovery(self):
        retention=getattr(self.config.values,"recovery_retention_days",self.RECOVERY_DEFAULT_RETENTION_DAYS);max_bytes=getattr(self.config.values,"recovery_max_mb",512)*1024*1024;now=time.time()
        folders=[p for p in self.recovery_dir.iterdir() if p.is_dir()]
        for folder in folders:
            try:expired=now-folder.stat().st_mtime>retention*86400
            except OSError:expired=True
            if expired:shutil.rmtree(folder,ignore_errors=True)
        folders=[p for p in self.recovery_dir.iterdir() if p.is_dir()];sizes=[];total=0
        for folder in folders:
            try:size=sum(item.stat().st_size for item in folder.rglob("*") if item.is_file())
            except OSError:size=0
            sizes.append((folder,size));total+=size
        for folder,size in sorted(sizes,key=lambda x:x[0].stat().st_mtime):
            if total<=max_bytes:break
            shutil.rmtree(folder,ignore_errors=True);total-=size
    def recovery_list(self,_=None):
        self.cleanup_recovery();items=[]
        for folder in sorted((p for p in self.recovery_dir.iterdir() if p.is_dir()),key=lambda p:p.stat().st_mtime,reverse=True):
            meta=self._recovery_metadata(folder)
            if meta:items.append(meta)
        return success("Recovery copies listed.",{"items":items[:200]},"Read only STONIC recovery metadata")
    def delete(self,args):
        path=self.resolve(args.path)
        if not path.is_file():raise ValueError("Only a single file can be deleted")
        max_bytes=getattr(self.config.values,"recovery_max_mb",512)*1024*1024
        if path.stat().st_size>max_bytes:raise ValueError("This file is larger than the configured recovery limit; increase the recovery limit before deleting it")
        recovery_id=uuid4().hex;folder=self.recovery_dir/recovery_id;folder.mkdir(parents=True);recovery_copy=folder/path.name
        try:
            shutil.copy2(path,recovery_copy);metadata={"id":recovery_id,"name":path.name,"original_path":str(path),"original_relative":str(path.relative_to(self.root)),"created_at":__import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),"bytes":recovery_copy.stat().st_size};(folder/"manifest.json").write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding="utf-8");path.unlink()
        except Exception:shutil.rmtree(folder,ignore_errors=True);raise
        self.cleanup_recovery()
        if path.exists() or not recovery_copy.exists():raise ValueError("Delete verification failed")
        return success("File removed; a bounded recovery copy was retained.",{"recovery_id":recovery_id,"recovery_path":str(recovery_copy),"original_path":str(path)},"Original is absent and the recovery copy plus manifest exist")
    def restore(self,args):
        self.cleanup_recovery();folder=self.recovery_dir/args.id;metadata=self._recovery_metadata(folder)
        if not metadata:raise ValueError("Recovery item does not exist or is invalid")
        target=self.resolve(metadata.get("original_relative",""),False);source=folder/str(metadata.get("name",""))
        if not source.is_file():raise ValueError("Recovery copy is missing")
        if target.exists():raise ValueError("The original path already exists; no file was overwritten")
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest()!=hashlib.sha256(source.read_bytes()).hexdigest():target.unlink(missing_ok=True);raise ValueError("Recovery restore verification failed")
        shutil.rmtree(folder,ignore_errors=True);return success("Recovery copy restored.",{"path":str(target)},"Restored bytes match the retained recovery copy")
    def purge(self,args):
        folder=self.recovery_dir/args.id
        if not self._recovery_metadata(folder):raise ValueError("Recovery item does not exist")
        shutil.rmtree(folder)
        if folder.exists():raise ValueError("Recovery copy could not be permanently removed")
        return success("Recovery copy permanently removed from the filesystem.",{"id":args.id},"Recovery folder no longer exists")
    async def search(self,args):
        root=self.resolve(args.path);results=[];inspected=0
        for base,directories,files in os.walk(root):
            directories[:]=[d for d in directories if not d.startswith(".") and d not in {"node_modules","__pycache__","dist"}]
            for name in files:
                inspected+=1
                try:
                    path=self.resolve(str(Path(base)/name))
                    if path.stat().st_size>300000:continue
                    for number,line in enumerate(path.read_text(encoding="utf-8").splitlines(),1):
                        if args.query.casefold() in line.casefold():
                            results.append({"path":str(path.relative_to(self.root)),"line":number,"text":line[:500]})
                            if len(results)>=80:return success("Workspace search completed at its result limit.",{"matches":results,"truncated":True,"inspected":inspected},"Matched actual UTF-8 file lines")
                except (OSError,ValueError,UnicodeError):continue
                await asyncio.sleep(0)
        return success("Workspace search completed.",{"matches":results,"truncated":False,"inspected":inspected},"Matched actual UTF-8 file lines")
    async def run(self,args):
        import shutil,sys
        path=self.resolve(args.path);npm=shutil.which("npm.cmd") or shutil.which("npm") or "npm"
        commands={"python_tests":[sys.executable,"-m","pytest","-q"],"npm_tests":[npm,"run","test","--if-present"],"npm_build":[npm,"run","build"],"git_status":["git","status","--short"],"git_diff":["git","diff","--no-ext-diff"]};command=commands[args.command]
        if args.command.startswith("npm"):
            try:package=json.loads((path/"package.json").read_text(encoding="utf-8"))
            except (OSError,ValueError) as error:raise ValueError("This project has no readable package.json") from error
            required="test" if args.command=="npm_tests" else "build"
            if required not in package.get("scripts",{}):raise ValueError("This project has no matching script")
        process=await asyncio.create_subprocess_exec(*command,cwd=path,env=sanitized_environment(),stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT,creationflags=0x08000000 if os.name=="nt" else 0);output=bytearray()
        try:
            while chunk:=await process.stdout.read(4096):
                if len(output)<40000:output.extend(chunk[:40000-len(output)])
            await process.wait()
        except asyncio.CancelledError:
            if os.name=="nt":
                killer=await asyncio.create_subprocess_exec("taskkill","/PID",str(process.pid),"/T","/F",env=sanitized_environment(),stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL,creationflags=0x08000000);await killer.wait()
            elif process.returncode is None:process.kill()
            await process.wait();raise
        return ActionResult(success=process.returncode==0,status="completed" if process.returncode==0 else "failed",message=f"Command exited with code {process.returncode}.",data={"exit_code":process.returncode,"output":output.decode(errors="replace")},verification=f"Observed process exit code {process.returncode}")
    def register(self,registry):
        items=[("files.list","List a folder inside the configured workspace",FilePath,Level.SAFE,self.tree,True), ("files.read","Read a UTF-8 workspace file and its content hash",FilePath,Level.SAFE,self.read,True), ("files.search","Search workspace text and source files",FileSearch,Level.SAFE,self.search,True), ("files.write","Create or edit one workspace file; existing files require their current SHA-256",FileWrite,Level.SENSITIVE,self.write,False), ("files.move","Move one workspace file without overwriting",FileMove,Level.SENSITIVE,self.move,False), ("files.delete","Remove one workspace file while retaining a bounded recovery copy",FilePath,Level.SENSITIVE,self.delete,False), ("files.recovery.list","List retained deleted-file recovery copies",Contract,Level.SAFE,self.recovery_list,True), ("files.recovery.restore","Restore one retained deleted file without overwriting an existing path",RecoveryItem,Level.SENSITIVE,self.restore,False), ("files.recovery.purge","Permanently remove one retained deleted-file recovery copy",RecoveryItem,Level.SENSITIVE,self.purge,False), ("developer.run","Run a fixed project test/build or Git inspection command; project scripts execute code",DeveloperRun,Level.CRITICAL,self.run,False)]
        for name,desc,args,level,run,safe in items:registry.register(Tool(name,desc,args,level,run,safe,120 if name=="developer.run" else 30,self.prepare if name not in {"files.recovery.list"} else None))
