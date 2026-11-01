"""Audit saved evidence, without inventing a success from an incomplete run."""
import json,math,statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def quantiles(values):
    values=sorted(values)
    return {'count':len(values),'median_ms':statistics.median(values) if values else None,
            'p95_ms':values[max(0,math.ceil(.95*len(values))-1)] if values else None}


def summarize(path):
    data=json.loads(path.read_text(encoding='utf-8'));events=data.get('events',[])
    decisions=data.get('decisions',[]);moves=data.get('navigation',[])
    state=data.get('state',{});jobs=state.get('jobs',[])
    pushes=[e for e in events if e['event']=='PHYSICAL_PUSH']
    complete=[j for j in jobs if j.get('completed') is not None]
    return dict(status=data['status'],success=data['success'],simulation_seconds=data.get('simulation_seconds'),
        wall_seconds=data.get('wall_seconds'),arrivals=[e for e in events if e['event']=='JOB_ARRIVAL'],
        jobs_completed=len(complete),jobs_observed=len(jobs),units_completed=sum(j['copies'] for j in complete),
        booklets_completed=sum(j['copies'] for j in complete if j['pages']>=8),
        leaflets_completed=sum(j['copies'] for j in complete if j['pages']==4),
        navigation_recoveries=sum(e['event']=='NAV_RECOVERY_CHOSEN' for e in events),
        tardiness_seconds={j['id']:max(0,j['completed']-j['due']) for j in complete},
        physical_pushes=len(pushes),supported_pushes=sum(e['supported'] for e in pushes),
        stale_rejections=sum(e['event']=='STALE_DECISION_REJECTED' for e in events),
        dispatch_latency=quantiles([d['latency_ms'] for d in decisions]),
        vision_latency=quantiles([d['visual']['latency_ms'] for d in decisions if 'visual' in d]),
        navigation={model:dict(inferences=len([m for m in moves if m['model']==model]),
                              latency=quantiles([m['latency_ms'] for m in moves if m['model']==model]))
                    for model in ('vint','nomad')},
        alternatives_per_decision=[len(d.get('candidates',[])) for d in decisions],
        choices=[dict(time_s=d['time_s'],choice=d['choice']) for d in decisions],
        claims={'training':'none','speed_superiority':'not established',
                'visual_generalization':'not established; controlled pair only',
                'physical_ai_necessity':'not established; classical navigation could solve known-map transport'})


if __name__=='__main__':
    out=ROOT/'output/jeff_factory';report={}
    for policy in ('jeff_single','jeff','rules'):
        path=out/policy/'result.json'
        if path.exists():report[policy]=summarize(path)
    report['primary']='jeff_single'
    report['comparison_note']='No controlled matched comparison establishes AI necessity or speed superiority. The saved rule-reference run was interrupted during motion-controller repairs; its incomplete count must not be compared as a completed benchmark.'
    (out/'evaluation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
