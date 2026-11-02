"""Actual no-wall factory initial-state/support check; no AI or manufactured outcome."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from print_factory.v2_scene import build_workshop
from print_factory.scene import numpy
from PIL import Image


def main():
    out=ROOT/'output/v2/scene_printing_probe';out.mkdir(parents=True,exist_ok=True)
    f=build_workshop()
    for _ in range(150):
        for r in f.robots:r.set_twist(0.,0.,.01)
        f.gantry.step(.01)
        for m in f.machines.values():m.step(.01)
        f.scene.step()
    supported=[len(numpy(p.get_contacts(with_entity=e)['link_a']))>0 for p,e in
               zip(f.papers,[f.machines['press'].entity,f.robots[1].entity])]
    contacts=len(numpy(f.robots[0].entity.get_contacts(with_entity=f.robots[1].entity)['link_a']))
    report=dict(payload_supported=supported,robot_contacts=contacts,robots=[r.state() for r in f.robots],
                papers=[numpy(p.get_pos()).tolist() for p in f.papers],gantry=f.gantry.state())
    (out/'result.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    Image.fromarray(f.overview.render()[0]).save(out/'overview.png')
    Image.fromarray(f.overhead.render()[0]).save(out/'overhead.png')
    print(json.dumps(report,indent=2),flush=True)
    if not all(supported) or contacts:raise RuntimeError('Invalid initial physical support/separation')


if __name__=='__main__':main()
