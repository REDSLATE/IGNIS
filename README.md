# Alpha Core

Separate long-equity repository extracted and rebuilt from RISEDUAL-AI-2.
**Status: tested execution foundation; NOT live-ready, connected, or deployed.**

The core ranks incoming setup batches, checks fresh broker facts, sizes each buy
at 3% of available buying power, and submits without per-trade operator confirmation
once explicitly armed. Starts disarmed every restart. No maximum-position-count rule.
No MC runtime, MongoDB, cloud-model calls, paper trading, or inherited chat approval.
SQLite records history and durable order intents; brokers remain authoritative.

## Run verification

Python 3.11+; the core uses only the standard library.

```sh
python -m unittest discover -s tests -v
```

## Integration entry point

```sh
python -m alpha.runner --adapter your_public_adapter:create --db alpha.sqlite
```

This consumes JSON arrays of Candidate objects on stdin. It does not discover stocks
or invent missing rules. A verified broker adapter and live discovery/trigger worker
must be installed before `--arm` can work. Existing Public/MooMoo source excerpts
are preserved for audit ONLY; their URLs and error fallbacks are not trusted.
The command is an integration harness, not an unattended production service.

## Retained source

`preserved/risedual_core`: all eight original pattern detectors and their schemas.
Install optional dependencies with `pip install '.[patterns]'`, then use
`PYTHONPATH=preserved` to import `risedual_core.ml.patterns`.
`preserved/ChartPatternLibrary.jsx`: original illustrated chart-pattern component.
`docs/PROVENANCE.json`: exact upstream commit.

The original detector confidence values are geometric heuristics, not calibrated
success probabilities. Detectors are not yet connected to a live scanner in this
repository. Five prior Alpha entry-pattern names are accepted policy identifiers;
this is not a claim that their missing implementations were recovered here.

## Boundaries

Only regular-session quotes supported initially, using broker bid/ask timestamps
and the 15-second policy. Adapter must supply an authoritative holiday/session
calendar. Policy spread, extension and reward/risk thresholds are provisional
engineering defaults and require operator review against recovered rules.
No shorting or options execution. No automatic retry of uncertain submissions.
Single engine process only; production needs an exclusive broker-account execution
lease to prevent legacy/new systems owning the same account. Do not run both armed.

## Remaining work before live use

1. Export saved custom rules/strategies and relevant bot configurations from the
   deployed database. GitHub does not contain those records.
2. Recover and connect the actual five Alpha trigger implementations; validate
   preserved patterns on causal, timestamped data without future-bar leakage.
3. Implement and contract-test current Public/MooMoo account, fresh quote, order,
   fractional increment, supported limit-order, client-id lookup and fill methods.
4. Add broker-backed exit protection, time exits, cancel handling and fill/position
   reconciliation; independent stops must survive worker downtime.
5. Add continuous discovery/feed, production supervisor, account lease, authenticated
   arming/status API and dashboard; session-aware pre/post/overnight policy later.
6. Historical replay with costs, outcome labeling/ranking calibration and latency
   measurements; controlled live validation only after integration review.

An acknowledgment is not a fill. Terminal order states need position reconciliation
in the adapter/service integration before this can be promoted to live operation.
