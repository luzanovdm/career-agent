"""Verified offline release installation. No network, data migration or global install."""
import json
import os
from pathlib import Path
import platform
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile
from .contracts import CareerError, VERSION, canonical, digest, require
from .repository import Repository, contained, now

RELEASE_FORMAT='career-agent.release/1'


def platform_key():
    os_name={'Darwin':'macos','Linux':'linux','Windows':'windows'}.get(platform.system())
    architecture={'arm64':'arm64','aarch64':'arm64','x86_64':'x86_64','AMD64':'x86_64'}.get(platform.machine())
    require(os_name and architecture,'UNSUPPORTED_PLATFORM','No declared portable runtime target')
    return os_name+'-'+architecture


def verify_release(root,expected_manifest=None):
    root=Path(root).absolute()
    manifest_path=contained(root,'RELEASE.json')
    body=manifest_path.read_bytes()
    if expected_manifest:require(digest(body)==expected_manifest,'RELEASE_CHANGED','Release manifest changed')
    manifest=json.loads(body)
    require(manifest['format']==RELEASE_FORMAT and isinstance(manifest['version'],str) and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?',manifest['version']) and 'career-agent.workspace/1' in manifest.get('workspace_formats',[]),'UNSUPPORTED_RELEASE','Unsupported release format/version')
    require(manifest['platform']['target']==platform_key(),'UNSUPPORTED_PLATFORM','Archive does not match this platform')
    require(len(manifest['files'])<=10000,'LIMIT_EXCEEDED','Release has too many files')
    actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() or p.is_symlink()}
    require(actual==set(manifest['files'])|{'RELEASE.json'},'RELEASE_CHANGED','Unexpected or missing managed files')
    for relative,record in manifest['files'].items():
        path=contained(root,relative)
        require(path.is_file() and path.stat().st_size==record['size'] and digest(path.read_bytes())==record['sha256'],
                'RELEASE_CHANGED','Managed release hash mismatch: '+relative)
    return manifest


def active_record(workspace):
    path=contained(Path(workspace),'.career-agent/active.json')
    require(path.is_file(),'NOT_INSTALLED','No installed release')
    return json.loads(path.read_text())


def verified_active(workspace):
    active=active_record(workspace)
    require(set(active)>= {'release_dir','manifest_sha256','version','release_id'},'INVALID_ACTIVE','Invalid installed code locator')
    relative=active['release_dir']
    require(relative.startswith('.career-agent/releases/'),'INVALID_ACTIVE','Active release must be installed within workspace')
    release=contained(Path(workspace),relative)
    manifest=verify_release(release,active['manifest_sha256'])
    require(manifest['release_id']==active['release_id'],'INVALID_ACTIVE','Release identity mismatch')
    return release,manifest


def atomic_json(path,value):
    temp=path.with_name(path.name+'.new')
    require(not temp.is_symlink(),'UNSAFE_PATH','Unsafe atomic locator')
    with temp.open('w') as stream:
        stream.write(canonical(value));stream.flush();os.fsync(stream.fileno())
    os.chmod(temp,0o600);os.replace(temp,path)


def install_archive(archive,workspace,expected_sha256,display_name=None,language='en',ui_locale='en'):
    """The bootstrap exception: verify everything before executing staged application code."""
    archive=Path(archive);root=Path(workspace).absolute()
    require(archive.is_file() and not archive.is_symlink(),'INVALID_ARCHIVE','Regular complete archive required')
    require(digest(archive.read_bytes())==expected_sha256,'ARCHIVE_HASH_MISMATCH','Approved archive digest does not match')
    report_path=contained(root,'Data/import-report.json')
    if report_path.exists():
        require(report_path.stat().st_size<=128*1024*1024,'IMPORT_REPORT_TOO_LARGE','Review the offline import report before activation')
        report=json.loads(report_path.read_text())
        require(report.get('format')=='career-agent.import/1' and report.get('strict_pass') is True and report.get('activation_allowed') is True and not report.get('quarantine') and report.get('doctor',{}).get('healthy') is True,'IMPORT_QUARANTINED','Offline import has unresolved records or failed integrity; destination remains unactivated',409)
    for name in ('.career-agent/staging','.career-agent/releases','.career-agent/run'):
        contained(root,name).mkdir(mode=0o700,parents=True,exist_ok=True)
    # Serialize bootstrap/update against other installers, independently of business transactions.
    require(os.name=='posix','UNSUPPORTED_PLATFORM','Private Windows process control has not passed acceptance')
    import fcntl
    lock=contained(root,'.career-agent/install.lock').open('a')
    try:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise CareerError('BUSY','Another installer owns this workspace',503)
        stage=contained(root,'.career-agent/staging/install-'+expected_sha256)
        journal_path=contained(root,'.career-agent/install-journal.json')
        def journal(step,**detail):atomic_json(journal_path,dict(archive_sha256=expected_sha256,stage=step,at=now(),**detail))
        journal('archive-verified')
        if stage.exists():
            # Retain interrupted extraction; verify complete content or preserve it under a distinct name.
            try:verify_release(stage)
            except (CareerError,OSError,ValueError):
                saved=stage.with_name(stage.name+'-preserved-'+str(os.getpid()));stage.rename(saved)
        if not stage.exists():
            stage.mkdir(mode=0o700)
            with zipfile.ZipFile(archive) as package:
                entries=package.infolist()
                require(len(entries)<=10000 and sum(i.file_size for i in entries)<=1024*1024*1024,'LIMIT_EXCEEDED','Archive exceeds installation bounds')
                seen=set()
                for entry in entries:
                    require(entry.filename not in seen,'INVALID_ARCHIVE','Duplicate archive entry');seen.add(entry.filename)
                    require(not entry.is_dir() and not stat.S_ISLNK(entry.external_attr>>16),'INVALID_ARCHIVE','Only regular allowlisted archive files accepted')
                    require(entry.filename=='RELEASE.json' or entry.filename.startswith(('runtime/','ui/','skill/','bin/','licenses/')),
                            'INVALID_ARCHIVE','Unknown release path')
                    target=contained(stage,entry.filename);target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
                    with package.open(entry) as incoming,target.open('xb') as outgoing:shutil.copyfileobj(incoming,outgoing,1024*1024)
                    os.chmod(target,0o700 if (entry.external_attr>>16)&0o111 else 0o600)
        manifest=verify_release(stage);journal('extracted-and-verified',release_id=manifest['release_id'])
        # Run only already verified staged executable; no system Python/package manager needed.
        python=contained(stage,manifest['python_executable'])
        check_script='import sqlite3,ssl,json,sys,pathlib,importlib,pkgutil; sys.path.insert(0,sys.argv[1]); import career; [importlib.import_module("career."+m.name) for m in pkgutil.iter_modules(career.__path__)]; c=sqlite3.connect(":memory:"); assert c.execute("select 1").fetchone()[0]==1; print(json.dumps({"sqlite":sqlite3.sqlite_version,"ssl":ssl.OPENSSL_VERSION,"application_imports":"passed"}))'
        check=subprocess.run([str(python),'-I','-B','-c',check_script,str(stage/'runtime')],capture_output=True,text=True,timeout=30)
        require(check.returncode==0,'SELF_CHECK_FAILED','Verified portable runtime self-check failed')
        journal('runtime-self-check-passed',self_check=json.loads(check.stdout))
        release_dir='.career-agent/releases/'+manifest['release_id'];release=contained(root,release_dir)
        if release.exists():
            verify_release(release,digest((stage/'RELEASE.json').read_bytes()))
        else:stage.rename(release)
        journal('promoted',runtime_installed=True,workspace_initialized=False)
        active_path=contained(root,'.career-agent/active.json')
        old=json.loads(active_path.read_text()) if active_path.exists() else None
        previous_path=contained(root,'.career-agent/previous.json')
        original_previous=json.loads(previous_path.read_text()) if previous_path.exists() else None
        locator=dict(release_dir=release_dir,manifest_sha256=digest((release/'RELEASE.json').read_bytes()),version=manifest['version'],release_id=manifest['release_id'])
        if old and old!=locator:
            old_release,old_manifest=verified_active(root)
            status_process=subprocess.run([str(old_release/old_manifest['python_executable']),'-I','-B',str(old_release/'bin/entry.py'),'--workspace',str(root),'ui','status'],capture_output=True,text=True,timeout=10)
            require(status_process.returncode==0,'RUNTIME_STATUS_UNKNOWN','Cannot verify old process status; preserve existing pointer',409)
            status=json.loads(status_process.stdout)
            require(status.get('status')=='stopped','RUNTIME_ACTIVE','Stop the application and preserve dirty edits before update',409)
            atomic_json(contained(root,'.career-agent/previous.json'),old)
        with Repository.code_switch(root):
            journal('switching',runtime_installed=True,workspace_initialized=(root/'Data/career.sqlite3').exists())
            atomic_json(active_path,locator)
        check_environment=dict(os.environ,CAREER_AGENT_BOOTSTRAP=manifest['release_id'])
        try:
            if (root/'Data/career.sqlite3').exists():
                checked=subprocess.run([str(release/manifest['python_executable']),'-I','-B',str(release/'bin/entry.py'),'--workspace',str(root),'context'],capture_output=True,text=True,timeout=30,env=check_environment)
                require(checked.returncode==0,'WORKSPACE_CHECK_FAILED','Installed runtime could not validate existing workspace; code pointer restored')
                current=json.loads(checked.stdout);initialized=dict(workspace_id=current['workspace_id'],revision=current['revision'],initialized=True,reused=True)
            elif (root/'Data/state.json').exists():
                journal('import-required',runtime_installed=True,workspace_initialized=False)
                return dict(runtime_installed=True,workspace_initialized=False,code='IMPORT_REQUIRED',release_id=manifest['release_id'])
            else:
                require(display_name,'PROFILE_REQUIRED','Runtime installed; supply display name to initialize workspace')
                # Initialization itself runs through the installed copy, not bootstrap's source modules.
                initialized_process=subprocess.run([str(release/manifest['python_executable']),'-I','-B',str(release/'bin/entry.py'),'--workspace',str(root),'init','--name',display_name,'--language',language,'--ui-locale',ui_locale],capture_output=True,text=True,timeout=30,env=check_environment)
                require(initialized_process.returncode==0,'INITIALIZATION_FAILED','Runtime installed but workspace initialization failed')
                initialized=json.loads(initialized_process.stdout)
        except Exception:
            if old:
                with Repository.code_switch(root):atomic_json(active_path,old)
                if original_previous:atomic_json(previous_path,original_previous)
                else:previous_path.unlink(missing_ok=True)
            journal('failed',runtime_installed=True,workspace_initialized=(root/'Data/career.sqlite3').exists(),previous_pointer_restored=bool(old))
            raise
        # Stable W launcher only resolves the installed release. Keep host-owned customizations separate.
        launcher=contained(root,'.career-agent/career')
        import shlex
        script = '#!/bin/sh\nset -eu\nW=$(CDPATH= cd -- "${0%/*}/.." && pwd)\nexec ' + shlex.quote(str(release/manifest['python_executable'])) + ' -I -B ' + shlex.quote(str(release/'bin/entry.py')) + ' --workspace "$W" "$@"\n' 
        launcher.write_text(script);os.chmod(launcher,0o700)
        journal('complete',runtime_installed=True,workspace_initialized=True)
        return dict(initialized,runtime_installed=True,workspace_initialized=True,release_id=manifest['release_id'],launcher=str(launcher))
    finally:lock.close()


def app_command(workspace,action):
    if action=='status':
        release,manifest=verified_active(workspace)
        return dict(runtime_installed=True,release_id=manifest['release_id'],release_path=str(release),version=manifest['version'],
                    workspace_initialized=(Path(workspace)/'Data/career.sqlite3').is_file(),platform=manifest['platform'])
    if action=='verify':
        release,manifest=verified_active(workspace)
        return dict(verified=True,release_id=manifest['release_id'],files=len(manifest['files']))
    if action=='rollback':
        from .lifecycle import control
        try:control(workspace,'status')
        except CareerError as error:require(error.code=='NOT_RUNNING',error.code,str(error))
        else:raise CareerError('RUNTIME_ACTIVE','Stop application before code rollback',409)
        previous=contained(Path(workspace),'.career-agent/previous.json')
        require(previous.exists(),'NO_PREVIOUS_RELEASE','No previous code locator')
        locator=json.loads(previous.read_text());verify_release(contained(Path(workspace),locator['release_dir']),locator['manifest_sha256'])
        active=active_record(workspace)
        with Repository.code_switch(workspace):atomic_json(contained(Path(workspace),'.career-agent/active.json'),locator)
        atomic_json(previous,active)
        return dict(rolled_back=True,release_id=locator['release_id'],database_migrated=False)
    raise CareerError('INVALID_ACTION','Unknown app action')
