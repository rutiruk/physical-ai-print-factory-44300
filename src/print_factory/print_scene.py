"""Genesis workshop for sheetfed print piles, folders and saddle-stitch finishing."""
from dataclasses import dataclass
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from .scene import ROOT
from .printing import FormLot


@dataclass
class PrintWorkshop:
    scene:object
    amrs:list
    loader:object
    flat:list
    folded:list
    overhead:object
    overview:object
    obstacle:object
    ports:dict
    book_block:object
    finished:object
    supports:dict
    stock_lift:object
    gather_bridge:object
    finishing:object
    navigation_cameras:list|None=None
    corridor_camera:object=None


def build_print_workshop(navigation=False,lot_specs=None):
    import genesis as gs
    if not getattr(gs,'_initialized',False):gs.init(backend=gs.cuda,precision='32',logging_level='warning',seed=41)
    scene=gs.Scene(sim_options=gs.options.SimOptions(dt=.01,substeps=2),
                   vis_options=gs.options.VisOptions(ambient_light=(.65,.65,.65),show_world_frame=False),show_viewer=False)
    def box(pos,size,color,fixed=True,mass=None,texture=None,collision=True):
        kwargs={'color':color} if texture is None else {'diffuse_texture':gs.textures.ImageTexture(image_path=str(texture))}
        material=gs.materials.Rigid(friction=.65,**({'rho':mass/np.prod(size)} if mass else {}))
        if texture is not None:
            import trimesh
            mesh=trimesh.creation.box(extents=size)
            uv=mesh.vertices[:,:2]/np.asarray(size[:2])+.5
            mesh.visual=trimesh.visual.TextureVisuals(uv=uv,image=Image.open(texture))
            mesh_path=texture.with_name(texture.stem+f'_{size[0]}_body.obj');mesh.export(str(mesh_path))
            morph=gs.morphs.Mesh(file=str(mesh_path),pos=pos,fixed=fixed,collision=collision,convexify=True)
        else:morph=gs.morphs.Box(pos=pos,size=size,fixed=fixed,collision=collision)
        return scene.add_entity(morph,
                                surface=gs.surfaces.Default(**kwargs),material=material)
    box((0,0,-.06),(9,6,.12),(.19,.23,.29))
    if navigation:
        # Enclosed workshop and fixed landmarks, visible to the forward cameras.
        # These are scene geometry, not demonstration/training images.
        for x in (-4.4,4.4):box((x,0,1.1),(.12,6,2.2),(.68,.7,.72))
        for y in (-2.9,2.9):box((0,y,1.1),(9,.12,2.2),(.72,.74,.76))
        for x in (-3.,-1.,1.,3.):
            for y in (-2.82,2.82):
                color=(.12,.48,.65) if x<0 else (.85,.65,.18)
                box((x,y,1.),(.18,.025,1.8),color,collision=False)
    ports={'press':(-2.,1.25),'folder':(0.,1.25),'gather':(2.,1.25)}
    supports={}
    for name,(x,y) in ports.items():
        box((x,y,.175),(.8,.65,.35),(.34,.4,.47))
        if name=='press':
            stock_lift=scene.add_entity(gs.morphs.MJCF(file=str(ROOT/'assets/paper_feeder.xml'),align=False))
            supports[name]=stock_lift
            box((x,.94,.415),(.63,.298,.02),(.52,.58,.65)) # raised bridge top.425, back edge1.089
            # Passive edge hold-down guides keep a pile flat at the elevated feeder bridge.
            # The narrow central pusher passes between them; no attraction/weld acts on paper.
            for side in [-1,1]:box((x+side*.218,.99,.447),(.014,.35,.02),(.7,.73,.78))
        elif name=='gather':
            supports[name]=box((x,1.335,.3725),(1.4 if navigation else .8,.48,.045),(.72,.75,.79))
            bridge_file='gather_bridge_multi.xml' if navigation else 'gather_bridge.xml'
            gather_bridge=scene.add_entity(gs.morphs.MJCF(file=str(ROOT/'assets'/bridge_file),align=False))
        else:
            supports[name]=box((x,y,.3725),(.8,.65,.045),(.72,.75,.79)) # top .395m
            box((x,.89,.375),(.63,.19,.04),(.52,.58,.65))
        if name=='press':
            for i,c in enumerate([(.05,.75,.85),(.85,.12,.6),(.95,.83,.1),(.12,.12,.14)]):
                box((x-.48+i*.32,2.05,.65),(.27,.65,1.3),c)
            box((x,1.8,1.37),(1.7,.06,.06),(.13,.17,.22))
        elif name=='folder':
            box((x,1.7,.6),(.75,.2,1.2),(.2,.58,.62))
            for yy in [1.6,1.73]:
                scene.add_entity(gs.morphs.Cylinder(pos=(x,yy,.78),radius=.07,height=.65,euler=(0,90,0),fixed=True),
                                 surface=gs.surfaces.Default(color=(.6,.65,.69)))
        else:
            box((2.55,1.72,.57),(1.8,.25,1.14),(.25,.52,.63))
    # Nearline finishing conveyor; mechanics are simplified, state gates are in printing.py.
    finishing=box((3.2 if navigation else 2.95,1.25,.3725),(.8 if navigation else 1.1,.65,.045),(.68,.72,.76))
    for x in [2.45,3.25]:
        box((x,1.7,1.05),(.08,.08,1.4),(.65,.69,.72))
        box((x,1.25,1.74),(.08,1.,.08),(.65,.69,.72))
    for x in np.arange(-3.8,4,.35):
        box((float(x),-.15,.002),(.18,.015,.004),(.7,.73,.76),collision=False)
    amrs=[scene.add_entity(gs.morphs.MJCF(file=str(ROOT/'assets/paper_amr.xml'),align=False)) for _ in range(2)]
    loader=scene.add_entity(gs.morphs.MJCF(file=str(ROOT/'assets/paper_loader.xml'),align=False))
    assets=ROOT/'output/printing/textures';assets.mkdir(parents=True,exist_ok=True)
    flat=[];folded=[]
    for i in range(1,5):
        lot=lot_specs[i-1] if lot_specs is not None else FormLot('BROCHURE',1,i,100)
        sheet=Image.new('RGB',(450,320),'#faf9f2');d=ImageDraw.Draw(sheet)
        font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',30)
        for n,page in enumerate(lot.imposition[0]):
            xx=15+n*210
            d.rectangle((xx,12,xx+195,308),outline='#182d42',width=2)
            d.text((xx+12,24),f'{lot.job} / F{lot.form}',font=font,fill='#182d42')
            d.text((xx+60,100),str(page),font=font,fill='#182d42')
            for row in range(7):d.line((xx+15,170+row*14,xx+175,170+row*14),fill='#536373',width=2)
        for n,c in enumerate(['cyan','magenta','yellow','black']):d.rectangle((170+n*24,2,190+n*24,9),fill=c)
        path=assets/f'form{i}.png';sheet.save(path)
        flat.append(box((-2,1.25,.400+(i-1)*.01),(.45,.32,.01),None,fixed=False,mass=lot.mass_kg,texture=path))
        folded.append(box((20+i,0,.02),(.225,.32,.02),None,fixed=False,mass=lot.mass_kg,texture=path))
    obstacle=box((-1,.55,.3),(.55,.55,.6),(.93,.08,.06))
    book_block=box((30,0,.04),(.225,.32,.08),(.95,.94,.9),fixed=False,mass=5.76)
    finished=box((31,0,.04),(.210,.297,.08),(.92,.95,.96),fixed=False,mass=4.9896)
    overhead=scene.add_camera(res=(768,512),pos=(0,0,7),lookat=(0,0,0),up=(0,1,0),fov=62,GUI=False)
    overview=scene.add_camera(res=(960,600),pos=(6,-8,7),lookat=(0,.6,.35),fov=48,GUI=False)
    navigation_cameras=[scene.add_camera(res=(320,240),pos=(-2,-1.6,.65),lookat=(0,-1.6,.60),
                       fov=100,GUI=False) for _ in range(3)] if navigation else None
    corridor_camera=scene.add_camera(res=(384,128),pos=(-1,.55,2),lookat=(-1,.55,0),
                                    up=(0,1,0),fov=30,GUI=False) if navigation else None
    scene.build()
    for i,amr in enumerate(amrs):
        amr.set_dofs_kp(np.array([2200,2200,1100,50000]))
        amr.set_dofs_kv(np.array([220,220,110,600]))
        amr.set_dofs_force_range(np.array([-800,-800,-200,-300]),np.array([800,800,200,300]))
        q=np.array([-.9 if i==0 else 3.2,-1.6,0,0]);amr.set_dofs_position(q);amr.control_dofs_position(q)
    loader.set_dofs_kp(np.array([5000,5000,15000,500]));loader.set_dofs_kv(np.array([180,180,220,40]))
    loader.set_dofs_force_range(np.array([-150,-150,-150,-40]),np.array([150,150,150,40]))
    loader.set_dofs_position(np.array([-3,0,.8,0]));loader.control_dofs_position(np.array([-3,0,.8,0]))
    stock_lift.set_dofs_kp(np.array([50000.]));stock_lift.set_dofs_kv(np.array([600.]))
    stock_lift.set_dofs_force_range(np.array([-400.]),np.array([400.]))
    stock_lift.control_dofs_position(np.array([0.]))
    gather_bridge.set_dofs_kp(np.array([50000.]));gather_bridge.set_dofs_kv(np.array([500.]))
    gather_bridge.set_dofs_force_range(np.array([-400.]),np.array([400.]))
    gather_bridge.control_dofs_position(np.array([0.]))
    return PrintWorkshop(scene,amrs,loader,flat,folded,overhead,overview,obstacle,ports,book_block,finished,supports,stock_lift,gather_bridge,finishing,navigation_cameras,corridor_camera)
