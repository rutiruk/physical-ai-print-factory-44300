"""Inference-only traffic-choice calibration on recorded actual factory RGB."""
from pathlib import Path
import sys,json,copy
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'vendor/jeff/src')]
from print_factory.jeff_policy import JeffPolicy


def main():
    latest=json.loads((ROOT/'output/v2/latest_run.json').read_text())
    run=json.loads((Path(latest['folder'])/'result.json').read_text())
    decision=run['decisions'][0];image=decision['image_path']
    policy=JeffPolicy(ROOT/'models/jeff-2b-v1.2','cuda:1');trials=[]
    for urgent in ('B','A'):
        state=copy.deepcopy(decision['observation'])
        due={'A':100 if urgent=='A' else 180,'B':100 if urgent=='B' else 180}
        state['objective']='Both passage orders are physically safe after withdrawal. Minimize the time until the more urgent lower-deadline WIP reaches its downstream machine. Do not prefer candidate order or a robot color.'
        for row in state['robots']:row['due']=due[row['job']]
        candidates=[dict(id=f'priority_{i}',description=
            f'FIRST deliver job{("A","B")[i]} (deadline {due[("A","B")[i]]}s, '
            f'{("printed stock to folder","folded stock to trimmer")[i]}) on AMR{i+1}. '
            f'AMR{2-i} carrying job{("B","A")[i]} (deadline {due[("B","A")[i]]}s) withdraws and waits, so its delivery is delayed.') for i in (0,1)]
        candidates+=[dict(id='hold',description='Keep both loaded robots stopped. Neither deadline advances; no physical obstruction is cleared.')]
        for text_only in (False,True):
            result=policy._decide_once(image,state,candidates,text_only=text_only)
            trials.append(dict(urgent=urgent,text_only=text_only,**result))
            path=ROOT/'output/v2/jeff_traffic_probe.json';path.write_text(json.dumps(dict(trials=trials),indent=2),encoding='utf8')
            print(json.dumps(dict(urgent=urgent,text_only=text_only,choice=result['choice'],probabilities=result['probabilities'],latency_ms=result['latency_ms'])),flush=True)


if __name__=='__main__':main()
