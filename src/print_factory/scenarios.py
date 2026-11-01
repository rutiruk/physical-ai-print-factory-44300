"""Fixed demo workloads; changing job count never changes machine or robot speeds."""
from .dispatch import Job


def factory_jobs(name):
    if name=='single':
        return [Job('B',0.,350.,pages=4,description='Single A4 folded leaflet job for continuous video')]
    if name=='multi':
        return [Job('A',0.,600.,pages=8,description='Regular 8-page brochure'),
                Job('B',8.5,350.,pages=4,description='Urgent 4-page leaflet'),
                Job('C',23.7,750.,pages=4,description='Additional folded 4-page leaflet')]
    raise ValueError('Unknown factory scenario: '+str(name))


def scenario_targets(name):
    jobs=factory_jobs(name)
    return dict(jobs=len(jobs),copies=sum(j.copies for j in jobs),pushes=4*sum(j.pages//4 for j in jobs))
