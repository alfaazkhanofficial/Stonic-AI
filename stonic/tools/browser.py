import asyncio,os,shutil,sys
from pathlib import Path
from pydantic import Field
from stonic.core.models import Contract,PermissionLevel as Level
from stonic.tools.registry import Tool
from stonic.tools.workspace import success
from stonic.security.process import sanitized_environment
from stonic.security.network import validate_http_url
class BrowserOpen(Contract):
    url:str=Field(min_length=8,max_length=4000)
class BrowserRef(Contract):
    ref:str=Field(pattern=r"^s\d+e\d+$");expected_url:str=Field(min_length=8,max_length=4000)
class BrowserFill(BrowserRef):text:str=Field(max_length=10000)
class BrowserTools:
    def __init__(self):self.process=None;self.lock=asyncio.Lock()
    async def _ensure(self):
        if self.process and self.process.returncode is None:return
        node=shutil.which("node") or (str(Path(__file__).resolve().parents[2]/"runtime/node/node.exe") if os.name=="nt" else "")
        if not node:raise ValueError("Node.js is required for owned browser tools")
        root=Path(__file__).resolve().parents[2];env=sanitized_environment(extra={"STONIC_BROWSER_HEADLESS":os.environ.get("STONIC_BROWSER_HEADLESS","0")})
        self.process=await asyncio.create_subprocess_exec(node,str(root/"scripts/browser-worker.mjs"),cwd=root,env=env,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,creationflags=0x08000000 if os.name=="nt" else 0)
    async def _call(self,payload):
        await self._ensure();self.process.stdin.write((__import__("json").dumps(payload)+"\n").encode());await self.process.stdin.drain()
        try:
            async with asyncio.timeout(30):line=await self.process.stdout.readline()
        except TimeoutError:raise ValueError("Owned browser did not respond within 30 seconds")
        if not line:raise ValueError("Owned browser process exited unexpectedly")
        result=__import__("json").loads(line)
        if not result.get("success"):raise ValueError(result.get("message","Browser action failed"))
        return result
    async def open(self,args):
        validate_http_url(args.url,resolve=False)
        async with self.lock:return success("Public web page opened in the owned browser.",(await self._call({"action":"open","url":args.url}))["data"],"Browser re-read the page after navigation")
    async def snapshot(self,_):
        async with self.lock:return success("Owned browser page inspected.",(await self._call({"action":"snapshot"}))["data"],"Browser returned the current URL, title, text and visible controls")
    async def click(self,args):
        async with self.lock:return success("Browser control completed.",(await self._call({"action":"click","ref":args.ref,"expected_url":args.expected_url}))["data"],"Browser re-read the page after the click")
    async def fill(self,args):
        async with self.lock:return success("Browser field updated.",(await self._call({"action":"fill","ref":args.ref,"expected_url":args.expected_url,"text":args.text}))["data"],"Browser re-read the page after the field update")
    async def close(self,_=None):
        async with self.lock:
            if self.process and self.process.returncode is None:
                try:await self._call({"action":"close"})
                except ValueError:pass
            if self.process and self.process.returncode is None:
                if os.name=="nt":
                    killer=await asyncio.create_subprocess_exec("taskkill","/PID",str(self.process.pid),"/T","/F",env=sanitized_environment(),stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL,creationflags=0x08000000);await killer.wait()
                else:self.process.kill()
            self.process=None
    def register(self,registry):
        registry.register(Tool("browser.open","Open a public HTTP/HTTPS page in STONIC's owned browser",BrowserOpen,Level.NORMAL,self.open,False,35))
        registry.register(Tool("browser.snapshot","Inspect the current owned browser page and visible controls",Contract,Level.SAFE,self.snapshot,True,35))
        registry.register(Tool("browser.click","Click a visible inspected browser control only if the page identity is unchanged",BrowserRef,Level.NORMAL,self.click,False,35))
        registry.register(Tool("browser.fill","Fill an inspected non-password browser field",BrowserFill,Level.NORMAL,self.fill,False,35))
        registry.register(Tool("browser.close","Close the owned browser session",Contract,Level.SAFE,self.close,True,20))
