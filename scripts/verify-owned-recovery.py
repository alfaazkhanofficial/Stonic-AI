"""Terminate only a test Electron instance's directly owned Stonic backend."""
import sys
from pathlib import Path
import psutil

parent=psutil.Process(int(sys.argv[1]))
executable=Path(parent.exe()).resolve()
root=Path(__file__).resolve().parents[1]
assert executable == (root/'node_modules/electron/dist/electron.exe').resolve() or executable.is_relative_to(root/'release') and executable.name.lower()=='stonic.exe'
children=[]
for child in parent.children(recursive=False):
    command=child.cmdline()
    if 'stonic.app' in command and '-m' in command:
        environment=child.environ()
        data=Path(environment.get('STONIC_DATA_DIR','')).resolve()
        allowed=Path(__file__).resolve().parents[1]/'.runtime'
        assert data.is_relative_to(allowed.resolve()) and 'test' in data.name
        children.append(child)
assert len(children)==1,'Expected exactly one directly owned isolated test backend'
children[0].kill()
children[0].wait(10)
print('Stopped the isolated native-test backend to verify recovery.')
