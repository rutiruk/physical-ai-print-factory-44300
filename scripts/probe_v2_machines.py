"""Isolated V2 contact/actuator smoke probe; writes measured JSON and one image."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
import numpy as np
from print_factory.v2_machines import build_gantry, build_machine


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='output/v2/machines_probe')
    parser.add_argument('--cpu', action='store_true')
    args = parser.parse_args()
    import genesis as gs
    gs.init(backend=gs.cpu if args.cpu else gs.cuda, logging_level='warning', seed=41)
    scene = gs.Scene(sim_options=gs.options.SimOptions(dt=.01, substeps=4), show_viewer=False)
    scene.add_entity(gs.morphs.Plane())
    gantry = build_gantry(scene)
    machine = build_machine(scene, 'folder', (2.8, 1.25))
    # A finite mass pile on a transfer table; the pusher has to transmit contact force.
    scene.add_entity(gs.morphs.Box(pos=(-2., 0., .375), size=(1.4, .9, .04), fixed=True))
    pile = scene.add_entity(gs.morphs.Box(pos=(-2., 0., .4), size=(.45, .32, .01)),
                            material=gs.materials.Rigid(rho=100, friction=.35))
    camera = scene.add_camera(res=(960, 600), pos=(6, -7, 5), lookat=(0, 0, .6), GUI=False)
    scene.build()
    gantry.configure()
    machine.configure()
    machine.request('feed', guard_closed=True, pile_present=True)
    def run(n):
        for _ in range(n):
            gantry.step(.01)
            machine.step(.01)
            scene.step()
    run(100)
    initial = np.asarray(pile.get_pos().cpu()).tolist()
    # Pusher is X-wide; translate along Y into the rear edge of the rigid pile.
    gantry.set_target(-2., -.28, .4)
    run(400)
    gantry.set_target(-2., .03, .4)
    run(240)
    pushed = np.asarray(pile.get_pos().cpu()).tolist()
    machine.request('clamp', guard_closed=True, pile_present=True)
    run(180)
    report = dict(gantry=gantry.state(), machine=machine.state(),
                  pile_initial=initial, pile_final=pushed,
                  pile_delta_y=float(pushed[1]-initial[1]))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    report['checks'] = dict(pile_contact_transfer=report['pile_delta_y'] > .05, gantry_tracks=max(abs(v) for v in report['gantry']['tracking_error'][:3]) < .04, rollers_moved=abs(report['machine']['dof_position'][0]) > 1., clamp_moved=report['machine']['dof_position'][2] < -.05)
    (output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    from PIL import Image
    rgb, *_ = camera.render(rgb=True)
    Image.fromarray(rgb).save(output/'overview.png')
    print(json.dumps(report, indent=2))
    gs.destroy()
    if not all(report['checks'].values()):
        raise RuntimeError('physical actuator/contact probe failed; inspect report.json')


if __name__ == '__main__':
    main()


