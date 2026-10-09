import importlib.util, json, threading, unittest, urllib.request, urllib.error
from pathlib import Path
spec=importlib.util.spec_from_file_location('relay',Path(__file__).parents[1]/'backend/server.py')
relay=importlib.util.module_from_spec(spec);spec.loader.exec_module(relay)
class RelayTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.server=relay.ThreadingHTTPServer(('127.0.0.1',0),relay.Handler)
  cls.url='http://127.0.0.1:'+str(cls.server.server_port)
  threading.Thread(target=cls.server.serve_forever,daemon=True).start()
 @classmethod
 def tearDownClass(cls): cls.server.shutdown();cls.server.server_close()
 def call(self,path,method='GET',data=None,token=None,origin=None):
  headers={'Content-Type':'application/json'}
  if token:headers['Authorization']='Bearer '+token
  if origin:headers['Origin']=origin
  req=urllib.request.Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,headers=headers,method=method)
  try:r=urllib.request.urlopen(req)
  except urllib.error.HTTPError as e:r=e
  with r:return r.status,json.loads(r.read())
 def test_lifecycle(self):
  code,s=self.call('/sessions','POST',{});self.assertEqual(code,201)
  path='/sessions/'+s['code'];p={'latitude':35.6,'longitude':139.7,'accuracy':12}
  self.assertIsNone(self.call(path)[1]['location'])
  self.assertEqual(self.call(path,'PUT',p)[0],403)
  self.assertEqual(self.call(path,'PUT',p,s['token'])[0],200)
  self.assertEqual(self.call(path)[1]['location']['latitude'],35.6)
  self.assertEqual(self.call(path,'DELETE',token='wrong')[0],403)
  self.assertEqual(self.call(path,'DELETE',token=s['token'])[0],200)
  self.assertEqual(self.call(path)[0],404)
 def test_validation_and_expiry(self):
  _,s=self.call('/sessions','POST',{});path='/sessions/'+s['code']
  for p in [{'latitude':91,'longitude':0,'accuracy':1},{'latitude':True,'longitude':0,'accuracy':1},{'latitude':0,'longitude':0,'accuracy':-1}]:
   self.assertEqual(self.call(path,'PUT',p,s['token'])[0],400)
  relay.sessions[s['code']]['expires']=0
  self.assertEqual(self.call(path)[0],404)
 def test_origin_and_health(self):
  self.assertEqual(self.call('/sessions','POST',{},origin='https://evil.example')[0],403)
  self.assertEqual(self.call('/health')[0],200)
