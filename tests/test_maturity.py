import json, math, unittest
from dataclasses import replace
from alpha.maturity import Move, MaturityPolicy
from alpha.expectancy import summarize
import test_core

class MaturityTests(unittest.TestCase):
    def setUp(self):
        test_core.CoreTests.setUp(self)
        self.move=Move(900,98,1,995,10,101,100,'first_pullback','trend','feed',5,1,-.1,1,.7)
        self.c=replace(self.c,move=self.move)
        self.e.maturity_policy=MaturityPolicy(enforce=True,max_leg_extension_atr=4,calibration_id='heldout-v1',regime='trend',feed='feed',timeframe_seconds=5)
    def tearDown(self):
        test_core.CoreTests.tearDown(self)
    def test_missing_blocks_when_enforced(self):
        self.e.arm();self.assertEqual(self.e.execute(replace(self.c,move=None))['reason'],'maturity_missing');self.assertFalse(self.b.sent)
    def test_first_pullback_eligible(self):
        self.e.arm();self.assertEqual(self.e.execute(self.c)['status'],'ACCEPTED')
    def test_peak_not_reset_by_pullback(self):
        self.e.arm();self.assertEqual(self.e.execute(replace(self.c,move=replace(self.move,peak_price=103)))['reason'],'maturity_extended')
    def test_current_ask_recomputes_retrace(self):
        self.e.arm();self.b.q=replace(self.b.q,bid=100.4,ask=100.45)
        self.assertEqual(self.e.execute(self.c)['reason'],'maturity_pullback_depth')
    def test_stale_move_blocks_fresh_quote(self):
        self.e.arm();self.assertEqual(self.e.execute(replace(self.c,move=replace(self.move,observed_at=980)))['reason'],'maturity_stale')
    def test_unknown_flow_not_invented(self):
        self.e.arm();self.assertEqual(self.e.execute(replace(self.c,move=replace(self.move,counter_volume_ratio=None)))['reason'],'maturity_counter_volume_missing')
    def test_future_origin_invalid(self):
        self.e.arm();self.assertEqual(self.e.execute(replace(self.c,move=replace(self.move,origin_at=1001)))['reason'],'maturity_invalid')
    def test_nan_atr_invalid(self):
        self.e.arm();self.assertEqual(self.e.execute(replace(self.c,move=replace(self.move,atr_at_origin=math.nan)))['reason'],'maturity_invalid')
    def test_second_pullback_blocked(self):
        self.e.arm();self.assertEqual(self.e.execute(replace(self.c,move=replace(self.move,pullback_count=2)))['reason'],'maturity_not_first_pullback')
    def test_scope_mismatch(self):
        self.e.arm();self.assertEqual(self.e.execute(replace(self.c,move=replace(self.move,regime='range')))['reason'],'maturity_calibration_scope')
    def test_decelerating_breakout(self):
        self.e.arm();self.assertEqual(self.e.execute(replace(self.c,move=replace(self.move,entry_kind='compression_breakout')))['reason'],'maturity_decelerating')
    def test_diagnostic_has_no_veto(self):
        self.e.maturity_policy=MaturityPolicy();self.e.arm()
        self.assertEqual(self.e.execute(replace(self.c,move=None))['status'],'ACCEPTED')
    def test_disarmed_signal_logged_and_labelled(self):
        self.e.execute(self.c)
        outcomes=[dict(candidate=self.c.id,stage='signal',horizon_seconds=60,exit_at=1055,exit_bid=101,total_cost_fraction=.002)]
        row=summarize(self.e.db,outcomes)[0]
        self.assertAlmostEqual(row['mean_net_pct'],.8);self.assertEqual(row['n'],1)
        with self.assertRaises(ValueError): summarize(self.e.db,outcomes+outcomes)
        with self.assertRaises(ValueError): summarize(self.e.db,[{**outcomes[0],'exit_at':1054}])
    def test_current_ask_cannot_escape_peak_cutoff(self):
        self.e.arm();self.b.q=replace(self.b.q,bid=102.1,ask=102.2)
        self.assertEqual(self.e.execute(self.c)['reason'],'maturity_extended')
    def test_boolean_config_required(self):
        with self.assertRaises(ValueError): MaturityPolicy(enforce='false')
    def test_scoped_calibration_required(self):
        with self.assertRaises(ValueError): MaturityPolicy(enforce=True)
