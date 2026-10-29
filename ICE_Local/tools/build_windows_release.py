"""Build and check the portable Windows ZIP, including its nested Python ZIP."""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path


APP = Path(__file__).resolve().parents[1]
OUTPUT = APP.parent / 'output'
SKIP_DIRS = {'data', '__pycache__', '.venv', '.git', '.pytest_cache'}


def check_runtime(data: bytes) -> None:
    with zipfile.ZipFile(io.BytesIO(data)) as inner:
        if inner.testzip() is not None:
            raise ValueError('Bundled python312.zip has a damaged member')
        required = {'encodings/__init__.pyc', 'encodings/aliases.pyc', 'os.pyc'}
        missing = required.difference(inner.namelist())
        if missing:
            raise ValueError(f'Bundled Python standard library is incomplete: {sorted(missing)}')


def verify(path: Path) -> None:
    with zipfile.ZipFile(path) as outer:
        bad = outer.testzip()
        if bad is not None:
            raise ValueError(f'Windows archive has a damaged member: {bad}')
        required = {
            'START_ICE.cmd', 'READ_ME_FIRST.txt',
            'ICE_Local/START_WINDOWS.cmd', 'ICE_Local/app.py',
            'ICE_Local/runtime/python.exe', 'ICE_Local/runtime/python312.dll',
            'ICE_Local/runtime/python312.zip',
            'ICE_Local/runtime/Lib/site-packages/lxml/etree.cp312-win_amd64.pyd',
        }
        names = set(outer.namelist())
        missing = required.difference(names)
        if missing:
            raise ValueError(f'Windows archive is missing: {sorted(missing)}')
        if any(name.startswith('ICE_Local/data/') for name in names):
            raise ValueError('User data must not be included in a release')
        check_runtime(outer.read('ICE_Local/runtime/python312.zip'))
        print(f'OK: {path} ({len(names)} files; nested Python standard library intact)')


def build(path: Path) -> None:
    check_runtime((APP / 'runtime/python312.zip').read_bytes())
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name in ('START_ICE.cmd', 'READ_ME_FIRST.txt'):
            z.write(OUTPUT / name, name)
        for source in sorted(APP.rglob('*')):
            if not source.is_file() or any(part in SKIP_DIRS for part in source.relative_to(APP).parts):
                continue
            z.write(source, f'ICE_Local/{source.relative_to(APP).as_posix()}')
    verify(path)


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--verify':
        verify(Path(sys.argv[2]))
    else:
        build(Path(sys.argv[1]) if len(sys.argv) > 1 else OUTPUT / 'ICE_Local_Windows_v1.zip')
