#!/usr/bin/env python3
"""Build complete offline installed releases from pinned portable Python and prebuilt UI."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile
import tempfile
import zipfile
from career.contracts import VERSION, canonical, digest, require
from career.installation import RELEASE_FORMAT

SOURCE=Path(__file__).resolve().parents[1]
PINNED={
 'macos-arm64':dict(asset='cpython-3.13.17+20261021-aarch64-apple-darwin-install_only_stripped.tar.gz',sha256='8dc60610a82f1e73be7faf964383e02520f95f6e39592a5c37c3809f5a7b798e',minimum_os='11.0',python_executable='runtime/python/bin/python3',control_supported=True),
 'macos-x86_64':dict(asset='cpython-3.13.17+20261021-x86_64-apple-darwin-install_only_stripped.tar.gz',sha256='ce9c748c8f7525c0052247edb2435fdb1cac89c77e687e0e199eaf2b827668c2',minimum_os='10.15',python_executable='runtime/python/bin/python3',control_supported=True),
 'linux-x86_64':dict(asset='cpython-3.13.17+20261021-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz',sha256='f829adc9d888e76c8801b4799ed444188d35239fcae3a9808a99ec5cb0d8d92c',minimum_os='glibc 2.17',python_executable='runtime/python/bin/python3',control_supported=True),
 'windows-x86_64':dict(asset='cpython-3.13.17+20261021-x86_64-pc-windows-msvc-install_only_stripped.tar.gz',sha256='56cde3b1a1dcc36576753cb408ee0c3568d211baafa0eee40423adc147c480f2',minimum_os='Windows 10',python_executable='runtime/python/python.exe',control_supported=False),
}

ENTRY='''"""Installed-only dispatcher: verify active bytes before application imports."""
import hashlib,json,os,pathlib,sys
if sys.argv.count('--workspace')!=1:raise SystemExit('Exactly one installed workspace is required')
i=sys.argv.index('--workspace');root=pathlib.Path(sys.argv[i+1]).absolute()
a=json.loads((root/'.career-agent/active.json').read_text())
relative=pathlib.PurePosixPath(a['release_dir'])
if relative.is_absolute() or '..' in relative.parts or not str(relative).startswith('.career-agent/releases/'):raise SystemExit('Unsafe active release')
release=root.joinpath(*relative.parts)
if release.is_symlink():raise SystemExit('Symlink release refused')
raw=(release/'RELEASE.json').read_bytes()
if hashlib.sha256(raw).hexdigest()!=a['manifest_sha256']:raise SystemExit('Manifest changed')
m=json.loads(raw)
for name,record in m['files'].items():
 if not (name.startswith('runtime/career/') or name.startswith('bin/') or name=='runtime/career_bootstrap_entry.py'):continue
 p=release/name
 if p.is_symlink() or not p.resolve().is_relative_to(release.resolve()) or hashlib.sha256(p.read_bytes()).hexdigest()!=record['sha256']:raise SystemExit('Installed bytes changed')
python=release/m['python_executable']
if pathlib.Path(__file__).resolve()!= (release/'bin/entry.py').resolve():os.execv(str(python),[str(python),'-I','-B',str(release/'bin/entry.py'),*sys.argv[1:]])
sys.dont_write_bytecode=True
sys.path.insert(0,str(release/'runtime'))
from career.cli import main
raise SystemExit(main())
'''


def collect_ui_licenses(ui,root):
    """Inventory exact installed production dependency closure; build-time only."""
    build=ui.parent
    package=json.loads((build/'package.json').read_text())
    target=root/'licenses/ui';target.mkdir(parents=True)
    inventory={}
    def locate(name,start):
        current=start
        while current!=current.parent:
            candidate=current/'node_modules'/name
            if (candidate/'package.json').is_file():return candidate
            current=current.parent
        raise ValueError('Missing UI production dependency license source: '+name)
    def visit(name,start):
        path=locate(name,start);metadata=json.loads((path/'package.json').read_text());key=name+'@'+metadata['version']
        if key in inventory:return
        license_files=[p for p in path.iterdir() if p.is_file() and p.name.lower().startswith(('license','licence','notice','copying'))]
        if not license_files:
            override=SOURCE/'licenses/ui-overrides'/(name.replace('/','_')+'-'+metadata['version']+'-LICENSE')
            provenance=override.with_name(override.name.replace('-LICENSE','-provenance.json'))
            if override.is_file() and provenance.is_file():
                proof=json.loads(provenance.read_text());require(digest(override.read_bytes())==proof['sha256'],'LICENSE_CHANGED','Pinned license override changed');license_files=[override,provenance]
        require(license_files,'LICENSE_MISSING','UI dependency needs license text: '+key)
        directory=target/(name.replace('/','_')+'-'+metadata['version']);directory.mkdir()
        records=[]
        for source in license_files:
            content=source.read_bytes();(directory/source.name).write_bytes(content)
            records.append(dict(file=str((directory/source.name).relative_to(root)),sha256=digest(content)))
        inventory[key]=dict(package=name,version=metadata['version'],license=metadata.get('license'),files=records)
        for dependency in metadata.get('dependencies',{}):visit(dependency,path)
    for name in package['dependencies']:visit(name,build)
    (target/'inventory.json').write_text(canonical(inventory))
    return inventory


def build(runtime_archive,destination,target,ui=None):
    pin=PINNED[target];runtime_archive=Path(runtime_archive);destination=Path(destination)
    require(not destination.exists(),'ALREADY_EXISTS','Bundle destination must be absent')
    require(digest(runtime_archive.read_bytes())==pin['sha256'],'RUNTIME_HASH_MISMATCH','Portable Python differs from pinned upstream archive')
    ui=Path(ui or SOURCE/'ui/dist')
    require((ui/'index.html').is_file() and (ui/'assets').is_dir(),'UI_BUILD_REQUIRED','Build the actual React UI before packaging')
    with tempfile.TemporaryDirectory(prefix='career-release-build-') as temp:
        root=Path(temp)
        with tarfile.open(runtime_archive) as upstream:
            members={entry.name:entry for entry in upstream}
            for name,entry in members.items():
                relative=PurePosixPath(name)
                require(not relative.is_absolute() and '..' not in relative.parts and relative.parts[0]=='python','UNSAFE_RUNTIME','Unsafe upstream path')
                if entry.isdir():continue
                require(entry.isfile() or entry.issym() or entry.islnk(),'UNSAFE_RUNTIME','Unsupported upstream file')
                # Do not ship a package manager; app helpers use only the standard library.
                if '/site-packages/' in name or relative.name.startswith(('pip','idle','pydoc')):continue
                if target!='windows-x86_64' and name.startswith('python/bin/') and name!='python/bin/python3':continue
                source=entry
                visited=set()
                while source.issym() or source.islnk():
                    require(source.name not in visited,'UNSAFE_RUNTIME','Cyclic upstream link');visited.add(source.name)
                    link=str(PurePosixPath(source.name).parent/source.linkname) if source.issym() else source.linkname
                    parts=[]
                    for part in PurePosixPath(link).parts:
                        if part=='..':
                            require(bool(parts),'UNSAFE_RUNTIME','Upstream link escapes root');parts.pop()
                        elif part!='.':parts.append(part)
                    link='/'.join(parts);require(link in members and link.startswith('python/'),'UNSAFE_RUNTIME','Unresolved upstream link')
                    source=members[link]
                path=root/'runtime'/relative;path.parent.mkdir(parents=True,exist_ok=True)
                with upstream.extractfile(source) as incoming,path.open('wb') as outgoing:shutil.copyfileobj(incoming,outgoing)
                os.chmod(path,0o755 if entry.mode&0o111 or source.mode&0o111 else 0o644)
        shutil.copytree(SOURCE/'scripts/career',root/'runtime/career',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        input_ui_hashes={str(p.relative_to(ui)):digest(p.read_bytes()) for p in ui.rglob('*') if p.is_file()}
        shutil.copytree(ui,root/'ui')
        require(input_ui_hashes=={str(p.relative_to(root/'ui')):digest(p.read_bytes()) for p in (root/'ui').rglob('*') if p.is_file()},'UI_BUILD_CHANGED','UI build changed while packaging')
        require(input_ui_hashes=={str(p.relative_to(ui)):digest(p.read_bytes()) for p in ui.rglob('*') if p.is_file()},'UI_BUILD_CHANGED','UI build changed while packaging')
        (root/'skill/references').mkdir(parents=True)
        for name in ('SKILL.md','LICENSE'):shutil.copyfile(SOURCE/'skills/career-agent'/name,root/'skill'/name)
        for name in ('profile-tracks.md','search-contacts-packets.md','progress-history-recovery.md','interviews.md','interaction-capabilities.md','installation.md'):
            shutil.copyfile(SOURCE/'skills/career-agent/references'/name,root/'skill/references'/name)
        (root/'bin').mkdir();(root/'bin/entry.py').write_text(ENTRY)
        bootstrap="import pathlib,sys\nsys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'runtime'))\nfrom career_bootstrap_entry import main\nraise SystemExit(main())\n"
        (root/'bin/bootstrap.py').write_text(bootstrap)
        shutil.copyfile(SOURCE/'scripts/career_bootstrap.py',root/'runtime/career_bootstrap_entry.py')
        (root/'bin/career').write_text('#!/bin/sh\nset -eu\nR=$(CDPATH= cd -- "${0%/*}/.." && pwd)\nW=$(CDPATH= cd -- "$R/../../.." && pwd)\nexec "$R/runtime/python/bin/python3" -I -B "$R/bin/entry.py" --workspace "$W" "$@"\n')
        os.chmod(root/'bin/career',0o755)
        (root/'licenses').mkdir();shutil.copytree(SOURCE/'licenses/runtime-python-build-standalone-20261021',root/'licenses/python-build-standalone');shutil.copyfile(SOURCE/'LICENSE',root/'licenses/career-agent-MIT.txt')
        shutil.copyfile(root/'runtime/python/lib/python3.13/LICENSE.txt',root/'licenses/CPython.txt') if target!='windows-x86_64' else None
        ui_inventory=collect_ui_licenses(ui,root)
        license_files=[str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and ('license' in p.name.lower() or 'copying' in p.name.lower())]
        (root/'licenses/inventory.json').write_text(canonical(dict(application='MIT',python='CPython 3.13.17; see CPython.txt',runtime_upstream=pin['asset'],included_license_files=license_files,
            ui='See licenses/ui/inventory.json; exact installed production dependency closure, '+str(len(ui_inventory))+' packages.')))
        files={str(p.relative_to(root)):dict(sha256=digest(p.read_bytes()),size=p.stat().st_size,executable=bool(p.stat().st_mode&0o111)) for p in root.rglob('*') if p.is_file()}
        release_id=VERSION+'-'+target+'-'+digest(files)[:16]
        manifest=dict(format=RELEASE_FORMAT,version=VERSION,release_id=release_id,workspace_formats=['career-agent.workspace/1'],
            platform=dict(target=target,minimum_os=pin['minimum_os'],minimum_tested=False,control_supported=pin['control_supported']),
            python_executable=pin['python_executable'],ui_build=dict(files_sha256=digest(input_ui_hashes),package_lock_sha256=digest((ui.parent/'package-lock.json').read_bytes()),dependencies=json.loads((ui.parent/'package.json').read_text())['dependencies']),runtime_provenance=dict(project='astral-sh/python-build-standalone',release='20261021',python='3.13.17',asset=pin['asset'],sha256=pin['sha256'],url='https://github.com/astral-sh/python-build-standalone/releases/download/20261021/'+pin['asset']),files=files)
        (root/'RELEASE.json').write_text(canonical(manifest))
        with zipfile.ZipFile(destination,'x',zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for path in sorted(p for p in root.rglob('*') if p.is_file()):
                info=zipfile.ZipInfo(str(path.relative_to(root)),(1980,1,1,0,0,0));info.external_attr=(0o100755 if path.stat().st_mode&0o111 else 0o100644)<<16;info.compress_type=zipfile.ZIP_DEFLATED
                archive.writestr(info,path.read_bytes())
    return dict(archive=str(destination),sha256=digest(destination.read_bytes()),release_id=release_id,files=len(files),platform=manifest['platform'])


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--python-archive',required=True);parser.add_argument('--target',required=True,choices=PINNED);parser.add_argument('--ui');parser.add_argument('output');args=parser.parse_args()
    print(json.dumps(build(args.python_archive,args.output,args.target,args.ui),indent=2))

if __name__=='__main__':main()
