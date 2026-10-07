"""Causal long-equity move snapshots; no inferred order flow or probabilities."""
from dataclasses import dataclass, asdict
import math

@dataclass(frozen=True)
class Move:
    # Worker must identify origin using only information available at observed_at.
    origin_at: float
    origin_price: float
    atr_at_origin: float  # frozen denominator; never enlarged to forgive extension
    observed_at: float
    bars_since_origin: int
    peak_price: float
    observed_ask: float  # executable ask at observed_at, not trigger or candle close
    entry_kind: str  # first_pullback or compression_breakout
    regime: str
    feed: str
    timeframe_seconds: float
    velocity_atr_per_min: float
    acceleration_atr_per_min2: float
    pullback_count: int = 0
    counter_volume_ratio: float | None = None  # current / previous counter-leg volume rate
    participation_slope: float | None = None
    aggressor_imbalance: float | None = None
    absorption: bool | None = None

    def validate(self, now):
        values=(self.origin_at,self.origin_price,self.atr_at_origin,self.observed_at,
                self.peak_price,self.observed_ask,self.timeframe_seconds,self.velocity_atr_per_min,
                self.acceleration_atr_per_min2)
        optional=(self.counter_volume_ratio,self.participation_slope,self.aggressor_imbalance)
        if any(not math.isfinite(x) for x in values): raise ValueError('nonfinite_move')
        if any(x is not None and not math.isfinite(x) for x in optional): raise ValueError('nonfinite_flow')
        if not 0 <= self.origin_at <= self.observed_at <= now: raise ValueError('move_time')
        if min(self.origin_price,self.observed_ask,self.atr_at_origin,self.timeframe_seconds)<=0: raise ValueError('move_scale')
        if self.peak_price<=self.origin_price: raise ValueError('move_peak')
        if type(self.bars_since_origin) is not int or self.bars_since_origin<0: raise ValueError('move_age')
        if type(self.pullback_count) is not int or self.pullback_count<0: raise ValueError('pullback_count')
        if not self.regime or not self.feed: raise ValueError('move_provenance')
        if self.entry_kind not in ('first_pullback','compression_breakout'): raise ValueError('entry_kind')
        if self.counter_volume_ratio is not None and self.counter_volume_ratio<0: raise ValueError('counter_volume')
        if self.absorption is not None and type(self.absorption) is not bool: raise ValueError('absorption')

    def metrics(self, price, now):
        self.validate(now)
        if not math.isfinite(price) or price<=0: raise ValueError('entry_price')
        return {**asdict(self), 'extension_atr':(price-self.origin_price)/self.atr_at_origin,
                'leg_extension_atr':(max(price,self.peak_price)-self.origin_price)/self.atr_at_origin,
                'retrace_fraction':(self.peak_price-price)/(self.peak_price-self.origin_price),
                'origin_lag_seconds':now-self.origin_at,
                'snapshot_age_seconds':now-self.observed_at,
                'entry_price':price}

@dataclass(frozen=True)
class MaturityPolicy:
    enforce: bool = False  # diagnostic rollout until calibrated externally
    max_leg_extension_atr: float | None = None
    calibration_id: str = ''
    regime: str = ''
    feed: str = ''
    timeframe_seconds: float | None = None
    max_snapshot_age_seconds: float = 15
    max_bars_since_origin: int | None = None
    retrace_min: float = .25
    retrace_max: float = .40

    def __post_init__(self):
        if type(self.enforce) is not bool: raise ValueError('enforce must be a JSON boolean')
        if not 0<self.retrace_min<self.retrace_max<1: raise ValueError('retrace_range')
        if not math.isfinite(self.max_snapshot_age_seconds) or self.max_snapshot_age_seconds<=0: raise ValueError('snapshot_age')
        if self.max_leg_extension_atr is not None and (not math.isfinite(self.max_leg_extension_atr) or self.max_leg_extension_atr<=0): raise ValueError('extension_cutoff')
        if self.max_bars_since_origin is not None and (type(self.max_bars_since_origin) is not int or self.max_bars_since_origin<0): raise ValueError('age_cutoff')
        if self.enforce and (self.max_leg_extension_atr is None or not self.calibration_id or not self.regime or not self.feed or self.timeframe_seconds is None):
            raise ValueError('Enforcement requires a versioned, scoped calibration')
        if self.timeframe_seconds is not None and (not math.isfinite(self.timeframe_seconds) or self.timeframe_seconds<=0): raise ValueError('timeframe')

    def evaluate(self, move, price, now):
        if move is None: return 'maturity_missing', None
        try: m=move.metrics(price,now)
        except (ValueError,TypeError,AttributeError): return 'maturity_invalid', None
        if m['snapshot_age_seconds']>self.max_snapshot_age_seconds: return 'maturity_stale',m
        if self.enforce and (move.regime,move.feed,move.timeframe_seconds)!=(self.regime,self.feed,self.timeframe_seconds): return 'maturity_calibration_scope',m
        # Peak extension prevents a spent move being reset by a pullback.
        if self.max_leg_extension_atr is not None and m['leg_extension_atr']>self.max_leg_extension_atr: return 'maturity_extended',m
        if self.max_bars_since_origin is not None and move.bars_since_origin>self.max_bars_since_origin: return 'maturity_old',m
        if move.absorption is True: return 'maturity_absorption',m
        if move.entry_kind=='first_pullback':
            if move.pullback_count!=1: return 'maturity_not_first_pullback',m
            if not self.retrace_min<=m['retrace_fraction']<=self.retrace_max: return 'maturity_pullback_depth',m
            if move.counter_volume_ratio is None: return 'maturity_counter_volume_missing',m
            if move.counter_volume_ratio>=1: return 'maturity_counter_volume',m
        else:
            if move.velocity_atr_per_min<=0 or move.acceleration_atr_per_min2<=0: return 'maturity_decelerating',m
            if move.participation_slope is not None and move.participation_slope<0: return 'maturity_participation',m
        return 'maturity_eligible',m
