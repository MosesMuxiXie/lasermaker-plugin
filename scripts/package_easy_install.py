"""Assemble integration releases without rebuilding or relabeling the core.

The base ZIP must match installer/manifest.json. Runtime and example payloads
are copied byte for byte; only explicitly listed integration files are overlaid.
"""
import argparse
import hashlib
import json
import subprocess
import zipfile
from pathlib import Path


def assemble_bundle(base_zip,source,output,manifest,entries):
    base_zip,source,output=map(lambda p:Path(p).resolve(),(base_zip,source,output))
    if output.exists():raise ValueError('NEW_OUTPUT_REQUIRED')
    if hashlib.sha256(base_zip.read_bytes()).hexdigest()!=manifest['sha256']:raise ValueError('BASE_CHECKSUM_MISMATCH')
    overlays={}
    for entry in entries:
        start=(source/entry).resolve()
        if not start.is_relative_to(source):raise ValueError('OVERLAY_OUTSIDE_SOURCE')
        if not start.exists():continue
        for p in ([start] if start.is_file() else sorted(start.rglob('*'))):
            if not p.is_file():continue
            if p.is_symlink():raise ValueError('SYMLINK_OVERLAY')
            relative=p.relative_to(source)
            if any(x in ('.git','node_modules','__pycache__') for x in relative.parts):continue
            overlays['lasermaker-agent/'+relative.as_posix()]=p.read_bytes()
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(base_zip) as original,zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as target:
        names=set()
        for info in original.infolist():
            relative=Path(info.filename)
            if relative.is_absolute() or '..' in relative.parts or relative.parts[0]!='lasermaker-agent':raise ValueError('UNSAFE_BASE_PATH')
            if info.filename in names:raise ValueError('DUPLICATE_BASE_ENTRY')
            names.add(info.filename)
            data=overlays.pop(info.filename,None)
            target.writestr(info.filename,data if data is not None else original.read(info.filename))
        for name,data in overlays.items():target.writestr(name,data)
    return {'integration_version':manifest['bundleVersion'],'core_version':manifest['coreVersion'],
            'base_archive_sha256':manifest['sha256'],'runtime_tree_sha256':manifest['runtimeTreeSha256'],
            'archive_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),'output':str(output)}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base-zip',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    root=Path(__file__).resolve().parents[1];manifest=json.loads((root/'installer/manifest.json').read_text(encoding='utf-8'))
    entries=json.loads(subprocess.check_output(['node','--input-type=module','-e',
        "import {overlayEntries} from './installer/core.mjs'; console.log(JSON.stringify(overlayEntries));"],cwd=root,text=True,encoding='utf-8'))
    print(json.dumps(assemble_bundle(a.base_zip,root,a.output,manifest,entries),ensure_ascii=False))
