# Rules and migration

## Authoritative requirements retained from operator instructions
- Equity Alpha independent of Mission Control.
- Live operation only; one arming decision, no per-trade approval when autonomous.
- 3% of broker available buying power per entry. No count-based position cap.
- Broker-authoritative positions/orders/account/fills.
- Fresh submit-time quote; idempotency, symbol inflight lock and reconciliation.
- RISE model promotion is separate from enabling the existing selector's execution.

## What must be recovered, not guessed
Custom strategies are saved by backend/routes/strategy.py into `strategies` and
`marketplace_strategies`; trading bot configuration is stored in `trading_bots`.
Obtain a read-only authenticated export from the deployed application. Exclude
credentials, user authentication records and keys. Include rule conditions,
parameters, strategy IDs and enabled state. Import only after schema validation.

## Findings in source
- run_signal_bot_dispatcher describes ~5-minute scheduling; not evidence that this
  is the current Alpha production entry path.
- Portfolio agent mandatory confirmation applies to paper proposals, not proven
  to delay live Alpha.
- Strategy generator prompt examples include max_positions=5 and 1% portfolio
  risk. Examples are not evidence those values controlled actual orders.
- Public/MooMoo legacy reads can return [] on error. Never carry that fallback
  into broker-authoritative duplicate checking.

## Replacement rollout
Keep current repository intact. Build new integrations beside it. Compare event
receipts against historical data. Stop legacy submission ownership before arming
new engine; verify exclusive account lease. Restore previous ownership only after
new engine disarmed and all outstanding broker orders reconciled.
