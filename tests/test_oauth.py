import sys,unittest,os,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import tesla_oauth as o,device_auth
from urllib.parse import urlsplit,parse_qs
class OAuthTest(unittest.TestCase):
 def setUp(self):
  self.env=patch.dict(os.environ,{'TESLA_OWNER_SECRET':'x'*32,'TESLA_CLIENT_ID':'client','TESLA_CLIENT_SECRET':'secret','TESLA_REDIRECT_URI':'https://tesla-webmap.onrender.com/auth/tesla/callback'});self.env.start();o.pending.clear();o.tokens.clear()
 def tearDown(self):self.env.stop()
 def flow(self):
  q=parse_qs(urlsplit(o.begin(device_auth.issue())).query);url,cookie=o.launch(q)
  return q['state'][0],cookie,url
 def test_owner_required(self):
  with self.assertRaises(o.OAuthError):o.begin('invalid')
 def test_browser_binding_replay_and_exchange(self):
  state,cookie,url=self.flow();self.assertIn('vehicle_cmds',url)
  with self.assertRaises(o.OAuthError):o.callback({'state':[state],'code':['code']},'tesla_oauth=wrong')
  with patch.object(o,'exchange',return_value={'access':'access','expires':time.time()+600,'refresh':'refresh'}) as exchange:
   o.callback({'state':[state],'code':['code']},'tesla_oauth='+cookie)
   self.assertEqual(exchange.call_args[0][0]['redirect_uri'],os.environ['TESLA_REDIRECT_URI'])
  self.assertEqual(o.access_token(),'access')
  with self.assertRaises(o.OAuthError):o.callback({'state':[state],'code':['code']},'tesla_oauth='+cookie)
 def test_expiry_and_secret_rotation(self):
  state,cookie,_=self.flow();o.pending[state]['expires']=0
  with self.assertRaises(o.OAuthError):o.callback({'state':[state],'code':['code']},'tesla_oauth='+cookie)
  o.tokens.update(access='a',expires=time.time()+500,owner_secret='old');self.assertEqual(o.access_token(),'')
 def test_cancel(self):
  state,cookie,_=self.flow()
  with self.assertRaises(o.OAuthError):o.callback({'state':[state],'error':['access_denied']},'tesla_oauth='+cookie)
  self.assertFalse(o.tokens)
 def test_bad_callback_configuration(self):
  os.environ['TESLA_REDIRECT_URI']='https://example.com/other'
  with self.assertRaises(o.OAuthError):o.begin(device_auth.issue())
