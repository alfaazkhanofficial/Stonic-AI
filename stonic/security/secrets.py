"""Windows user-bound DPAPI storage for provider credentials."""
from __future__ import annotations
import ctypes,json,os
from ctypes import wintypes
from pathlib import Path
from urllib.parse import urlsplit
class Blob(ctypes.Structure): _fields_=[("size",wintypes.DWORD),("data",ctypes.POINTER(ctypes.c_ubyte))]
DEFAULT_ENDPOINT="https://api.xkiro.com/v1"
def canonical_endpoint(endpoint:str)->str:
    parts=urlsplit(endpoint)
    if parts.scheme not in {"http","https"} or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment: raise ValueError("Provider endpoint must be a clean HTTP or HTTPS URL")
    return endpoint.rstrip("/")
class SecretStore:
    FORMAT_VERSION=1
    def __init__(self,directory:Path): self.path=Path(directory)/"credentials.dpapi";self._cache={};self._cache_loaded=False
    @staticmethod
    def _crypt(raw:bytes,decrypt:bool=False)->bytes:
        if os.name!="nt": raise ValueError("Secure credential storage requires Windows DPAPI; use environment credentials on other systems.")
        buffer=ctypes.create_string_buffer(raw);source=Blob(len(raw),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)));target=Blob();crypt=ctypes.WinDLL("crypt32",use_last_error=True);kernel=ctypes.WinDLL("kernel32",use_last_error=True);kernel.LocalFree.argtypes=[ctypes.c_void_p]
        function=crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData;function.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,wintypes.DWORD,ctypes.POINTER(Blob)];function.restype=wintypes.BOOL
        if not function(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):raise OSError("Windows credential protection failed")
        try:return ctypes.string_at(target.data,target.size)
        finally:kernel.LocalFree(target.data)
    def _load(self):
        if self._cache_loaded:return dict(self._cache)
        values={}
        if self.path.is_file():
            plaintext=self._crypt(self.path.read_bytes(),decrypt=True)
            try:
                payload=json.loads(plaintext.decode("utf-8"));credentials=payload.get("credentials",{}) if isinstance(payload,dict) else {}
                if isinstance(credentials,dict):
                    for key,value in credentials.items():
                        if isinstance(value,str) and value:
                            try:values[canonical_endpoint(str(key))]=value
                            except ValueError:pass
            except (UnicodeDecodeError,json.JSONDecodeError,AttributeError,TypeError):
                try:legacy=plaintext.decode("utf-8").strip()
                except UnicodeDecodeError:legacy=""
                if legacy and not legacy.startswith("gsk_"):values[DEFAULT_ENDPOINT]=legacy
        self._cache,self._cache_loaded=values,True;return dict(values)
    def _write(self,credentials):
        payload=json.dumps({"version":self.FORMAT_VERSION,"credentials":credentials},separators=(",",":"),sort_keys=True).encode("utf-8");encrypted=self._crypt(payload);self.path.parent.mkdir(parents=True,exist_ok=True);temporary=self.path.with_suffix(".tmp")
        try:
            with temporary.open("wb") as handle:handle.write(encrypted);handle.flush();os.fsync(handle.fileno())
            temporary.replace(self.path)
            if self._crypt(self.path.read_bytes(),decrypt=True)!=payload:raise OSError("Windows credential verification failed")
        finally:temporary.unlink(missing_ok=True)
        self._cache=dict(credentials);self._cache_loaded=True
    def save(self,key:str,endpoint:str=DEFAULT_ENDPOINT):
        endpoint=canonical_endpoint(endpoint);key=key.strip()
        if not 10<=len(key)<=1024 or any(c.isspace() for c in key):raise ValueError("Enter a valid API key without spaces.")
        credentials=self._load();credentials[endpoint]=key;self._write(credentials)
    def delete(self,endpoint:str=DEFAULT_ENDPOINT):
        endpoint=canonical_endpoint(endpoint);credentials=self._load();credentials.pop(endpoint,None)
        if credentials:self._write(credentials)
        else:self.path.unlink(missing_ok=True);self._cache={};self._cache_loaded=True
    def key(self,endpoint:str)->str:
        endpoint=canonical_endpoint(endpoint)
        try:value=self._load().get(endpoint,"")
        except (OSError,ValueError,UnicodeError):value=""
        if value:return value
        if urlsplit(endpoint).hostname=="api.xkiro.com":return os.environ.get("XKIRO_API_KEY","")
        return os.environ.get("STONIC_LLM_API_KEY","")
    def configured(self,endpoint:str)->bool:
        try:return bool(self.key(endpoint))
        except (OSError,ValueError,UnicodeError):return False
