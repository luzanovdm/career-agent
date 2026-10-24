"""Private current-user local control; never attach/kill using a PID or port alone."""
import json
import os
from pathlib import Path
import socket
import stat
import subprocess
import sys
import threading
import time
import webbrowser
from .contracts import CareerError, PROTOCOL, canonical, require
from .repository import Repository, contained, now


def run_directory(workspace):
    require(os.name=='posix','UNSUPPORTED_PLATFORM','Private Windows named-pipe control is not implemented')
    root=Path(workspace).absolute()
    run=contained(root,'.career-agent/run');run.mkdir(parents=True,exist_ok=True,mode=0o700)
    info=run.stat()
    require(info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700,'UNSAFE_CONTROL','Control directory must be current-user-only')
    return run


def control_path(workspace):
    """A short owner-only socket path supports arbitrarily long chosen workspace paths."""
    from .contracts import digest
    run_directory(workspace)
    base=Path('/tmp')/('career-agent-control-'+str(os.getuid()))
    require(not base.is_symlink(),'UNSAFE_CONTROL','Control root cannot be a symlink')
    base.mkdir(mode=0o700,exist_ok=True)
    info=base.stat()
    require(info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700,'UNSAFE_CONTROL','Control root must be owner-only')
    directory=contained(base,digest(str(Path(workspace).resolve()))[:32]);directory.mkdir(mode=0o700,exist_ok=True)
    info=directory.stat()
    require(info.st_uid==os.getuid() and stat.S_IMODE(info.st_mode)==0o700,'UNSAFE_CONTROL','Control namespace must be owner-only')
    return contained(directory,'control.sock')


def control(workspace,action):
    run=run_directory(workspace)
    path=control_path(workspace)
    if not path.exists():raise CareerError('NOT_RUNNING','Local application is not running',404)
    require(stat.S_ISSOCK(path.stat().st_mode) and path.stat().st_uid==os.getuid() and stat.S_IMODE(path.stat().st_mode)==0o600,
            'UNSAFE_CONTROL','Control socket must be owner-only')
    client=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);client.settimeout(3)
    try:
        client.connect(str(path));client.sendall((canonical(dict(action=action))+'\n').encode())
        content=client.recv(8192)
        require(bool(content),'NOT_RUNNING','Control process is stopping or unavailable',404)
        result=json.loads(content)
        require(result.get('protocol')==PROTOCOL,'UNRELATED_PROCESS','Local process protocol mismatch')
        with Repository(workspace).open() as snapshot:require(result.get('workspace_id')==snapshot.workspace_id,'UNRELATED_PROCESS','Local process workspace mismatch')
        return result
    except (ConnectionRefusedError,ConnectionResetError,FileNotFoundError):raise CareerError('NOT_RUNNING','No healthy local control process',404)
    finally:client.close()


def development_snapshot(workspace):
    """Pin code and assets together before a development child process imports them."""
    from .contracts import digest
    import shutil
    source_assets=Path(os.environ['CAREER_AGENT_DEVELOPMENT_ASSETS']).absolute() if os.environ.get('CAREER_AGENT_DEVELOPMENT_ASSETS') else Path(__file__).resolve().parents[2]/'ui/dist'
    require((source_assets/'index.html').is_file(),'UI_BUILD_REQUIRED','Build the UI before opening development preview')
    source_backend=Path(__file__).parent
    ui_files={str(p.relative_to(source_assets)):digest(p.read_bytes()) for p in source_assets.rglob('*') if p.is_file()}
    backend_files={p.name:digest(p.read_bytes()) for p in source_backend.iterdir() if p.is_file() and p.suffix in ('.py','.sql','.json')}
    release_id='development-'+digest(dict(ui=ui_files,backend=backend_files))[:16]
    snapshot=contained(Path(workspace),'.career-agent/staging/'+release_id)
    if not snapshot.exists():
        snapshot.mkdir(mode=0o700,parents=True)
        shutil.copytree(source_assets,snapshot/'ui')
        (snapshot/'runtime/career').mkdir(parents=True)
        for name in backend_files:shutil.copyfile(source_backend/name,snapshot/'runtime/career'/name)
        (snapshot/'entry.py').write_text("import pathlib,sys\nsys.dont_write_bytecode=True\nsys.path.insert(0,str(pathlib.Path(__file__).resolve().parent/'runtime'))\nfrom career.cli import main\nraise SystemExit(main())\n")
        (snapshot/'DEV.json').write_text(canonical(dict(release_id=release_id,ui=ui_files,backend=backend_files)))
    for name,sha in ui_files.items():require(digest(contained(snapshot/'ui',name).read_bytes())==sha,'DEVELOPMENT_CHANGED','Pinned UI bytes changed')
    for name,sha in backend_files.items():require(digest(contained(snapshot/'runtime/career',name).read_bytes())==sha,'DEVELOPMENT_CHANGED','Pinned backend bytes changed')
    return snapshot,dict(release_id=release_id,ui=ui_files,backend=backend_files)


def serve(workspace):
    from .server import LocalServer
    run=run_directory(workspace)
    # Advisory flock lives outside business transactions; never delete a live lock.
    import fcntl
    lock=open(contained(run,'server.lock'),'a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise CareerError('BUSY','A cooperating application process already owns this workspace',503)
    active=contained(Path(workspace),'.career-agent/active.json')
    hashes={}
    if active.exists():
        from .installation import verified_active
        release,manifest=verified_active(workspace)
        assets=release/'ui';hashes={key[3:]:value['sha256'] for key,value in manifest['files'].items() if key.startswith('ui/')}
        release_id=manifest['release_id']
    else:
        require(os.environ.get('CAREER_AGENT_DEVELOPMENT')=='1','INSTALLED_COPY_REQUIRED','Install a verified release before opening the application')
        pinned=os.environ.get('CAREER_AGENT_DEVELOPMENT_SNAPSHOT')
        if pinned:
            snapshot=Path(pinned).absolute()
            require(snapshot.resolve().is_relative_to(contained(Path(workspace),'.career-agent/staging').resolve()),'UNSAFE_PATH','Development snapshot must belong to workspace')
            metadata=json.loads((snapshot/'DEV.json').read_text())
            require(Path(__file__).resolve()==(snapshot/'runtime/career/lifecycle.py').resolve(),'DEVELOPMENT_CHANGED','Backend is not running from pinned snapshot')
            assets=snapshot/'ui';hashes=metadata['ui'];release_id=metadata['release_id']
        else:
            snapshot,metadata=development_snapshot(workspace);assets=snapshot/'ui';hashes=metadata['ui'];release_id=metadata['release_id']
    server=LocalServer(workspace,assets,hashes)
    path=control_path(workspace)
    if path.exists():
        require(stat.S_ISSOCK(path.stat().st_mode) and path.stat().st_uid==os.getuid(),'UNSAFE_CONTROL','Unknown socket path preserved')
        path.unlink()
    listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);listener.bind(str(path));os.chmod(path,0o600);listener.listen(4);listener.settimeout(.5)
    context=server.tasks.context()
    descriptor=dict(protocol=PROTOCOL,workspace_id=context['workspace_id'],run_id=server.run_id,port=server.server_port,pid=os.getpid(),started_at=now(),release_id=release_id)
    descriptor_path=contained(run,'process.json');descriptor_path.write_text(canonical(descriptor));os.chmod(descriptor_path,0o600)
    def accept_control():
        while not server.shutdown_event.is_set():
            try:client,_=listener.accept()
            except socket.timeout:continue
            except OSError:return
            with client:
                client.settimeout(2)
                try:
                    request=json.loads(client.recv(4096));action=request.get('action')
                    require(set(request)=={'action'} and action in ('status','mint-open','stop'),'INVALID_CONTROL','Unknown control action')
                    payload=dict(descriptor,status='running')
                    if action=='mint-open':payload['url']=server.mint()
                    client.sendall(canonical(payload).encode())
                    if action=='stop':server.stop()
                except (CareerError,ValueError,OSError):continue
    threading.Thread(target=accept_control,daemon=True).start()
    try:server.serve_forever(poll_interval=.2)
    finally:
        server.server_close();listener.close();path.unlink(missing_ok=True);descriptor_path.unlink(missing_ok=True);lock.close()
    return dict(status='stopped')


def process_lock_free(workspace):
    import fcntl
    run=run_directory(workspace)
    with contained(run,'server.lock').open('a') as lock:
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return False
        fcntl.flock(lock,fcntl.LOCK_UN);return True


def ui_command(workspace,action,open_browser=True):
    if action=='serve':return serve(workspace)
    try:running=control(workspace,'status')
    except CareerError as error:
        if error.code!='NOT_RUNNING':raise
        running=None
    if running and action not in ('stop','restart') and contained(Path(workspace),'.career-agent/active.json').exists():
        from .installation import active_record
        require(running['release_id']==active_record(workspace)['release_id'],'RUNTIME_MISMATCH','Restart to use the active installed release',409)
    if action=='status':return running or dict(status='stopped')
    if action in ('stop','restart') and running:
        control(workspace,'stop')
        for _ in range(60):
            try:control(workspace,'status')
            except CareerError as error:
                if error.code=='NOT_RUNNING' and process_lock_free(workspace):break
                if error.code=='NOT_RUNNING':time.sleep(.1);continue
                raise
            time.sleep(.1)
        else:raise CareerError('BUSY','Local process is still stopping',503)
        running=None
    if action=='stop':return dict(status='stopped')
    if not running:
        launcher=Path(sys.argv[0]).absolute();environment=dict(os.environ)
        if not contained(Path(workspace),'.career-agent/active.json').exists():
            require(os.environ.get('CAREER_AGENT_DEVELOPMENT')=='1','INSTALLED_COPY_REQUIRED','Install a verified release before application work')
            snapshot,_=development_snapshot(workspace);launcher=snapshot/'entry.py';environment['CAREER_AGENT_DEVELOPMENT_SNAPSHOT']=str(snapshot)
        command=[sys.executable,'-I','-B',str(launcher),'--workspace',str(Path(workspace).absolute()),'ui','serve']
        subprocess.Popen(command,env=environment,stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        for _ in range(50):
            try:running=control(workspace,'status');break
            except CareerError as error:
                if error.code!='NOT_RUNNING':raise
            time.sleep(.1)
        require(running,'START_FAILED','Installed application did not become healthy')
    result=control(workspace,'mint-open')
    if open_browser:webbrowser.open(result['url'])
    return result
