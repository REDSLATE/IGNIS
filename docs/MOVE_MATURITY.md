# Move maturity: diagnostic rollout first

The previous `extended` gate caps distance above the *trigger*. This change adds
an independent move-origin gate, evaluated using the current broker ask before
submission. Starts diagnostic-only. No live adapter, scanner or deployment is added.

## Worker contract

Each Candidate may carry a `move` object (see `alpha.maturity.Move`). The scanner
must define an origin causally, freeze its ATR at that point, retain that origin
and peak throughout subsequent pullbacks, and attach timestamps, actual observed
ask, bar age, regime, feed and timeframe. Never choose a later hindsight swing low,
relabel an old move as new, or normalize it with a larger subsequent ATR.

Velocity and acceleration are signed price change per elapsed minute, normalized
by origin ATR, and its time derivative. Use consistent rolling windows. Worker
must supply these from timestamped observations. A breakout must be identified at
compression onset by the detector, not merely labeled `compression_breakout` here.
The gate validates a supplied setup; it does not discover or place pullback orders.

Counter-volume ratio compares counter-leg volume *rates* across consecutive
windows; values below 1 mean declining participation. OHLCV supports volume-rate
features, not true aggressor imbalance or absorption. Those require timestamped
trade/quote data and an explicit classifier. Missing order flow remains null.
OI/funding is outside this equity-only patch. No blanket crypto OI rule is added.

## Diagnostics

SIGNAL receipts include every execute attempt, including disarmed/rejected
candidates. MATURITY receipts add current-ask extension and signal-to-submit lag
for candidates reaching the fresh broker quote. Log origin-to-snapshot delay,
origin-to-decision delay, snapshot age, origin bar age, extension and peak extension.
Group by feed and timeframe to expose detection/feed bottlenecks. Duplicates remain
visible in receipts but are deduplicated by candidate ID in outcome reports.

Record forward executable bids for ALL signals, including vetoed signals, without
placing orders. Outcome JSONL uses `candidate`, `stage` (signal/submit),
`horizon_seconds`, `exit_at`, `exit_bid`, `total_cost_fraction`. This estimates
forward quote expectancy, not realized fill P&L; costs include commissions and
estimated slippage, with spread already reflected by ask-to-bid measurement.
Signal horizon starts at snapshot observed_at; submit horizon starts at quote-check
clock time. Exit labels must fall at/after the horizon within one source bar.
Do not mix signal and submit cohorts or executed-only labels.

```
python -m alpha.expectancy --db alpha.sqlite --outcomes outcomes.jsonl --output report --stage signal
```

Produces expectancy.csv and expectancy.svg, split by pattern/regime/feed/timeframe/
horizon, 1-ATR extension buckets and 5-bar age buckets. No data means no inferred
cutoff. Approximate intervals assume independent observations; overlapping signals
need session/block bootstrap before using uncertainty for calibration.

## Enforcement

Supply `--maturity-policy calibration.json` to the runner. Enforcement requires
an explicit positive `max_leg_extension_atr`, `calibration_id`, `regime`, `feed`,
`timeframe_seconds` and `enforce: true`. Derive these offline using chronological
training/validation splits with leakage purging for overlapping outcome horizons,
then test on held-out sessions including costs. Never auto-enable from a report.
The initial policy supports one scoped cohort; mismatched cohorts fail closed.
Extension percentile and calibrated P(continuation) are NOT implemented: completed
leg distributions are not calibrated conditional continuation probabilities.

When enforcing, missing/invalid/stale moves veto entry. Peak leg extension includes
any higher current ask, so a pullback cannot erase exhaustion. First-pullback entries
require pullback_count=1, configurable 25–40% retrace and declining counter-volume.
Compression entries require positive velocity and acceleration; declining supplied
participation vetoes those entries. Supplied absorption vetoes either entry type.
All thresholds/mechanics remain hypotheses until validation; they cannot guarantee
improved entries or returns. Existing trigger extension, risk, freshness, sizing,
duplicate protection and manual arming gates still apply.
