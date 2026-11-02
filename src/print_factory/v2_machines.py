"""V2 force-driven portal and observable feeder/clamp mechanics.

Units: m, s, N, Nm. Rigid piles only: no ink chemistry, flexible folding,
blade cutting or manufactured paper claims. No runtime pose teleportation.
"""
from dataclasses import dataclass
from pathlib import Path
import math
import numpy as np

ASSETS = Path(__file__).resolve().parents[2] / 'assets' / 'v2'


@dataclass(frozen=True)
class GantryLimits:
    lower: tuple = (-3.4, -1.6, .4, -math.pi)
    upper: tuple = (3.4, 1.6, 1.1, math.pi)
    speed: tuple = (.6, .45, .25, 1.2)
    force: tuple = (150., 125., 120., 12.)


class GantryTrajectory:
    def __init__(self, limits=None):
        self.limits = limits or GantryLimits()
        self.command = np.array([-3., 0., 1., 0.])
        self.target = self.command.copy()

    def set_target(self, x, y, z, yaw=0):
        target = np.array([x, y, z, yaw], dtype=float)
        if not np.all(np.isfinite(target)) or np.any(target < self.limits.lower) or np.any(target > self.limits.upper):
            raise ValueError('gantry target outside finite mechanical travel')
        self.target = target

    def advance(self, dt):
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError('dt must be finite and positive')
        delta = np.asarray(self.limits.speed) * dt
        self.command += np.clip(self.target - self.command, -delta, delta)
        q = self.command.copy()
        q[2] -= 1.75
        return q


def _array(tensor):
    return tensor.detach().cpu().numpy().reshape(-1) if hasattr(tensor, 'detach') else np.asarray(tensor).reshape(-1)


class Gantry:
    def __init__(self, entity):
        self.entity = entity
        self.trajectory = GantryTrajectory()
        self.configured = False

    def configure(self):
        """Call once after scene.build; initial assembly pose only."""
        self.entity.set_dofs_kp(np.array([1800., 1600., 2600., 100.]))
        self.entity.set_dofs_kv(np.array([170., 100., 90., 10.]))
        force = np.asarray(self.trajectory.limits.force)
        self.entity.set_dofs_force_range(-force, force)
        q = self.trajectory.advance(.001)
        self.entity.set_dofs_position(q)
        self.entity.control_dofs_position(q)
        self.configured = True

    def set_target(self, x, y, z, yaw=0):
        self.trajectory.set_target(x, y, z, yaw)

    def step(self, dt):
        if not self.configured:
            raise RuntimeError('configure gantry after scene.build()')
        self.entity.control_dofs_position(self.trajectory.advance(dt))

    def state(self):
        q = _array(self.entity.get_dofs_position()).copy()
        q[2] += 1.75
        velocity = _array(self.entity.get_dofs_velocity())
        force = _array(self.entity.get_dofs_control_force())
        limits = self.trajectory.limits
        error = self.trajectory.target - q
        return dict(pose=q.tolist(), velocity=velocity.tolist(), target=self.trajectory.target.tolist(),
                    command=self.trajectory.command.tolist(), tracking_error=error.tolist(),
                    force=force.tolist(), force_saturated=(np.abs(force) >= np.asarray(limits.force)*.98).tolist(),
                    lower=list(limits.lower), upper=list(limits.upper), speed_limit=list(limits.speed),
                    force_limit=list(limits.force), overspeed=(np.abs(velocity) > np.asarray(limits.speed)*1.15).tolist())


def build_gantry(scene):
    import genesis as gs
    return Gantry(scene.add_entity(gs.morphs.MJCF(file=str(ASSETS / 'gantry.xml'), align=False)))


class MachineCycle:
    """Guard/pile permissives and overload latch; no physical sheet conversion."""
    def __init__(self, kind):
        if kind not in ('press', 'folder', 'trim'):
            raise ValueError('unknown machine kind')
        self.kind = kind
        self.roller_velocity = 0.
        self.clamp_target = 0.
        self.fault = None
        self.mode = 'idle'

    def request(self, mode, *, guard_closed=False, pile_present=False):
        if mode not in ('feed', 'clamp', 'release', 'stop', 'reset'):
            raise ValueError('unknown machine operation')
        if mode in ('feed', 'clamp'):
            if self.fault:
                raise ValueError('reset latched machine fault first')
            if not guard_closed:
                raise ValueError('guard must be closed')
            if not pile_present:
                raise ValueError('pile must be present')
        self.mode = mode
        self.roller_velocity = -4. if mode == 'feed' else 0.
        if mode == 'clamp':
            self.clamp_target = -.065
        elif mode in ('release', 'reset'):
            self.clamp_target = 0.
        if mode == 'reset':
            self.fault = None

    def observe_load(self, roller_torque):
        if abs(roller_torque) >= 7.8:
            self.fault = 'roller_overload'
            self.roller_velocity = 0.
            self.mode = 'fault'


class MachineActuator:
    def __init__(self, entity, kind):
        self.entity = entity
        self.cycle = MachineCycle(kind)
        self.configured = False
        self.clamp_command = 0.
        self.overload_seconds = 0.

    def configure(self):
        self.entity.set_dofs_kp(np.array([0., 0., 6000.]))
        self.entity.set_dofs_kv(np.array([2., 2., 180.]))
        self.entity.set_dofs_force_range(np.array([-8., -8., -250.]), np.array([8., 8., 250.]))
        self.configured = True

    def request(self, mode, **permissives):
        self.cycle.request(mode, **permissives)

    def step(self, dt):
        if not self.configured:
            raise RuntimeError('configure machine after scene.build()')
        if not math.isfinite(dt) or dt <= 0:
            raise ValueError('dt must be finite and positive')
        forces = _array(self.entity.get_dofs_control_force())
        self.overload_seconds = self.overload_seconds + dt if max(abs(forces[:2])) >= 7.8 else 0.
        if self.overload_seconds >= .25:
            self.cycle.observe_load(float(max(abs(forces[:2]))))
        self.clamp_command += float(np.clip(self.cycle.clamp_target-self.clamp_command, -.06*dt, .06*dt))
        self.entity.control_dofs_velocity(np.array([self.cycle.roller_velocity]*2), dofs_idx_local=[0, 1])
        self.entity.control_dofs_position(np.array([self.clamp_command]), dofs_idx_local=[2])

    def state(self):
        return dict(kind=self.cycle.kind, mode=self.cycle.mode, fault=self.cycle.fault,
                    dof_position=_array(self.entity.get_dofs_position()).tolist(),
                    dof_velocity=_array(self.entity.get_dofs_velocity()).tolist(),
                    force=_array(self.entity.get_dofs_control_force()).tolist(),
                    roller_target=self.cycle.roller_velocity, clamp_target=self.cycle.clamp_target,
                    clamp_travel=[-.065, 0.], roller_torque_limit=8., clamp_force_limit=250.,
                    process_model='rigid contact and driven rollers/clamp; ink/folding/cutting not modeled')


def machine_yaw(kind, yaw=None):
    value = (math.pi if kind == 'trim' else 0.) if yaw is None else float(yaw)
    if not math.isfinite(value):
        raise ValueError('machine yaw must be finite')
    return value


def build_machine(scene, kind, origin, yaw=None):
    import genesis as gs
    pos = tuple(origin) if len(origin) == 3 else (*origin, 0.)
    angle = machine_yaw(kind, yaw)
    entity = scene.add_entity(gs.morphs.MJCF(file=str(ASSETS / 'machine.xml'), pos=pos,
                                           quat=(math.cos(angle/2), 0., 0., math.sin(angle/2)), align=False))
    return MachineActuator(entity, kind)


