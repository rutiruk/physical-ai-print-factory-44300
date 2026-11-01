"""Procedural factory geometry; assets are original, small MJCF robot models."""
from dataclasses import dataclass
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def numpy(tensor):
    return tensor.detach().cpu().numpy()


@dataclass
class FactoryScene:
    scene: object
    overhead: object
    overview: object
    bundle: object
    amr: object
    arm: object
    obstacle: object
    output_tray: object
    backend: str = 'cuda'

    def amr_position(self):
        # MJCF world root is fixed; the named vehicle link carries planar joints.
        return numpy(self.amr.get_link('amr').get_pos())

    def hold(self):
        self.amr.control_dofs_position(np.zeros(3))
        self.arm.control_dofs_position(np.array([0, 0, 0]))


def build_scene(show_viewer=False):
    import genesis as gs
    if not getattr(gs, '_initialized', False):
        gs.init(backend=gs.cuda, precision='32', logging_level='warning', seed=7)
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=0.02, substeps=2),
        rigid_options=gs.options.RigidOptions(enable_self_collision=False, max_dynamic_constraints=8),
        vis_options=gs.options.VisOptions(
            ambient_light=(0.5, 0.5, 0.5),
            show_world_frame=False,
            segmentation_level='entity',
        ),
        show_viewer=show_viewer,
    )

    def box(pos, size, color, fixed=True, collision=True):
        return scene.add_entity(
            gs.morphs.Box(pos=pos, size=size, fixed=fixed, collision=collision),
            surface=gs.surfaces.Default(color=color),
            material=gs.materials.Rigid(friction=0.8),
        )

    box((0, 0, -0.07), (7.2, 5.3, 0.12), (0.19, 0.23, 0.29))
    # Work cells sit beside the central transport lane.
    box((-2.45, 1.12, 0.5), (1.2, 0.7, 1.0), (0.32, 0.39, 0.47))
    box((-2.45, 1.12, 1.08), (1.1, 0.65, 0.16), (0.10, 0.14, 0.19))
    box((-2.45, 0.72, 0.55), (0.75, 0.15, 0.12), (0.70, 0.74, 0.80), collision=False)
    box((2.48, 0.0, 0.22), (0.72, 0.65, 0.44), (0.32, 0.39, 0.47))
    output_tray = box((2.48, 0.0, 0.47), (0.7, 0.62, 0.06), (0.65, 0.70, 0.76))
    box((2.65, 0.65, 0.55), (0.7, 0.55, 1.1), (0.32, 0.39, 0.47))
    for x in (1.15, 2.85):
        box((x, 0.55, 0.8), (0.08, 0.08, 1.6), (0.45, 0.50, 0.57))
    # Floor markings are non-colliding, decorative geometry.
    for y in (-1.75, 1.75):
        box((0, y, 0.001), (6.2, 0.018, 0.005), (0.65, 0.68, 0.68), collision=False)
    for x in np.linspace(-2.8, 2.8, 15):
        box((float(x), -0.48, 0.003), (0.18, 0.015, 0.006), (0.65, 0.68, 0.68), collision=False)

    amr = scene.add_entity(gs.morphs.MJCF(file=str(ROOT / 'assets/amr.xml')))
    arm = scene.add_entity(gs.morphs.MJCF(file=str(ROOT / 'assets/gantry.xml')))
    # Cyan transport, magenta bundle, red obstacle: learned color appearance in this toy domain.
    bundle = box((-2.0, 0, 0.58), (0.34, 0.25, 0.14), (0.75, 0.05, 0.70), fixed=False)
    obstacle = box((0, 0, -2), (0.62, 0.62, 0.60), (0.90, 0.05, 0.04))
    overhead = scene.add_camera(res=(256, 256), pos=(0, 0, 7.5), lookat=(0, 0, 0), up=(0, 1, 0), fov=55, GUI=False)
    overview = scene.add_camera(res=(960, 600), pos=(6.8, -8, 7.2), lookat=(0, 0, 0.35), fov=32, GUI=False)
    scene.build()
    amr.set_dofs_kp(np.array([1800, 1800, 900]))
    amr.set_dofs_kv(np.array([180, 180, 80]))
    arm.set_dofs_kp(np.array([1800, 1800, 1800]))
    arm.set_dofs_kv(np.array([150, 150, 150]))
    result = FactoryScene(scene, overhead, overview, bundle, amr, arm, obstacle, output_tray)
    result.hold()
    return result
