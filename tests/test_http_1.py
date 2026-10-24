"""Loopback security and shared CLI/HTTP/SSE persistence with fictional data."""
import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from career.server import LocalServer
from test_runtime_1 import Fixture


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='career-http-fictional-');self.addCleanup(self.temp.cleanup)
        self.fx=Fixture(self.temp.name).seed()
        assets=Path(self.temp.name)/'test-assets';assets.mkdir();(assets/'index.html').write_text('<html data-theme="system"><body>Fictional app</body></html>')
        self.server=LocalServer(self.temp.name,assets)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.cleanup_server)
        self.cookie=None;self.csrf=None

    def cleanup_server(self):
        self.server.stop();self.thread.join(3);self.server.server_close()

    def request(self,path,method='GET',body=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        values={'Origin':self.server.origin}
        if self.cookie:values['Cookie']=self.cookie
        if self.csrf:values['X-CSRF-Token']=self.csrf
        if body is not None:body=json.dumps(body);values['Content-Type']='application/json'
        values.update(headers or {})
        connection.request(method,path,body,values);response=connection.getresponse();content=response.read();result=(response.status,dict(response.getheaders()),content);connection.close();return result

    def authenticate(self):
        capability=self.server.mint().split('#launch=')[1]
        status,headers,body=self.request('/api/v1/session','POST',dict(capability=capability))
        self.assertEqual(200,status);self.cookie=headers['Set-Cookie'].split(';')[0];self.csrf=json.loads(body)['csrf_token']
        return capability

    def test_host_origin_csrf_session_expiry_and_security_headers(self):
        self.assertEqual(403,self.request('/health',headers={'Host':'attacker.example'})[0])
        self.assertEqual(403,self.request('/health',headers={'Origin':'null'})[0])
        self.assertEqual(401,self.request('/api/v1/context')[0])
        self.assertEqual(401,self.request('/api/v1/events')[0])
        capability=self.authenticate()
        self.assertEqual(401,self.request('/api/v1/session','POST',dict(capability=capability))[0])
        self.csrf=None
        self.assertEqual(403,self.request('/api/v1/commands','POST',{})[0])
        status,headers,body=self.request('/api/v1/session','POST',{})
        self.assertEqual(200,status);self.csrf=json.loads(body)['csrf_token']
        self.assertIn("frame-ancestors 'none'",headers['Content-Security-Policy'])
        self.assertNotIn('Access-Control-Allow-Origin',headers)
        self.assertEqual(403,self.request('/api/v1/context',headers={'Sec-Fetch-Site':'cross-site'})[0])

    def test_ui_save_cli_read_and_stale_conflict_receipt_lookup(self):
        self.authenticate();revision=self.fx.tasks.context()['revision']
        command=dict(request_id='browser_save',expected_revision=revision,intent='case.note',input=dict(case_id='case_one',text='Saved from browser'))
        status,_,body=self.request('/api/v1/commands','POST',command)
        self.assertEqual(200,status);receipt=json.loads(body)
        self.assertEqual('Saved from browser',self.fx.tasks.query('case',record_id='case_one')['notes'])
        self.assertEqual(receipt,json.loads(self.request('/api/v1/commands/browser_save')[2]))
        self.fx.command('preferences.set',theme='dark')
        self.assertEqual(409,self.request('/api/v1/commands','POST',dict(command,request_id='stale'))[0])
        self.assertEqual(receipt,json.loads(self.request('/api/v1/commands','POST',command)[2]))
        self.assertIn(b'data-theme="dark"',self.request('/')[2])

    def test_cli_commit_replayed_through_sse_and_polling(self):
        self.authenticate();before=self.fx.tasks.context()['revision']
        connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        connection.request('GET','/api/v1/events?after='+str(before),headers={'Cookie':self.cookie,'Origin':self.server.origin})
        response=connection.getresponse();self.assertEqual(200,response.status)
        self.fx.command('case.note',case_id='case_one',text='External CLI change')
        lines=[]
        while True:
            line=response.readline().decode();lines.append(line)
            if line=='\n':break
        payload=json.loads(next(line[6:] for line in lines if line.startswith('data: ')))
        self.assertEqual(before+1,payload['revision']);self.assertEqual(self.fx.tasks.context()['workspace_id'],payload['workspace_id'])
        connection.close()
        poll=json.loads(self.request('/api/v1/changes?after='+str(before))[2])
        self.assertEqual(before+1,poll['changes'][0]['cursor'])

    def test_paths_arbitrary_commands_upload_bounds_and_private_download(self):
        self.authenticate()
        self.assertEqual(403,self.request('/%2e%2e/private')[0])
        self.assertEqual(404,self.request('/api/v1/sql')[0])
        self.assertEqual(422,self.request('/api/v1/commands','POST',dict(request_id='bad',expected_revision=8,intent='sql',input={}))[0])
        self.assertEqual(422,self.request('/api/v1/cases?arbitrary=true')[0])
        projection=self.fx.tasks.query('selection',record_id='packet_one')
        status,headers,body=self.request(projection['slots'][0]['download_url'])
        self.assertEqual(200,status);self.assertIn('attachment',headers['Content-Disposition'])
        self.assertEqual(projection['slots'][0]['text'].encode(),body)


if __name__=='__main__':unittest.main()
