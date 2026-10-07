"""Join receipts to externally observed forward bids, including rejected signals.
Example: python -m alpha.expectancy --db alpha.sqlite --outcomes outcomes.jsonl --output report
No synthetic fills; signal observations and submit observations are separate cohorts.
"""
import argparse, csv, html, json, math, sqlite3
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

def summarize(db, outcomes, stage='signal'):
    observations={}
    for event,payload in db.execute("SELECT event,payload FROM receipts WHERE event IN ('SIGNAL','MATURITY') ORDER BY seq"):
        p=json.loads(payload)
        if p['stage']==stage and p.get('metrics'):
            # Keep first observation per candidate; duplicates don't inflate evidence.
            observations.setdefault(p['candidate'],p)
    groups=defaultdict(list)
    seen=set()
    for o in outcomes:
        if o.get('stage')!=stage: continue
        key=(o['candidate'],o['horizon_seconds'])
        if key in seen: raise ValueError('duplicate forward label')
        seen.add(key)
        if o['candidate'] not in observations: continue
        p=observations[o['candidate']];m=p['metrics']
        exit_bid,cost,horizon,exit_at=(o['exit_bid'],o['total_cost_fraction'],o['horizon_seconds'],o['exit_at'])
        if any(not math.isfinite(v) for v in (exit_bid,cost,horizon,exit_at)) or exit_bid<=0 or cost<0 or horizon<=0: raise ValueError('invalid outcome')
        entry_at=m['observed_at'] if stage=='signal' else m['observed_at']+m['snapshot_age_seconds']
        # Labels must be first executable bid at/after the specified horizon,
        # with <= one source bar delay. Require timestamped evidence.
        if not entry_at+horizon<=exit_at<=entry_at+horizon+m['timeframe_seconds']: raise ValueError('wrong outcome horizon')
        extension_bucket=math.floor(m['extension_atr'])
        age_bucket=m['bars_since_origin']//5*5
        group=(p['pattern'],m['regime'],m['feed'],m['timeframe_seconds'],horizon,extension_bucket,age_bucket)
        groups[group].append((exit_bid/m['entry_price']-1-cost)*100)
    rows=[]
    for group,values in sorted(groups.items()):
        error=1.96*stdev(values)/math.sqrt(len(values)) if len(values)>1 else None
        rows.append(dict(zip(('pattern','regime','feed','timeframe_seconds','horizon_seconds','extension_atr_floor','age_bars_floor'),group),
                         n=len(values),mean_net_pct=mean(values),approx_ci_half_width_pct=error,
                         positive_fraction=sum(v>0 for v in values)/len(values)))
    return rows

def write_report(rows, output):
    output.mkdir(parents=True,exist_ok=True)
    fields=['pattern','regime','feed','timeframe_seconds','horizon_seconds','extension_atr_floor','age_bars_floor','n','mean_net_pct','approx_ci_half_width_pct','positive_fraction']
    with (output/'expectancy.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    # Static chart: exact cohorts remain explicit rather than averaging regimes.
    limit=max([abs(r['mean_net_pct'])+(r['approx_ci_half_width_pct'] or 0) for r in rows]+[.01])
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="{max(140,100+35*len(rows))}">',
         '<rect width="100%" height="100%" fill="white"/>',
         '<text x="20" y="25">Forward net return (%) by extension and origin age</text>',
         '<text x="20" y="48">Observational cohorts; intervals are approximate and assume independent samples.</text>']
    for i,r in enumerate(rows):
        y=85+i*35
        label=f"{r['pattern']} / {r['regime']} / {r['feed']} / {r['timeframe_seconds']}s / +{r['horizon_seconds']}s | ext {r['extension_atr_floor']}–{r['extension_atr_floor']+1} ATR | age {r['age_bars_floor']}–{r['age_bars_floor']+4} | n={r['n']}"
        x=950+200*r['mean_net_pct']/limit
        svg.extend([f'<text x="15" y="{y}" font-size="11">{html.escape(label)}</text>',f'<line x1="950" x2="950" y1="{y-12}" y2="{y+5}" stroke="gray"/>',f'<circle cx="{x}" cy="{y-4}" r="4" fill="navy"/>',f'<text x="{x}" y="{y+12}" font-size="10">{r["mean_net_pct"]:.3f}%</text>'])
        if r['approx_ci_half_width_pct'] is not None:
            dx=200*r['approx_ci_half_width_pct']/limit
            svg.append(f'<line x1="{x-dx}" x2="{x+dx}" y1="{y-4}" y2="{y-4}" stroke="navy"/>')
    if not rows: svg.append('<text x="20" y="85">No joined outcomes. No cutoff or probability has been estimated.</text>')
    svg.append('</svg>');(output/'expectancy.svg').write_text('\n'.join(svg))

def main():
    p=argparse.ArgumentParser();p.add_argument('--db',required=True);p.add_argument('--outcomes',required=True);p.add_argument('--output',required=True);p.add_argument('--stage',choices=['signal','submit'],default='signal');a=p.parse_args()
    with open(a.outcomes) as f: outcomes=[json.loads(line) for line in f if line.strip()]
    with sqlite3.connect(f'file:{Path(a.db).resolve()}?mode=ro',uri=True) as db: rows=summarize(db,outcomes,a.stage)
    write_report(rows,Path(a.output))
if __name__=='__main__': main()
