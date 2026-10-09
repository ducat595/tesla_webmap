import unittest, os
from unittest.mock import patch
import test_relay as fixture
relay=fixture.relay

class PairingTest(unittest.TestCase):
    setUpClass=classmethod(fixture.RelayTest.setUpClass.__func__)
    tearDownClass=classmethod(fixture.RelayTest.tearDownClass.__func__)
    call=fixture.RelayTest.call
    def test_short_code_requires_owner_approval(self):
        _,s=self.call('/sessions','POST',{});self.assertRegex(s['code'],r'^\d{4}$');path='/sessions/'+s['code']
        self.call(path,'PUT',{'latitude':35,'longitude':139,'accuracy':10},s['token'])
        self.assertEqual(self.call(path,anonymous=True)[0],403)
        _,pair=self.call(path+'/pair','POST',{})
        self.assertEqual(self.call(path,token=pair['viewerToken'])[0],403)
        self.assertFalse(self.call(path+'/pair-status',token=pair['viewerToken'])[1]['approved'])
        self.assertEqual(self.call(path+'/approve','POST',{'pairId':pair['pairId'],'allow':True},pair['viewerToken'])[0],403)
        self.assertEqual(self.call(path+'/approve','POST',{'pairId':pair['pairId'],'allow':True},s['token'])[0],200)
        self.assertEqual(self.call(path,token=pair['viewerToken'])[1]['location']['latitude'],35)
        self.assertEqual(self.call(path,'DELETE',token=pair['viewerToken'])[0],403)
        self.call(path,'DELETE',token=s['token']);self.assertEqual(self.call(path,token=pair['viewerToken'])[0],404)
    def test_rejection_and_pair_expiry(self):
        _,s=self.call('/sessions','POST',{});path='/sessions/'+s['code'];_,pair=self.call(path+'/pair','POST',{})
        self.call(path+'/approve','POST',{'pairId':pair['pairId'],'allow':False},s['token'])
        self.assertEqual(self.call(path+'/pair-status',token=pair['viewerToken'])[0],403)
        relay.sessions[s['code']]['pairExpires']=0
        self.assertEqual(self.call(path+'/pair','POST',{})[0],410)
    def test_device_registration_and_rotation(self):
        with patch.dict(os.environ,{'TESLA_OWNER_SECRET':'a'*40}):
            self.assertEqual(self.call('/owner-device','POST',{'key':'wrong'})[0],403)
            _,d=self.call('/owner-device','POST',{'key':'a'*40})
            ticket=d['deviceToken'];self.assertTrue(relay.device_auth.valid(ticket))
            self.assertFalse(relay.device_auth.valid(ticket+'x'))
            _,s=self.call('/sessions','POST',{},extra={'X-Tesla-Device-Token':ticket});self.assertTrue(s['ownerAuthorized'])
            path='/sessions/'+s['code'];_,pair=self.call(path+'/pair','POST',{})
            self.call(path+'/approve','POST',{'pairId':pair['pairId'],'allow':True},s['token'])
            result=self.call(path,token=pair['viewerToken'])[1];self.assertTrue(result['ownerAuthorized']);self.assertNotIn('ownerDevice',result)
            with patch.dict(os.environ,{'TESLA_OWNER_SECRET':'b'*40}):
                self.assertFalse(relay.device_auth.valid(ticket));self.assertFalse(self.call(path)[1]['ownerAuthorized'])
