import tempfile, unittest
from dataclasses import replace
from decimal import Decimal
from alpha import *

class FixtureBroker:
    # Contract fixture only; not a paper-trading product or deployable adapter.
    live_certified=True
    quantity_step=Decimal('.0001')
    def __init__(self): self.sent=[]; self.held={}; self.pending=[]; self.q=Quote('SPY',100,100.1,1000,'regular');self.fail=False;self.timeout=False
    def account(self): return Account(229.28,264.76)
    def positions(self):
        if self.fail: raise BrokerError('unavailable')
        return self.held
    def open_orders(self): return self.pending
    def quote(self,s): return self.q
    def submit(self,s,qty,side,limit,client_id):
        o=Order('order-1',client_id,s,'ACCEPTED');self.sent.append((o,qty,limit))
        if self.timeout: raise TimeoutError()
        return o
    def lookup(self,c): return next((o for o,_,_ in self.sent if o.client_id==c),None)

class CoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.b=FixtureBroker();self.path=self.tmp.name+'/receipts.sqlite';self.e=Engine(self.b,self.path,clock=lambda:1000)
        self.c=Candidate('setup-1','SPY','BREAKOUT',990,1030,100,98,105,.8)
    def tearDown(self): self.e.db.close();self.tmp.cleanup()
    def test_disarmed_has_no_order(self): self.assertEqual(self.e.execute(self.c)['reason'],'disarmed');self.assertFalse(self.b.sent)
    def test_armed_executes_without_confirmation_and_sizes_bp(self):
        self.e.arm();r=self.e.execute(self.c);self.assertEqual(r['status'],'ACCEPTED');self.assertLessEqual(r['qty']*100.1,229.28*.03)
    def test_stale_quote(self):
        self.e.arm();self.b.q=replace(self.b.q,timestamp=980);self.assertEqual(self.e.execute(self.c)['reason'],'invalid_or_stale_book')
    def test_extension_rechecked_at_submission(self):
        self.e.arm();self.b.q=replace(self.b.q,bid=101,ask=101.1);self.assertEqual(self.e.execute(self.c)['reason'],'extended')
    def test_failed_position_read_is_not_empty(self):
        self.e.arm();self.b.fail=True;self.assertEqual(self.e.execute(self.c)['reason'],'broker_read_failed');self.assertFalse(self.b.sent)
    def test_held_position_blocks(self):
        self.e.arm();self.b.held={'SPY':1};self.assertEqual(self.e.execute(self.c)['reason'],'broker_position_exists')
    def test_duplicate_survives_restart(self):
        self.e.arm();self.e.execute(self.c);self.e.db.close();self.e=Engine(self.b,self.path,clock=lambda:1000);self.e.arm();self.assertEqual(self.e.execute(self.c)['reason'],'duplicate_intent');self.assertEqual(len(self.b.sent),1)
    def test_timeout_reconciles_without_resubmitting(self):
        self.e.arm();self.b.timeout=True;self.assertEqual(self.e.execute(self.c)['status'],'UNKNOWN');self.assertFalse(self.e.armed);self.e.arm();self.assertEqual(self.e.status()['intents'][0]['status'],'ACCEPTED');self.assertEqual(len(self.b.sent),1)
    def test_expired_setup(self):
        self.e.arm();self.assertEqual(self.e.execute(replace(self.c,expires_at=999))['reason'],'expired_or_future_setup')
    def test_no_position_count_cap(self):
        self.e.arm();self.b.held={f'OTHER{i}':1 for i in range(20)};self.assertEqual(self.e.execute(self.c)['status'],'ACCEPTED')
    def test_uncertified_adapter_cannot_arm(self):
        self.b.live_certified=False
        with self.assertRaises(BrokerError): self.e.arm()
    def test_unknown_blocks_different_symbol(self):
        self.e.arm();self.b.timeout=True;self.e.execute(self.c);self.e.armed=True
        self.assertEqual(self.e.execute(replace(self.c,id='2',symbol='WMT'))['reason'],'unresolved_order')
    def test_closed_session(self):
        self.e.arm();self.b.q=replace(self.b.q,session='closed');self.assertEqual(self.e.execute(self.c)['reason'],'unsupported_session')
    def test_nan_quote(self):
        self.e.arm();self.b.q=replace(self.b.q,ask=float('nan'));self.assertEqual(self.e.execute(self.c)['reason'],'invalid_broker_data')
    def test_ranking_before_submission(self):
        self.e.arm();other=replace(self.c,id='better',score=.9);self.e.batch([self.c,other]);self.assertEqual(self.e.status()['intents'][0]['id'],'better');self.assertEqual(len(self.b.sent),1)

if __name__=='__main__': unittest.main()
