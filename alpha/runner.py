"""Feed completed setup candidates as JSON arrays, one event batch per stdin line.
No broker included: an installed account-specific adapter must meet Broker contract.
"""
import argparse, importlib, json, sys
from .core import Candidate, Engine
from .maturity import Move, MaturityPolicy

def main():
    p=argparse.ArgumentParser();p.add_argument('--adapter',required=True,help='module:factory');p.add_argument('--db',default='alpha.sqlite');p.add_argument('--arm',action='store_true');p.add_argument('--maturity-policy',help='JSON file with scoped calibration and enforce flag');a=p.parse_args()
    module,factory=a.adapter.split(':',1)
    broker=getattr(importlib.import_module(module),factory)()
    policy=MaturityPolicy()
    if a.maturity_policy:
        with open(a.maturity_policy) as f: policy=MaturityPolicy(**json.load(f))
    engine=Engine(broker,a.db,maturity_policy=policy)
    if a.arm: engine.arm()
    for line in sys.stdin:
        if not line.strip():continue
        try:
            candidates=[]
            for item in json.loads(line):
                if item.get('move') is not None: item['move']=Move(**item['move'])
                candidates.append(Candidate(**item))
            print(json.dumps(engine.batch(candidates)),flush=True)
        except Exception as e:
            engine.disarm();print(json.dumps({'status':'ERROR','error_type':type(e).__name__}),flush=True)
    engine.disarm()
if __name__=='__main__':main()
