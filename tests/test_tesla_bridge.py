import json, os, threading, unittest
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import test_relay as fixture
relay=fixture.relay

class Proxy(BaseHTTPRequestHandler):
    calls=[]
    success=True
    def log_message(self,*args): pass
    def do_POST(self):
        body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.calls.append((self.path,body,self.headers.get('Authorization')))
        self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers()
        self.wfile.write(json.dumps({'response':{'result':self.success}}).encode())

class TeslaBridgeTest(unittest.TestCase):
    setUpClass=classmethod(fixture.RelayTest.setUpClass.__func__)
    tearDownClass=classmethod(fixture.RelayTest.tearDownClass.__func__)
    call=fixture.RelayTest.call
    def setUp(self):
        self.proxy=ThreadingHTTPServer(('127.0.0.1',0),Proxy)
        threading.Thread(target=self.proxy.serve_forever,daemon=True).start()
        Proxy.calls=[];Proxy.success=True
        self.env=patch.dict(os.environ,{'TESLA_COMMAND_PROXY_URL':'http://127.0.0.1:'+str(self.proxy.server_port),'TESLA_ACCESS_TOKEN':'fixture-token','TESLA_VIN':'5YJ3E1EA0PF000001','TESLA_OWNER_SECRET':'a'*40})
        self.env.start()
    def tearDown(self):
        self.env.stop();self.proxy.shutdown();self.proxy.server_close()
    def owner_call(self,path,payload,owner='a'*40):
        import urllib.request,urllib.error
        r=urllib.request.Request(self.url+path,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+(self.tokens[path.rsplit('/',1)[0]] if owner=='a'*40 else 'wrong')},method='POST')
        try: result=urllib.request.urlopen(r)
        except urllib.error.HTTPError as e: result=e
        with result:return result.status,json.loads(result.read())
    def plan(self):
        _,s=self.call('/sessions','POST',{});path='/sessions/'+s['code']
        d={'latitude':35.2,'longitude':139.2,'name':'目的地','placeId':'DESTINATION_ID'}
        w=[{'latitude':35.1,'longitude':139.1,'name':'経由A','placeId':'WAYPOINT_A'},{'latitude':35.15,'longitude':139.15,'name':'経由B','placeId':'WAYPOINT_B'}]
        code,p=self.call(path,'PUT',{'destination':d,'waypoints':w},s['token']);self.assertEqual(code,200)
        _,device=self.call('/owner-device','POST',{'key':'a'*40})
        self.assertEqual(self.call(path+'/authorize','POST',{},s['token'],extra={'X-Tesla-Device-Token':device['deviceToken']})[0],200)
        return s,path,p['destinationVersion']
    def test_order_auth_and_duplicate(self):
        s,path,v=self.plan();request={'version':v,'requestId':'fixture-request-0001'}
        self.assertEqual(self.owner_call(path+'/tesla-navigate',request,'wrong')[0],403)
        self.assertEqual(Proxy.calls,[])
        self.assertEqual(self.owner_call(path+'/tesla-navigate',{**request,'version':v-1})[0],409)
        code,result=self.owner_call(path+'/tesla-navigate',request);self.assertEqual(code,200);self.assertTrue(result['accepted'])
        self.assertEqual(Proxy.calls[0][1],{'waypoints':'refId:WAYPOINT_A,refId:WAYPOINT_B,refId:DESTINATION_ID'})
        self.assertEqual(Proxy.calls[0][2],'Bearer fixture-token')
        self.owner_call(path+'/tesla-navigate',request);self.assertEqual(len(Proxy.calls),1)
        shared=self.call(path)[1];self.assertEqual([x['name'] for x in shared['waypoints']],['経由A','経由B'])
        self.assertNotIn('token',shared);self.assertNotIn('TESLA_OWNER_SECRET',shared)
    def test_rejection_and_place_ids(self):
        s,path,v=self.plan();Proxy.success=False
        self.assertEqual(self.owner_call(path+'/tesla-navigate',{'version':v,'requestId':'fixture-request-0002'})[0],502)
        self.call(path,'PUT',{'destination':{'latitude':35.2,'longitude':139.2,'name':'IDなし'},'waypoints':[]},s['token'])
        self.assertEqual(self.owner_call(path+'/tesla-navigate',{'version':v+1,'requestId':'fixture-request-0003'})[0],400)
        self.assertEqual(len(Proxy.calls),1)
    def test_waypoints_limit(self):
        s,path,v=self.plan();w={'latitude':35.1,'longitude':139.1,'name':'経由'}
        self.assertEqual(self.call(path,'PUT',{'waypoints':[w]*9},s['token'])[0],400)
