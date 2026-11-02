"""Free-base four-wheel skid AMR: floor friction is the only planar drive force.

Genesis controls only four wheel hinges and the bounded lifting platform. The
base's six DOFs never receive pose, velocity, force, or position commands.
"""
from dataclasses import dataclass
from pathlib import Path
import math
import xml.etree.ElementTree as ET
import numpy as np

WHEEL_RADIUS = .09
TRACK = .49

@dataclass(frozen=True)
class DriveLimits:
    max_speed: float = .35
    max_yaw_rate: float = .8
    acceleration: float = .5
    yaw_acceleration: float = .9
    motor_torque: float = 6.0
    lift_force: float = 250.0
    lift_travel: float = .06


def twist_to_wheels(v, w, radius=WHEEL_RADIUS, track=TRACK):
    return (v-w*track/2)/radius, (v+w*track/2)/radius


def limited_twist(v, w, previous, dt, limits=DriveLimits()):
    if not all(math.isfinite(float(x)) for x in (v,w,dt,*previous)) or dt <= 0:
        raise ValueError('Twist and dt must be finite; dt must be positive')
    desired = (np.clip(v,-limits.max_speed,limits.max_speed), np.clip(w,-limits.max_yaw_rate,limits.max_yaw_rate))
    return tuple(float(np.clip(t,p-a*dt,p+a*dt)) for t,p,a in zip(desired,previous,(limits.acceleration,limits.yaw_acceleration)))


def _array(value):
    if hasattr(value,'detach'): value=value.detach().cpu().numpy()
    return np.asarray(value,dtype=float)


class DriveAMR:
    radius = WHEEL_RADIUS
    track = TRACK
    limits = DriveLimits()

    def __init__(self, entity):
        self.entity = entity
        self.motor_indices = [entity.get_joint(name).dofs_idx_local[0] for name in ('motor_fl','motor_rl','motor_fr','motor_rr')]
        self.lift_index = entity.get_joint('lift').dofs_idx_local[0]
        self.command = (0.,0.)
        self.lift_target = 0.
        self._configured = False
        self._pose_cache = None

    def configure(self):
        """Call after scene.build(), or let the first command configure motors."""
        if self._configured: return
        e=self.entity; idx=self.motor_indices
        e.set_dofs_kp(np.zeros(4),idx)
        e.set_dofs_kv(np.full(4,8.),idx)
        e.set_dofs_force_range(np.full(4,-self.limits.motor_torque),np.full(4,self.limits.motor_torque),idx)
        e.set_dofs_kp(np.array([20000.]),[self.lift_index])
        e.set_dofs_kv(np.array([300.]),[self.lift_index])
        e.set_dofs_force_range(np.array([-self.limits.lift_force]),np.array([self.limits.lift_force]),[self.lift_index])
        self._configured=True
        self.set_lift(0.)

    def set_twist(self,v,w,dt,emergency=False):
        self.configure()
        # Emergency removes the wheel velocity setpoint immediately; finite
        # motor torque and tire contact still determine actual stopping motion.
        self.command = (0.,0.) if emergency else limited_twist(v,w,self.command,dt,self.limits)
        left,right=twist_to_wheels(*self.command)
        self.entity.control_dofs_velocity(np.array([left,left,right,right]),self.motor_indices)
        return self.command

    def set_lift(self,height):
        if not math.isfinite(float(height)): raise ValueError('Invalid lift height')
        self.configure()
        self.lift_target=float(np.clip(height,0.,self.limits.lift_travel))
        self.entity.control_dofs_position(np.array([self.lift_target]),[self.lift_index])
        return self.lift_target

    def pose(self):
        if self._pose_cache is not None:return self._pose_cache.copy()
        return self._read_pose()

    def refresh_pose(self):
        """Sample once after each physics step; all control reads share that tick."""
        self._pose_cache=self._read_pose()
        return self._pose_cache.copy()

    def _read_pose(self):
        p=_array(self.entity.get_pos()); q=_array(self.entity.get_quat())
        qw,qx,qy,qz=q
        return dict(x=float(p[0]),y=float(p[1]),z=float(p[2]),yaw=math.atan2(2*(qw*qz+qx*qy),1-2*(qy*qy+qz*qz)))

    def state(self):
        e=self.entity
        return dict(**self.pose(), velocity=_array(e.get_vel()).tolist(),angular_velocity=_array(e.get_ang()).tolist(),
                    wheel_velocity=_array(e.get_dofs_velocity(self.motor_indices)).tolist(),
                    wheel_torque=_array(e.get_dofs_control_force(self.motor_indices)).tolist(),
                    lift_position=float(_array(e.get_dofs_position([self.lift_index]))[0]),
                    lift_force=float(_array(e.get_dofs_control_force([self.lift_index]))[0]),
                    command_v=self.command[0],command_w=self.command[1],lift_target=self.lift_target,
                    motor_indices=self.motor_indices,lift_index=self.lift_index,
                    torque_limit=self.limits.motor_torque,lift_force_limit=self.limits.lift_force,
                    drive_model='free-base four-wheel skid drive; isotropic tire friction')


def _colored_amr_xml(color):
    path=Path(__file__).resolve().parents[2]/'assets/v2/amr_drive.xml'
    root=ET.parse(path).getroot()
    rgba=' '.join(str(float(c)) for c in color[:3])+' 1'
    for name in ('chassis','platform'):
        root.find(f".//geom[@name='{name}']").set('rgba',rgba)
    return root


def build_drive_amr(scene, position=(0.,0.), yaw=0., color=(.08,.55,.95)):
    import genesis as gs
    entity=scene.add_entity(gs.morphs.MJCF(file=_colored_amr_xml(color),align=False,pos=(position[0],position[1],.095),
                                         quat=(math.cos(yaw/2),0.,0.,math.sin(yaw/2))),
                            material=gs.materials.Rigid(friction=.65),surface=gs.surfaces.Default())
    return DriveAMR(entity)



