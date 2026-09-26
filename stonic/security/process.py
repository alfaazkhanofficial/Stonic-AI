"""Safe environment construction for child processes launched by STONIC."""
from __future__ import annotations
import os
SAFE_ENV_KEYS={"COMSPEC","HOMEDRIVE","HOMEPATH","LOCALAPPDATA","PROGRAMDATA","PROGRAMFILES","PROGRAMFILES(X86)","SYSTEMDRIVE","SYSTEMROOT","TEMP","TMP","USERPROFILE","WINDIR","PATH","PATHEXT","PSMODULEPATH","NUMBER_OF_PROCESSORS","PROCESSOR_ARCHITECTURE","PROCESSOR_IDENTIFIER","PROCESSOR_LEVEL","PROCESSOR_REVISION","OS","LANG","LC_ALL","LC_CTYPE","TZ"}
def sanitized_environment(*,extra:dict[str,str]|None=None)->dict[str,str]:
    result={}
    for key,value in os.environ.items():
        upper=key.upper()
        if upper in SAFE_ENV_KEYS and not any(token in upper for token in ("KEY","TOKEN","SECRET","PASSWORD","CREDENTIAL")):
            result[key]=value
    if extra:
        for key,value in extra.items():
            upper=key.upper()
            if not any(token in upper for token in ("KEY","TOKEN","SECRET","PASSWORD","CREDENTIAL")):
                result[key]=str(value)
    return result
