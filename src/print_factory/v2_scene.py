"""No-wall mechanical workshop with real wheel AMRs and one-lane equipment gap."""
from dataclasses import dataclass
import math
from .v2_vehicle import build_drive_amr
from .v2_machines import build_gantry,build_machine
from .v2_printing import build_printing_press


@dataclass
class MechanicalWorkshop:
    scene:object
    robots:list
    papers:list
    gantry:object
    machines:dict
    cabinets:list
    contact_obstacles:list
    overview:object
    overhead:object
    front:list
    goal_camera:object


def build_workshop():
    import genesis as gs
    if not getattr(gs,'_initialized',False):gs.init(backend=gs.cuda,logging_level='warning',seed=42)
    scene=gs.Scene(sim_options=gs.options.SimOptions(dt=.01,substeps=4),
                   rigid_options=gs.options.RigidOptions(enable_self_collision=False),
                   vis_options=gs.options.VisOptions(ambient_light=(.65,.65,.65),show_world_frame=False),show_viewer=False)
    contact_obstacles=[]
    def box(pos,size,color,fixed=True,mass=None,collision=True):
        entity=scene.add_entity(gs.morphs.Box(pos=pos,size=size,fixed=fixed,collision=collision),
            material=gs.materials.Rigid(friction=.65,**({'rho':mass/(size[0]*size[1]*size[2])} if mass else {})),
            surface=gs.surfaces.Default(color=color))
        if fixed and collision:contact_obstacles.append(entity)
        return entity
    scene.add_entity(gs.morphs.Plane(),material=gs.materials.Rigid(friction=.65),surface=gs.surfaces.Default(color=(.19,.23,.28)))
    box((0,0,-.006),(60,60,.01),(.19,.23,.28),collision=False)
    cabinets=[]
    for y in (-.72,.72):
        cabinets.append(box((0,y,.17),(2.8,.54,.34),(.23,.43,.49)))
        for x in (-1.2,-.6,0,.6,1.2):
            box((x,y,.345),(.035,.50,.01),(.95,.63,.15),collision=False)
    for side in (-1,1):
        box((side*1.95,-1.45,.002),(1.05,.85,.004),(.12,.37,.36),collision=False)
        for x in [side*1.95]:
            box((x,-1.45,.005),(.65,.025,.005),(.65,.87,.74),collision=False)
    for n in range(-12,13):
        box((n*.25,0,.003),(.12,.018,.004),(.74,.77,.79),collision=False)
    gantry=build_gantry(scene)
    machines={name:(build_printing_press(scene,xy) if name=='press' else build_machine(scene,name,xy)) for name,xy in
              [('press',(-2.8,1.25)),('folder',(2.8,1.25)),('trim',(-2.8,-1.25))]}
    for x,sign in [(-2.8,1),(2.8,1),(-2.8,-1)]:
        # End-on dock: the deck extends .30m along world Y. Leave45mm
        # mechanical clearance; paper spans this gap onto the fixed bridge.
        box((x,sign*.94,.375),(.62,.09,.04),(.59,.65,.69))
    for x,color in [(-3.1,(.1,.65,.75)),(-2.8,(.7,.16,.5)),(-2.5,(.87,.73,.12))]:
        box((x,1.95,.62),(.25,.38,1.24),color)
    box((2.8,1.95,.58),(.75,.38,1.16),(.12,.52,.57))
    robots=[build_drive_amr(scene,(-2.8,.55),-math.pi/2,(.08,.55,.95)),
            build_drive_amr(scene,(2.8,.55),-math.pi/2,(.65,.3,.85))]
    papers=[box((-2.8,1.25,.4),(.45,.32,.01),(.96,.94,.81),False,1.44),
            box((2.8,.55,.413),(.225,.32,.02),(.96,.87,.92),False,1.44)]
    overview=scene.add_camera(res=(1100,660),pos=(6,-8,9),lookat=(0,0,.35),fov=38,GUI=False)
    overhead=scene.add_camera(res=(768,512),pos=(0,-.2,8),lookat=(0,0,0),up=(0,1,0),fov=60,GUI=False)
    front=[scene.add_camera(res=(320,240),pos=(0,0,.67),lookat=(1,0,.60),fov=100,GUI=False) for _ in range(2)]
    goal=scene.add_camera(res=(320,240),pos=(0,0,.67),lookat=(1,0,.6),fov=100,GUI=False)
    scene.build()
    for r in robots:r.configure()
    gantry.configure()
    for m in machines.values():m.configure()
    contact_obstacles.extend([gantry.entity]+[m.entity for m in machines.values()])
    return MechanicalWorkshop(scene,robots,papers,gantry,machines,cabinets,contact_obstacles,overview,overhead,front,goal)
