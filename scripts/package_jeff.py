"""Allowlisted Jeff factory submission; excludes environments and model weights."""
from pathlib import Path
import hashlib,json,zipfile
ROOT=Path(__file__).resolve().parents[1]


def main():
    result=json.loads((ROOT/'output/jeff_factory/jeff/result.json').read_text(encoding='utf-8'))
    if not (result.get('success') and result.get('status')=='complete'):
        raise RuntimeError('Cannot package an unverified factory run as final submission')
    names=['README.md','README_JEFF.md','SUBMISSION.md','THIRD_PARTY.md','.gitignore','pyproject.toml',
           'requirements.txt','requirements-local-lock.txt','requirements-jeff.txt','requirements-navigation.txt','run.ps1','run-jeff.ps1','setup-jeff-factory.ps1']
    names += [f'src/print_factory/{n}.py' for n in ['__init__','scene','printing','print_scene','dispatch',
              'video','json_worker','jeff_policy','navigation_policy','navigation_guard','navigation_motion','factory_dashboard','run_artifacts']]
    names += [f'assets/{n}.xml' for n in ['paper_amr','paper_loader','paper_feeder','gather_bridge','gather_bridge_multi']]
    names += ['assets/navigation/README.md','assets/navigation/manifest.json']
    names += [f'scripts/{n}.py' for n in ['jeff_factory_demo','jeff_worker','navigation_worker','nav_factory_probe','dock_navigation_probe',
               'navigation_probe','setup_jeff','jeff_probe','jeff_probe_roi','compose_jeff_video',
               'summarize_jeff_factory','compose_amr_motion_check','report_jeff','report','package_jeff','check_jeff_artifacts']]
    names += ['scripts/setup_navigation.ps1']
    names += [f'tests/test_{n}.py' for n in ['printing','dispatch','dynamic_dispatch','jeff_policy',
               'navigation_policy','navigation_guard','navigation_motion','factory_dashboard','jeff_video','jeff_artifacts','run_artifacts']]
    names += ['docs/superpowers/specs/2026-11-01-jeff-factory-design.md',
              'docs/superpowers/plans/2026-11-01-jeff-factory.md','docs/superpowers/README_JEFF_RUNTIME.md',
              'docs/superpowers/specs/2026-11-01-print-process-design.md',
              'docs/superpowers/README_ROBOBRAIN_HISTORY.md','docs/superpowers/SUBMISSION_ROBOBRAIN_HISTORY.md']
    names += ['models/jeff-2b-v1.2/factory_provenance.json','models/jeff-2b-v1.2/LICENSE',
              'vendor/jeff/LICENSE','vendor/visualnav-transformer/LICENSE','vendor/diffusion_policy/LICENSE',
              'output/PrintFactory_Jeff_report.pdf','output/説明資料_PAI最終課題_44300.pdf','output/jeff_factory/evaluation.json',
              'output/jeff_factory/artifact_check.json','output/jeff_factory/jeff/result.json',
              'output/jeff_factory/jeff/video_edit.json','output/jeff_factory/jeff/motion_samples.json','output/jeff_factory/jeff/motion_audit.json','output/jeff_factory/jeff/handoff_motion_check.json','output/jeff_factory/jeff/motion_clip.json','output/jeff_factory/jeff/completed_jeff.png',
              'output/jeff_factory/tests-final.log']
    names += [f'output/jeff_factory/{name}.json' for name in ['jeff_probe_controlled','jeff_probe_2b_controlled',
              'jeff_probe_2b_roi','jeff_probe_2stage','jeff_probe_wait_modalities','jeff_probe_recovery_finish',
              'navigation_probe_forward_rgb','navigation_protocol_probe']]
    names += ['output/printing/comparison_clear.png','output/printing/comparison_blocked.png',
              'output/jeff_factory/jeff_probe_roi_clear.png','output/jeff_factory/jeff_probe_roi_blocked.png']
    names += [str(p.relative_to(ROOT)).replace('\\','/') for p in (ROOT/'output/jeff_factory/probe_inputs').glob('*') if p.is_file()]
    names += ['output/jeff_factory/dock_probe/centered_fixed/result.json',
              'output/jeff_factory/dock_probe/recorded_fixed/result.json',
              'output/jeff_factory/jeff/failed_dock_capture.json','output/jeff_factory/jeff/failed_boundary_before_recovery.json']
    # Decision cameras are evidence, whereas high-frequency nav images remain local.
    for decision in result.get('decisions',[]):
        for key in ('image_path','corridor_image_path'):
            if key in decision:names.append(str(Path(decision[key]).relative_to(ROOT)).replace('\\','/'))
    for model in ('vint','nomad'):
        sample=next(row for row in result['navigation'] if row['model']==model)
        for value in [*sample['observation_paths'],sample['goal_path']]:
            names.append(str(Path(value).relative_to(ROOT)).replace('\\','/'))
    files=sorted(set(names));manifest={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files}
    manifest_path=ROOT/'output/jeff_factory/source_manifest.json'
    manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    files.append(str(manifest_path.relative_to(ROOT)))
    path=ROOT/'output/submission_jeff_code.zip'
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for name in files:z.write(ROOT/name,name)
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        assert all(not n.endswith(('.pth','.safetensors')) for n in z.namelist())
        assert all(not (n.startswith('docs/') and n.endswith(('.pdf','.zip'))) for n in z.namelist())
        for name,digest in manifest.items():assert hashlib.sha256(z.read(name)).hexdigest()==digest
    print(json.dumps(dict(path=str(path),members=len(files),bytes=path.stat().st_size,sha256=hashlib.sha256(path.read_bytes()).hexdigest())))


if __name__=='__main__':main()
