"""Close only native verification processes using the isolated test data directory."""
from pathlib import Path
import psutil
root=Path(__file__).resolve().parents[1]
for process in psutil.process_iter(['pid','exe']):
    try:
        if not process.info['exe'] or Path(process.info['exe']).resolve()!=(root/'node_modules/electron/dist/electron.exe').resolve():continue
        data=Path(process.environ().get('STONIC_DATA_DIR','')).resolve()
        if not data.is_relative_to(root/'.runtime') or data.name!='desktop-test':continue
        for child in process.children(recursive=True):
            try:child.kill()
            except psutil.Error:pass
        process.kill()
        print('Closed isolated native-test process',process.pid)
    except (psutil.Error,OSError):pass
