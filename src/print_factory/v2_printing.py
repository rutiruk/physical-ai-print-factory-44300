"""Connected rigid-paper WIP tickets and a process-specific roller printing press.

Ink appearance, flexible folding and cutting are process-state approximations;
contact, roller motion and finishing clamp motion are measured prerequisites.
"""
from dataclasses import dataclass, field
import math
import xml.etree.ElementTree as ET
import numpy as np
from .v2_machines import ASSETS, MachineCycle


@dataclass
class PrintJob:
    job_id: str
    stage: str = 'raw'
    copies: int = 100
    mass_kg: float = 1.44
    ink_coverage: float = 0.
    history: list = field(default_factory=list)

    def __post_init__(self):
        if self.stage not in ('raw','printed','folded','finished'):
            raise ValueError('unknown rigid-paper WIP stage')
        if self.stage!='raw':self.ink_coverage=1.

    def record_operation(self, kind, *, paper_supported, roller_delta=0., clamp_displacement=0.):
        transitions={'press':('raw','printed'),'folder':('printed','folded'),'trim':('folded','finished')}
        if kind not in transitions or self.stage!=transitions[kind][0]:
            raise ValueError('operation does not follow connected WIP sequence')
        if not paper_supported:
            raise ValueError('paper must physically contact process machine')
        if not all(math.isfinite(float(v)) for v in (roller_delta,clamp_displacement)):
            raise ValueError('nonfinite process evidence')
        if kind in ('press','folder') and abs(roller_delta)<.35:
            raise ValueError('measured roller rotation insufficient')
        if kind in ('folder','trim') and abs(clamp_displacement)<.015:
            raise ValueError('measured clamp stroke insufficient')
        before=self.stage;self.stage=transitions[kind][1]
        if kind=='press':self.ink_coverage=1.
        self.history.append(dict(machine=kind,before=before,after=self.stage,
                                 roller_delta=float(roller_delta),clamp_displacement=float(clamp_displacement),
                                 process_model='ink appearance/folding/cutting are state approximation; measured rigid-contact mechanics'))
        return self.stage

    def state(self):
        return dict(job_id=self.job_id,stage=self.stage,copies=self.copies,mass_kg=self.mass_kg,ink_coverage=self.ink_coverage,
                    history=list(self.history),paper_model='rigid WIP; ink/fold/cut appearance is a state approximation')


def printing_press_xml():
    """Keep the actual feeder drive; finishing clamp is not a printing actuator."""
    root=ET.parse(ASSETS/'machine.xml').getroot()
    root.set('model','roller_printing_press')
    frame=root.find('worldbody/body')
    for element in list(frame):
        name=element.get('name','')
        if name=='clamp' or name.startswith('clamp_'):
            frame.remove(element)
    return root


def _array(value):
    return value.detach().cpu().numpy().reshape(-1) if hasattr(value,'detach') else np.asarray(value).reshape(-1)


class PrintingPress:
    def __init__(self,entity):
        self.entity=entity
        self.cycle=MachineCycle('press')
        self.configured=False
        self.overload_seconds=0.

    def configure(self):
        self.entity.set_dofs_kp(np.zeros(2))
        self.entity.set_dofs_kv(np.full(2,2.))
        self.entity.set_dofs_force_range(np.full(2,-8.),np.full(2,8.))
        self.configured=True

    def request(self,mode,**permissives):
        if mode in ('clamp','release'):
            raise ValueError('printing press has roller feed, not a finishing clamp')
        self.cycle.request(mode,**permissives)

    def step(self,dt):
        if not self.configured:raise RuntimeError('configure press after scene.build()')
        if not math.isfinite(dt) or dt<=0:raise ValueError('dt must be finite and positive')
        force=_array(self.entity.get_dofs_control_force())
        self.overload_seconds=self.overload_seconds+dt if max(abs(force))>=7.8 else 0.
        if self.overload_seconds>=.25:self.cycle.observe_load(float(max(abs(force))))
        self.entity.control_dofs_velocity(np.full(2,self.cycle.roller_velocity))

    def state(self):
        return dict(kind='press',mode=self.cycle.mode,fault=self.cycle.fault,
                    dof_position=_array(self.entity.get_dofs_position()).tolist(),
                    dof_velocity=_array(self.entity.get_dofs_velocity()).tolist(),
                    force=_array(self.entity.get_dofs_control_force()).tolist(),
                    roller_target=self.cycle.roller_velocity,roller_torque_limit=8.,
                    clamp_present=False,process_model='driven roller contact; ink coverage is an explicit state approximation')


def build_printing_press(scene,origin):
    import genesis as gs
    pos=tuple(origin) if len(origin)==3 else (*origin,0.)
    return PrintingPress(scene.add_entity(gs.morphs.MJCF(file=printing_press_xml(),pos=pos,align=False)))
