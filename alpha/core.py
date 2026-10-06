"""Independent long-equity engine. No cloud-model or MC execution dependency."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from decimal import Decimal, ROUND_DOWN
from typing import Protocol
import json, math, sqlite3, threading, time, uuid

class BrokerError(RuntimeError): pass

@dataclass(frozen=True)
class Account:
    buying_power: float
    equity: float

@dataclass(frozen=True)
class Quote:
    symbol: str
    bid: float
    ask: float
    timestamp: float  # broker book UTC epoch, never fetch time
    session: str     # regular/pre/post/overnight/closed from broker calendar

@dataclass(frozen=True)
class Candidate:
    id: str
    symbol: str
    pattern: str
    detected_at: float
    expires_at: float
    trigger: float
    stop: float
    target: float
    score: float

@dataclass(frozen=True)
class Order:
    id: str
    client_id: str
    symbol: str
    status: str
    filled_qty: float = 0

class Broker(Protocol):
    """Every read raises BrokerError on failure; never return empty fallback facts.
    positions includes signed quantities. open_orders includes unfilled BUYs.
    quote must bypass cache. submit must preserve client_id on uncertain responses.
    Broker integration must verify supported fractional precision and order type.
    """
    live_certified: bool
    quantity_step: Decimal
    def account(self) -> Account: ...
    def positions(self) -> dict[str, float]: ...
    def open_orders(self) -> list[Order]: ...
    def quote(self, symbol: str) -> Quote: ...
    def submit(self, symbol: str, qty: float, side: str, limit: float, client_id: str) -> Order: ...
    def lookup(self, client_id: str) -> Order | None: ...

@dataclass(frozen=True)
class Policy:
    allocation: float = .03
    quote_age_seconds: float = 15
    max_spread_fraction: float = .005
    max_extension_fraction: float = .005
    min_reward_risk: float = 2
    patterns: tuple[str, ...] = ('VWAP_RECLAIM','HOD_BREAK','BREAKOUT','PULLBACK','MOMENTUM_REACCEL')
    def __post_init__(self):
        if self.allocation != .03: raise ValueError('Allocation is 3% of available buying power')
        for value in (self.quote_age_seconds,self.max_spread_fraction,self.max_extension_fraction,self.min_reward_risk):
            if not math.isfinite(value) or value <= 0: raise ValueError('Invalid policy')

class Engine:
    def __init__(self, broker: Broker, db_path: str, policy: Policy = Policy(), clock=time.time):
        self.broker,self.policy,self.clock = broker,policy,clock
        self.armed = False
        self.lock = threading.RLock()
        self.db = sqlite3.connect(db_path,check_same_thread=False)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS intents (id TEXT PRIMARY KEY,symbol TEXT,client_id TEXT UNIQUE,status TEXT,order_id TEXT,qty REAL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS receipts (seq INTEGER PRIMARY KEY,at REAL,event TEXT,payload TEXT)')
        self.db.commit()
    def record(self,event,**payload):
        self.db.execute('INSERT INTO receipts(at,event,payload) VALUES(?,?,?)',(self.clock(),event,json.dumps(payload)))
        self.db.commit()
    def arm(self):
        with self.lock:
            if not self.broker.live_certified: raise BrokerError('Broker integration not certified for live execution')
            self.reconcile()
            if self.db.execute("SELECT 1 FROM intents WHERE status IN ('SUBMITTING','UNKNOWN')").fetchone():
                raise BrokerError('Unresolved order intent')
            self.armed=True
            self.record('ARMED')
    def disarm(self):
        with self.lock:
            self.armed=False
            self.record('DISARMED')
    def batch(self,candidates):
        # Caller delivers a bounded discovery batch; ordering precedes execution.
        return [self.execute(c) for c in sorted(candidates,key=lambda c:(-c.score,c.symbol,c.id))]
    def reject(self,c,reason):
        self.record('REJECT',candidate=c.id,symbol=c.symbol,reason=reason)
        return {'status':'REJECTED','reason':reason}
    def execute(self,c: Candidate):
        with self.lock:
            if not self.armed: return self.reject(c,'disarmed')
            numbers=(c.detected_at,c.expires_at,c.trigger,c.stop,c.target,c.score)
            if not c.id or not c.symbol or any(not math.isfinite(x) for x in numbers): return self.reject(c,'invalid_candidate')
            if c.pattern not in self.policy.patterns: return self.reject(c,'pattern_not_enabled')
            if self.db.execute('SELECT 1 FROM intents WHERE id=?',(c.id,)).fetchone(): return self.reject(c,'duplicate_intent')
            if self.db.execute("SELECT 1 FROM intents WHERE status IN ('SUBMITTING','UNKNOWN')").fetchone(): return self.reject(c,'unresolved_order')
            if self.db.execute("SELECT 1 FROM intents WHERE symbol=? AND status NOT IN ('FILLED','CANCELED','REJECTED','EXPIRED')",(c.symbol,)).fetchone(): return self.reject(c,'symbol_inflight')
            try:
                a=self.broker.account();positions=self.broker.positions();orders=self.broker.open_orders()
                if positions.get(c.symbol,0)!=0: return self.reject(c,'broker_position_exists')
                if any(o.symbol==c.symbol for o in orders): return self.reject(c,'broker_order_exists')
                # LAST read before validating and committing intent: never emit-time quote.
                q=self.broker.quote(c.symbol)
                now=self.clock()
                if c.detected_at>now or not c.detected_at<=now<c.expires_at: return self.reject(c,'expired_or_future_setup')
                if q.symbol!=c.symbol or q.session!='regular': return self.reject(c,'unsupported_session')
                if any(not math.isfinite(x) for x in (q.bid,q.ask,q.timestamp,a.buying_power,a.equity)): return self.reject(c,'invalid_broker_data')
                if q.bid<=0 or q.ask<q.bid or not 0<=now-q.timestamp<=self.policy.quote_age_seconds: return self.reject(c,'invalid_or_stale_book')
                if (q.ask-q.bid)/q.ask>self.policy.max_spread_fraction: return self.reject(c,'spread')
                if not 0<c.stop<c.trigger<c.target: return self.reject(c,'invalid_trade_plan')
                if q.ask<c.trigger: return self.reject(c,'trigger_not_reached')
                if q.ask>c.trigger*(1+self.policy.max_extension_fraction): return self.reject(c,'extended')
                if (c.target-q.ask)/(q.ask-c.stop)<self.policy.min_reward_risk: return self.reject(c,'reward_risk')
                if a.buying_power<=0 or a.equity<=0: return self.reject(c,'no_buying_power')
                step=self.broker.quantity_step
                if not step.is_finite() or step<=0: return self.reject(c,'invalid_quantity_step')
                units=(Decimal(str(a.buying_power))*Decimal('.03')/Decimal(str(q.ask))/step).to_integral_value(rounding=ROUND_DOWN)
                qty=float(units*step)
                if qty<=0: return self.reject(c,'unaffordable')
            except Exception as e:
                self.record('BROKER_READ_ERROR',candidate=c.id,error_type=type(e).__name__)
                return self.reject(c,'broker_read_failed')
            client_id=str(uuid.uuid4())
            self.db.execute('INSERT INTO intents VALUES(?,?,?,?,?,?)',(c.id,c.symbol,client_id,'SUBMITTING',None,qty))
            self.db.commit() # Durable before any network submission.
            self.record('SUBMITTING',candidate=c.id,client_id=client_id,symbol=c.symbol,qty=qty,limit=q.ask,book_timestamp=q.timestamp,detected_at=c.detected_at)
            try:
                o=self.broker.submit(c.symbol,qty,'BUY',q.ask,client_id)
                self._accept(c.id,client_id,c.symbol,qty,o)
                return {'status':o.status,'order_id':o.id,'qty':qty}
            except Exception as e:
                self.db.execute("UPDATE intents SET status='UNKNOWN' WHERE id=?",(c.id,));self.db.commit()
                self.record('UNKNOWN',candidate=c.id,error_type=type(e).__name__)
                self.armed=False # Uncertain submission never retried automatically.
                return {'status':'UNKNOWN','reason':'reconciliation_required'}
    def _accept(self,id,client_id,symbol,qty,o):
        valid={'ACCEPTED','PARTIALLY_FILLED','FILLED','CANCELED','REJECTED','EXPIRED'}
        if not o.id or o.client_id!=client_id or o.symbol!=symbol or o.status not in valid or not math.isfinite(o.filled_qty) or not 0<=o.filled_qty<=qty:
            raise BrokerError('Invalid acknowledgment')
        self.db.execute('UPDATE intents SET status=?,order_id=? WHERE id=?',(o.status,o.id,id));self.db.commit()
        self.record('BROKER_ORDER',candidate=id,**asdict(o))
    def reconcile(self):
        with self.lock:
            rows=self.db.execute("SELECT id,symbol,client_id,qty FROM intents WHERE status NOT IN ('FILLED','CANCELED','REJECTED','EXPIRED')").fetchall()
            for id,symbol,client_id,qty in rows:
                try:
                    o=self.broker.lookup(client_id)
                    if o: self._accept(id,client_id,symbol,qty,o)
                    else:
                        self.db.execute("UPDATE intents SET status='UNKNOWN' WHERE id=?",(id,));self.db.commit()
                        self.armed=False
                except Exception:
                    self.armed=False
                    raise BrokerError('Reconciliation failed') from None
    def status(self):
        return {'armed':self.armed,'allocation':self.policy.allocation,'intents':[dict(zip(('id','symbol','client_id','status','order_id','qty'),r)) for r in self.db.execute('SELECT * FROM intents')], 'receipts':[{'at':r[0],'event':r[1],**json.loads(r[2])} for r in self.db.execute('SELECT at,event,payload FROM receipts ORDER BY seq DESC LIMIT 100')]}
