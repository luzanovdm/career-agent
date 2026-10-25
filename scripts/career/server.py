"""Bounded loopback HTTP adapter; domain mutations go through Tasks only."""
from concurrent.futures import ThreadPoolExecutor
from http import cookies
from http.server import BaseHTTPRequestHandler, HTTPServer
from logging.handlers import RotatingFileHandler
import json
import gzip
import re
import logging
import mimetypes
import os
from pathlib import Path
import queue
import secrets
import socket
import threading
import time
from urllib.parse import parse_qs, urlsplit, unquote
from .contracts import CareerError, PROTOCOL, canonical, require
from .facade import Tasks
from .repository import contained, digest, new_id

CSP = "default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'self'; style-src-attr 'unsafe-inline'; img-src 'self' data:; font-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"


class LocalServer(HTTPServer):
    allow_reuse_address=False
    request_queue_size=16

    def __init__(self,workspace,assets,asset_hashes=None,port=0):
        self.tasks=Tasks(workspace)
        self.tasks.repository.ensure_projection_cache()
        self.assets=Path(assets).absolute()
        self.asset_hashes=asset_hashes or {}
        self.sessions={};self.capabilities={};self.listeners=set()
        self.lock=threading.Lock();self.shutdown_event=threading.Event()
        self.run_id=new_id('run');self.control_socket=None
        self.executor=ThreadPoolExecutor(max_workers=16,thread_name_prefix='career-http')
        self.slots=threading.BoundedSemaphore(16)
        self.stream_slots=threading.BoundedSemaphore(8)
        self.static_cache={}
        logs=contained(self.tasks.repository.root,'.career-agent/logs')
        logs.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.logger=logging.getLogger('career.'+self.run_id);self.logger.setLevel(logging.INFO)
        handler=RotatingFileHandler(logs/'http.log',maxBytes=1024*1024,backupCount=2)
        os.chmod(logs/'http.log',0o600)
        handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'));self.logger.addHandler(handler)
        super().__init__(('127.0.0.1',port),Handler)
        self.origin='http://127.0.0.1:'+str(self.server_port)
        self.dispatcher=threading.Thread(target=self.dispatch_changes,daemon=True)
        self.dispatcher.start()

    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):
            try:request.sendall(b'HTTP/1.1 503 Busy\r\nConnection: close\r\nContent-Length: 0\r\n\r\n')
            finally:request.close()
            return
        self.executor.submit(self.run_request,request,address)

    def run_request(self,request,address):
        try:self.finish_request(request,address)
        except (OSError,ValueError):pass
        finally:self.shutdown_request(request);self.slots.release()

    def mint(self):
        capability=secrets.token_urlsafe(32)
        with self.lock:
            self.capabilities={key:expiry for key,expiry in self.capabilities.items() if expiry>time.monotonic()}
            require(len(self.capabilities)<32,'BUSY','Too many outstanding launches',503)
            self.capabilities[capability]=time.monotonic()+60
        return self.origin+'/#launch='+capability

    def dispatch_changes(self):
        cursor=self.tasks.context()['revision'];integrity_token=None
        while not self.shutdown_event.wait(.25):
            try:
                if not self.tasks.repository.database.is_file():self.stop();return
                refreshed=self.tasks.repository.ensure_projection_cache()
                changes=self.tasks.query('changes',after=cursor)
                if refreshed:
                    with self.lock:
                        for listener in self.listeners:
                            try:listener.put_nowait(('resync',dict(revision=changes['revision'],workspace_id=changes['workspace_id'])))
                            except queue.Full:pass
                if changes.get('integrity_token')!=integrity_token:
                    if integrity_token is not None or changes.get('integrity_token'):
                        with self.lock:
                            for listener in self.listeners:
                                try:listener.put_nowait(('resync',dict(revision=changes['revision'],workspace_id=changes['workspace_id'])))
                                except queue.Full:pass
                    integrity_token=changes.get('integrity_token')
                if changes.get('replay_gap',changes['resync_required']):
                    with self.lock:
                        for listener in self.listeners:
                            try:listener.put_nowait(('resync',dict(revision=changes['revision'],workspace_id=changes['workspace_id'])))
                            except queue.Full:pass
                    cursor=changes['revision'];continue
                for change in changes['changes']:
                    change['workspace_id']=changes['workspace_id']
                    with self.lock:
                        for listener in list(self.listeners):
                            try:listener.put_nowait(('change',change))
                            except queue.Full:
                                while not listener.empty():
                                    try:listener.get_nowait()
                                    except queue.Empty:break
                                listener.put_nowait(('resync',dict(revision=changes['revision'],workspace_id=changes['workspace_id'])))
                    cursor=change['cursor']
            except (CareerError,OSError):
                continue

    def stop(self):
        self.shutdown_event.set()
        with self.lock:
            for listener in self.listeners:
                try:listener.put_nowait(('stop',{}))
                except queue.Full:pass
        threading.Thread(target=self.shutdown,daemon=True).start()

    def server_close(self):
        self.shutdown_event.set()
        super().server_close()
        self.executor.shutdown(wait=True,cancel_futures=True)
        for handler in list(self.logger.handlers):handler.close();self.logger.removeHandler(handler)


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    server_version='CareerAgent'
    sys_version=''

    def setup(self):
        super().setup();self.connection.settimeout(10)

    def log_message(self,*args):
        # Never log request URLs, bodies, capabilities, record IDs or raw filenames.
        pass

    def do_GET(self):self.dispatch()
    def do_POST(self):self.dispatch()
    def do_OPTIONS(self):self.send_error(405)

    def send_error(self,code,message=None,explain=None):
        self.reply(code,{'error':{'code':'HTTP_ERROR','message':'Request rejected','issues':[]}})

    def reply(self,status,payload,media='application/json',extra=None):
        body=canonical(payload).encode() if media=='application/json' and not isinstance(payload,bytes) else payload
        self.send_response(status)
        self.send_header('Content-Type',media)
        self.send_header('Content-Length',str(len(body)))
        self.security_headers(cache_control=(extra or {}).get('Cache-Control','private, no-store'))
        if extra:
            for key,value in extra.items():
                if key!='Cache-Control':self.send_header(key,value)
        self.send_header('Connection','close');self.end_headers()
        try:self.wfile.write(body)
        except (BrokenPipeError,ConnectionResetError):pass
        self.close_connection=True

    def security_headers(self,cache_control='private, no-store'):
        self.send_header('Content-Security-Policy',CSP)
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Frame-Options','DENY')
        self.send_header('Cache-Control',cache_control)

    def session(self):
        jar=cookies.SimpleCookie()
        try:jar.load(self.headers.get('Cookie',''))
        except cookies.CookieError:return None
        token=jar.get('career_session')
        return self.server.sessions.get(token.value) if token else None

    def body(self,maximum=1024*1024,json_body=True):
        require(not self.headers.get('Transfer-Encoding') and len(self.headers.get_all('Content-Length',[]))==1,
                'INVALID_BODY','Exactly one Content-Length and no Transfer-Encoding required',400)
        raw=self.headers['Content-Length']
        require(raw.isdigit(),'INVALID_BODY','Invalid Content-Length',400)
        length=int(raw);require(length<=maximum,'LIMIT_EXCEEDED','Request body too large',413)
        expected='application/json' if json_body else 'application/octet-stream'
        require(self.headers.get('Content-Type','').split(';')[0].strip()==expected,'INVALID_CONTENT_TYPE','Unsupported content type',415)
        content=self.rfile.read(length)
        require(len(content)==length,'INVALID_BODY','Truncated request body',400)
        if json_body:
            try:
                value=json.loads(content)
                require(isinstance(value,dict),'INVALID_INPUT','JSON object required')
                return value
            except (ValueError,UnicodeError) as error:raise CareerError('INVALID_JSON','Malformed JSON',422) from error
        return content

    def boundary(self):
        require(len(str(self.headers).encode())<=16384 and len(self.path)<=8192,'LIMIT_EXCEEDED','Headers or URL exceed bounds',431)
        require(len(self.headers.get_all('Host',[]))==1 and self.headers['Host']=='127.0.0.1:'+str(self.server.server_port),
                'FOREIGN_HOST','Exact numeric loopback Host required',403)
        require(not self.headers.get('Transfer-Encoding') and len(self.headers.get_all('Content-Length',[]))<=1,'INVALID_BODY','Ambiguous message framing rejected',400)
        require(len(self.headers.get_all('Origin',[]))<=1 and len(self.headers.get_all('X-CSRF-Token',[]))<=1,'INVALID_HEADERS','Duplicate security headers rejected',400)
        origin=self.headers.get('Origin')
        require(origin is None or origin==self.server.origin,'FOREIGN_ORIGIN','Origin not allowed',403)
        site=self.headers.get('Sec-Fetch-Site')
        require(site in (None,'same-origin','none'),'FOREIGN_FETCH','Cross-site request rejected',403)
        if self.command=='POST':require(origin==self.server.origin,'ORIGIN_REQUIRED','Exact Origin required for mutation',403)

    def dispatch(self):
        started=time.monotonic();route='unmatched';status=500
        try:
            self.boundary()
            parsed=urlsplit(self.path);path=unquote(parsed.path)
            require('\\' not in path and '\x00' not in path and '..' not in path.split('/'),'UNSAFE_PATH','Unsafe route',403)
            query=parse_qs(parsed.query,keep_blank_values=True)
            require(all(len(values)==1 for values in query.values()),'INVALID_QUERY','Duplicate query fields')
            values={key:value[0] for key,value in query.items()}
            if path=='/health' and self.command=='GET':
                route='health';status=200;return self.reply(200,dict(protocol=PROTOCOL,status='ok'))
            if path=='/api/v1/session' and self.command=='POST':
                route='session';body=self.body();session=self.session()
                require(set(body)<= {'capability'},'INVALID_INPUT','Only capability accepted')
                if body.get('capability'):
                    with self.server.lock:expiry=self.server.capabilities.pop(body['capability'],None)
                    require(expiry and expiry>time.monotonic(),'UNAUTHENTICATED','Launch capability expired or used',401)
                    require(len(self.server.sessions)<128,'BUSY','Session capacity reached',503)
                    token=secrets.token_urlsafe(32);session=dict(csrf=secrets.token_urlsafe(32))
                    self.server.sessions[token]=session
                    extra={'Set-Cookie':'career_session='+token+'; HttpOnly; SameSite=Strict; Path=/'}
                else:
                    require(session,'UNAUTHENTICATED','Trusted launch required',401);extra={}
                status=200;return self.reply(200,dict(csrf_token=session['csrf'],protocol=PROTOCOL),extra=extra)
            if path.startswith('/api/'):
                session=self.session();require(session,'UNAUTHENTICATED','Trusted launch required',401)
                if self.command=='POST':
                    require(secrets.compare_digest(self.headers.get('X-CSRF-Token',''),session['csrf']),'CSRF_REQUIRED','Invalid CSRF token',403)
                tasks=self.server.tasks
                if self.command=='GET' and path=='/api/v1/context':
                    route='context';require(set(values)<= {'task','case_id','track_id','source_id','claim_id','answer_id','limit','cursor'},'INVALID_QUERY','Unknown context scope')
                    if 'limit' in values:values['limit']=int(values['limit'])
                    payload=tasks.context(**values)
                elif self.command=='GET' and path=='/api/v1/localization':
                    route='localization';require(set(values)<= {'locale'},'INVALID_QUERY','Unknown localization filter');payload=tasks.query('localization',**values)
                elif self.command=='GET' and path=='/api/v1/agent-intent':
                    route='agent-intent';require(set(values)<= {'intent','case_id','track_id','packet_id','version_id'} and 'intent' in values,'INVALID_QUERY','Expected intent and optional case_id/track_id/packet_id');payload=tasks.query('agent-intent',**values)
                elif self.command=='GET' and path in ('/api/v1/cases','/api/v1/contacts','/api/v1/board'):
                    route=path.rsplit('/',1)[-1]
                    allowed={'limit','cursor','q','company_id'} if route=='contacts' else {'limit','cursor','view','column','track_id','q','closed'}
                    if route=='board':allowed={'limit','track_id','q','closed'}
                    require(set(values)<=allowed,'INVALID_QUERY','Unknown filter')
                    if 'limit' in values:values['limit']=int(values['limit'])
                    if 'closed' in values:
                        require(values['closed'] in ('true','false'),'INVALID_QUERY','Invalid closed filter')
                        values['closed']=values['closed']=='true'
                    payload=tasks.query(route,**values)
                elif self.command=='GET' and re.fullmatch(r'/api/v1/contacts/[A-Za-z0-9_-]{1,128}/packets',path):
                    route='contact-packets';require(set(values)<={'limit','cursor'},'INVALID_QUERY','Unknown packet filter')
                    if 'limit' in values:values['limit']=int(values['limit'])
                    payload=tasks.query(route,record_id=path.split('/')[-2],**values)
                elif self.command=='GET' and re.fullmatch(r'/api/v1/packets/[A-Za-z0-9_-]{1,128}/versions',path):
                    route='versions';require(set(values)<={'limit','cursor'},'INVALID_QUERY','Unknown version filter')
                    if 'limit' in values:values['limit']=int(values['limit'])
                    payload=tasks.query(route,record_id=path.split('/')[-2],**values)
                elif self.command=='GET' and re.fullmatch(r'/api/v1/cases/[A-Za-z0-9_-]{1,128}/history',path):
                    route='case-history';require(set(values)<={'limit','cursor'},'INVALID_QUERY','Unknown history filter')
                    if 'limit' in values:values['limit']=int(values['limit'])
                    payload=tasks.query(route,record_id=path.split('/')[-2],**values)
                elif self.command=='GET' and path=='/api/v1/history/observations':
                    route='historical-observations';require(set(values)<={'limit','cursor'},'INVALID_QUERY','Unknown historical filter')
                    if 'limit' in values:values['limit']=int(values['limit'])
                    payload=tasks.query(route,**values)
                elif self.command=='GET' and re.fullmatch(r'/api/v1/cases/[A-Za-z0-9_-]{1,128}',path):
                    route='case-detail';payload=tasks.query('case',record_id=path.split('/')[-1])
                elif self.command=='GET' and re.fullmatch(r'/api/v1/packets/[A-Za-z0-9_-]{1,128}/selection',path):
                    route='selection';require(set(values)<={'version_id'},'INVALID_QUERY','Unknown selection filter');payload=tasks.query('selection',record_id=path.split('/')[-2],**values)
                elif self.command=='POST' and path=='/api/v1/commands':
                    route='commands';payload=tasks.command(self.body())
                elif self.command=='GET' and re.fullmatch(r'/api/v1/commands/[A-Za-z0-9_-]{1,128}',path):
                    route='command-status';payload=tasks.repository.status(path.split('/')[-1])
                elif self.command=='GET' and path=='/api/v1/changes':
                    route='changes';require(set(values)<= {'after'},'INVALID_QUERY','Unknown changes filter');payload=tasks.query('changes',after=int(values.get('after','0')))
                elif self.command=='GET' and path=='/api/v1/events':
                    route='events';status=200;return self.events(values)
                elif self.command=='POST' and path=='/api/v1/uploads':
                    route='uploads';content=self.body(25*1024*1024,False)
                    input_id=new_id('input');target=contained(tasks.repository.root,'.career-agent/staging/'+input_id)
                    with target.open('xb') as stream:stream.write(content)
                    os.chmod(target,0o600);payload=dict(input_id=input_id,sha256=digest(content),size=len(content))
                elif self.command=='GET' and re.fullmatch(r'/api/v1/artifacts/[A-Za-z0-9_-]{1,128}/download',path):
                    route='download'
                    with tasks.repository.open() as snapshot:artifact,source=snapshot.object(path.split('/')[-2]);content=source.read_bytes();require(digest(content)==artifact['sha256'],'MATERIAL_CHANGED','Download bytes changed during read')
                    status=200;return self.reply(200,content,artifact['media_type'],{'Content-Disposition':'attachment; filename="document.'+artifact['extension']+'"'})
                elif self.command=='GET' and re.fullmatch(r'/api/v1/exports/[A-Za-z0-9_-]{1,128}/files/[0-9]{1,3}',path):
                    route='view-download';require(not values,'INVALID_QUERY','Export download takes no filters')
                    from .views import export_download
                    with tasks.repository.open() as snapshot:content,media_type,name=export_download(snapshot,path.split('/')[-3],int(path.split('/')[-1]))
                    status=200;return self.reply(200,content,media_type,{'Content-Disposition':'attachment; filename="'+name+'"'})
                elif self.command=='POST' and path=='/api/v1/runtime/stop':
                    route='runtime-stop';require(self.body()=={},'INVALID_INPUT','Stop takes no input');payload=dict(status='stopping');self.server.stop()
                else:raise CareerError('NOT_FOUND','Route not found',404)
                status=200;return self.reply(200,payload)
            require(self.command=='GET','METHOD_NOT_ALLOWED','Only GET accepted',405)
            require(not values,'INVALID_QUERY','Static paths take no query')
            relative='index.html' if path in ('/','/index.html') else path.lstrip('/')
            require(relative=='index.html' or relative.startswith('assets/') or relative in ('locales/en.json','locales/ru.json'),'NOT_FOUND','Static asset not found',404)
            source=contained(self.server.assets,relative)
            require(source.is_file(),'NOT_FOUND','Static asset not found',404)
            cached=self.server.static_cache.get(relative)
            content=cached[0] if cached else source.read_bytes()
            expected=self.server.asset_hashes.get(relative)
            require(not self.server.asset_hashes or expected==digest(content),'MATERIAL_CHANGED','Installed asset failed verification')
            if relative=='index.html':
                preferences=self.server.tasks.context()['preferences'];theme=preferences['theme']
                locale=preferences['ui_locale']
                content=content.replace(b'lang="en"',('lang="'+locale+'" data-ui-locale="'+locale+'"').encode())
                content=content.replace(b'data-theme="system"',('data-theme="'+theme+'"').encode()).replace(b"data-theme='system'",("data-theme='"+theme+"'").encode())
            media='text/html; charset=utf-8' if relative=='index.html' else mimetypes.guess_type(relative)[0] or 'application/octet-stream'
            extra={}
            if relative.startswith('assets/') and re.search(r'-[A-Za-z0-9_-]{8,}\.',relative):
                sha=digest(content);extra={'Cache-Control':'private, max-age=31536000, immutable','ETag':'"'+sha+'"','Vary':'Accept-Encoding'}
                if self.headers.get('If-None-Match')==extra['ETag']:
                    route='static';status=304;return self.reply(304,b'',media,extra)
                compressed=cached[1] if cached else gzip.compress(content,compresslevel=6,mtime=0)
                if len(self.server.static_cache)<64:self.server.static_cache[relative]=(content,compressed)
                if 'gzip' in self.headers.get('Accept-Encoding',''):
                    content=compressed;extra['Content-Encoding']='gzip'
            route='static';status=200;return self.reply(200,content,media,extra)
        except CareerError as error:
            status=error.status;payload=error.wire()
            if error.status==409:payload['revision']=self.server.tasks.context()['revision']
            self.reply(status,payload)
        except (ValueError,TypeError,KeyError,UnicodeError):
            status=422;self.reply(status,{'error':{'code':'INVALID_INPUT','message':'Malformed bounded request','issues':[]}})
        except (OSError,TimeoutError):
            status=503;self.reply(status,{'error':{'code':'IO_FAILED','message':'Local operation failed; resolve command status before retry','issues':[]}})
        except Exception:
            status=500;self.reply(status,{'error':{'code':'INTERNAL_ERROR','message':'Local operation failed; no success receipt','issues':[]}})
        finally:
            self.server.logger.info('route=%s status=%s elapsed_ms=%s',route,status,round((time.monotonic()-started)*1000))

    def events(self,values):
        require(set(values)<= {'after'},'INVALID_QUERY','Unknown event filter')
        after=int(self.headers.get('Last-Event-ID',values.get('after','0')))
        require(self.server.stream_slots.acquire(blocking=False),'BUSY','At most eight event streams are supported',503)
        listener=queue.Queue(maxsize=64)
        # Subscribe before replay: deduplicate by cursor to close the replay/subscribe race.
        with self.server.lock:self.server.listeners.add(listener)
        try:
            replay=self.server.tasks.query('changes',after=after)
            self.send_response(200);self.send_header('Content-Type','text/event-stream');self.security_headers();self.send_header('Connection','close');self.end_headers()
            if replay['resync_required']:
                self.event('resync',dict(revision=replay['revision'],workspace_id=replay['workspace_id']));after=replay['revision']
            else:
                for change in replay['changes']:
                    change['workspace_id']=replay['workspace_id'];self.event('change',change);after=change['cursor']
            self.connection.settimeout(20)
            while not self.server.shutdown_event.is_set():
                try:
                    event,value=listener.get(timeout=15)
                    if event=='stop':break
                    if event=='change' and value['cursor']<=after:continue
                    self.event(event,value)
                    if event=='change':after=value['cursor']
                except queue.Empty:self.wfile.write(b': heartbeat\n\n');self.wfile.flush()
        except (BrokenPipeError,ConnectionResetError,TimeoutError):pass
        finally:
            with self.server.lock:self.server.listeners.discard(listener)
            self.server.stream_slots.release()
            self.close_connection=True

    def event(self,event,value):
        prefix=('id: '+str(value['cursor'])+'\n') if 'cursor' in value else ''
        self.wfile.write((prefix+'event: '+event+'\ndata: '+canonical(value)+'\n\n').encode());self.wfile.flush()
