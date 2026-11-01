"""Audit final Jeff evidence only after simulation, edit, and report finish.

The approved legacy annotation identifies mutable metadata; it does not reconstruct
model inputs or change decisions, probabilities, events, or rendered video.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from print_factory.scenarios import scenario_targets
LEGACY_NOTE = ('not an immutable input capture; actual candidates/image hashes and '
               'event log retained; new source fix covered by unit-test. '
               'live_state_metadata contains legacy references to mutable world metadata, '
               'not reconstructed exact model inputs.')
BUNDLED_PYTHON = Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8*1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def annotate_legacy_observations(result):
    if result.get('immutable_observation_snapshot') is True:
        return False
    changed = False
    for decision in result.get('decisions', []):
        if decision.get('immutable_observation_snapshot') is not True and 'observation' in decision:
            decision['live_state_metadata'] = decision.pop('observation')
            decision['observation_capture_warning'] = LEGACY_NOTE
            changed = True
    if changed:
        result['observation_history_note'] = LEGACY_NOTE
    return changed


def check_summary(result):
    errors = []
    try:target=scenario_targets(result.get('scenario','multi'))
    except ValueError:
        errors.append('Unknown factory scenario');target=scenario_targets('multi')
    if result.get('success') is not True or result.get('status') != 'complete':
        errors.append('Run must have success=true and status=complete')
    jobs = result.get('state', {}).get('jobs', [])
    completed = [job for job in jobs if job.get('completed') is not None]
    copies = sum(job.get('copies', 0) for job in completed)
    if len(jobs) != target['jobs'] or len(completed) != target['jobs'] or copies != target['copies']:
        errors.append(f"Expected {target['jobs']} completed jobs totaling {target['copies']} copies")
    pushes = [event for event in result.get('events', []) if event.get('event') == 'PHYSICAL_PUSH']
    if len(pushes) != target['pushes']:
        errors.append(f"Expected {target['pushes']} PHYSICAL_PUSH events, got {len(pushes)}")
    if not all(event.get('supported') is True for event in pushes):
        errors.append('Every physical push must have supported=true')
    counts = {name: sum(str(row.get('model', '')).lower() == name for row in result.get('navigation', []))
              for name in ('vint', 'nomad')}
    if not all(counts.values()):
        errors.append('Both ViNT and NoMaD must have actual navigation inference records')
    finished={e.get('job'):e for e in result.get('events',[]) if e.get('event')=='PROCESS_COMPLETE' and e.get('machine')=='finishing'}
    for job in jobs:
        item=finished.get(job.get('id'),{})
        expected='fold_only' if job.get('pages')==4 else 'saddle_stitch'
        if item.get('binding')!=expected or item.get('stitched')!=(expected=='saddle_stitch'):
            errors.append(f'Finishing recipe mismatch for {job.get("id")}: leaflet must bypass wire, booklet requires stitching')
    return dict(errors=errors, jobs=len(jobs), completed_jobs=len(completed), completed_copies=copies,
                physical_pushes=len(pushes), supported_pushes=sum(e.get('supported') is True for e in pushes),
                navigation_model_counts=counts)


def _resolve_image(value, folder):
    path = Path(value)
    if path.exists():
        return path
    relocated = folder/path.name
    if relocated.exists():
        return relocated
    raise FileNotFoundError(path)


def continuous_errors(edit,simulation_seconds):
    errors=[]
    for key,value in dict(continuous=True,playback_speed=2,source_fps=20,fps=40,
                          cuts=[],dropped_frames=0,interpolated_frames=0,closing_summary_seconds=0,
                          source_sim_first_frame_s=.05,sim_frame_step_s=.05).items():
        if edit.get(key)!=value:errors.append('Continuous video invalid '+key)
    count=edit.get('frame_count',0)
    if not count or count!=edit.get('source_frame_count'):errors.append('Continuous video omitted source frames')
    if abs(count/20-simulation_seconds)>1e-6:errors.append('Continuous source frames do not span the full SIM clock')
    keep=edit.get('keep',[])
    if len(keep)!=1 or len(keep[0])!=2 or abs(keep[0][0])>1e-6 or abs(keep[0][1]-simulation_seconds)>1e-6:
        errors.append('Continuous video must keep the entire run')
    if abs(edit.get('duration_seconds',0)*2-simulation_seconds)>1e-6:errors.append('Continuous playback does not match SIM duration')
    if abs(edit.get('source_sim_last_frame_s',0)-simulation_seconds)>1e-6:errors.append('Continuous final frame is missing')
    return errors


def check(folder, video, pdf, destination):
    sys.path.insert(0, str(ROOT/'src'))
    from print_factory.run_artifacts import write_result
    result_path = folder/'result.json'
    result = json.loads(result_path.read_text(encoding='utf-8'))
    # Never modify a live or failed run, nor overwrite its evidence from this audit.
    if result.get('status') != 'complete' or result.get('success') is not True:
        report = check_summary(result)
        write_result(destination, dict(success=False, **report))
        raise RuntimeError('Run is not successfully complete; artifact audit refused')
    annotated = annotate_legacy_observations(result)
    if annotated:
        write_result(result_path, result)
    report = check_summary(result)
    errors, hashes = report['errors'], {}
    report.update(legacy_observation_annotation_applied=annotated, hashes=hashes)

    def attempt(label, action):
        try:
            return action()
        except Exception as exc:
            errors.append(f'{label}: {type(exc).__name__}: {exc}')
            return None

    def verify_file(path, expected=None):
        digest = sha256(path)
        hashes[str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path)] = digest
        if expected is not None and digest != expected:
            raise ValueError(f'SHA256 mismatch: {path.name}')
        return digest

    attempt('result hash', lambda: verify_file(result_path))
    if result.get('motion_control'):
        def check_motion():
            from print_factory.navigation_motion import motion_summary,handoff_speeds
            path=folder/'motion_samples.json'
            samples=json.loads(path.read_text(encoding='utf-8'))
            summary=motion_summary(samples,result['events'])
            if not samples or not summary['adjacent_physics_ticks']:
                errors.append('No physics-rate learned-motion samples')
            if summary['linear_limit_violations'] or summary['angular_limit_violations']:
                errors.append('Learned-motion acceleration limit violated')
            if not summary['internal_nodes_without_stop'] or summary['internal_nodes_with_nonzero_command']!=summary['internal_nodes_without_stop']:
                errors.append('Internal collinear image-goal handoffs must retain nonzero commands')
            handoffs=handoff_speeds(samples,result['events'])
            if any(item['minimum_measured_speed'] is None or item['minimum_measured_speed']<=.01 for item in handoffs):
                errors.append('Actual position evidence missing or body stopped at an internal goal handoff')
            summary['measured_handoff_speed_min_m_s']=min((item['minimum_measured_speed'] for item in handoffs if item['minimum_measured_speed'] is not None),default=0.)
            write_result(folder/'handoff_motion_check.json',handoffs)
            verify_file(folder/'handoff_motion_check.json')
            report['motion']=summary
            verify_file(path)
            write_result(folder/'motion_audit.json',summary)
            verify_file(folder/'motion_audit.json')
        attempt('motion smoothing',check_motion)
    nav_metadata = result.get('models', {}).get('navigation', {}).get('models', {})
    for model in ('vint', 'nomad'):
        metadata = nav_metadata.get(model, {})
        if metadata.get('strict_weights') is not True or not metadata.get('checkpoint_sha256'):
            errors.append(f'{model}: missing strict_weights=true or checkpoint SHA256')
        else:
            attempt(f'{model} checkpoint', lambda m=model, md=metadata: verify_file(ROOT/f'assets/navigation/{m}.pth', md['checkpoint_sha256']))
    for index, row in enumerate(result.get('navigation', [])):
        model = str(row.get('model', '')).lower()
        if row.get('strict_weights') is not True or row.get('checkpoint_sha256') != nav_metadata.get(model, {}).get('checkpoint_sha256'):
            errors.append(f'Navigation record {index}: inconsistent strict model provenance')

    jeff = result.get('models', {}).get('jeff', {}).get('model', {})
    expected = jeff.get('checkpoint_sha256', {})
    provenance_files = list((ROOT/'models').glob('*/factory_provenance.json'))
    matching = []
    for path in provenance_files:
        metadata = json.loads(path.read_text(encoding='utf-8'))
        if metadata.get('id') == jeff.get('id') and metadata.get('revision') == jeff.get('revision'):
            matching.append(path)
    if not expected or not matching or not jeff.get('vendor_revision'):
        errors.append('Jeff checkpoint hashes/revision/vendor provenance missing or unavailable')
    else:
        provenance = matching[0]
        attempt('Jeff provenance', lambda: verify_file(provenance))
        for filename, digest in expected.items():
            attempt(f'Jeff {filename}', lambda p=provenance.parent/filename, d=digest: verify_file(p, d))

    decisions = result.get('decisions', [])
    report['jeff_decisions'] = len(decisions)
    report['visual_decisions'] = 0
    if not decisions:
        errors.append('No actual Jeff decisions recorded')
    for index, decision in enumerate(decisions):
        candidates = {candidate['id'] for candidate in decision.get('candidates', [])}
        if decision.get('choice') not in candidates:
            errors.append(f'Jeff decision {index}: chosen action absent from actual candidates')
        planning = decision.get('planning', decision)
        if planning.get('image_used') is not False or 'image' in planning.get('modalities', []):
            errors.append(f'Jeff decision {index}: planning must honestly record image_used=false')
        attempt(f'Jeff decision {index} planning image hash', lambda d=decision, p=planning:
                verify_file(_resolve_image(d['image_path'], folder), p['image_sha256']))
        if 'visual' in decision:
            visual = decision['visual']
            report['visual_decisions'] += 1
            if visual.get('image_used') is not True or 'image' not in visual.get('modalities', []):
                errors.append(f'Jeff visual decision {index}: actual image modality missing')
            attempt(f'Jeff decision {index} corridor image hash', lambda d=decision, v=visual:
                    verify_file(_resolve_image(d['corridor_image_path'], folder), v['image_sha256']))
    if report['visual_decisions'] == 0:
        errors.append('No actual Jeff visual decisions recorded')

    def check_edit():
        edit_path = folder/'video_edit.json'
        edit = json.loads(edit_path.read_text(encoding='utf-8'))
        if edit.get('playback_speed') != 2:
            errors.append('Video edit must be 2x playback')
        if result.get('scenario')=='single':
            errors.extend(continuous_errors(edit,result['simulation_seconds']))
            verify_file(folder/'factory_raw.mp4',edit.get('source_sha256'))
            verify_file(result_path,edit.get('result_sha256'))
            if not edit.get('source_sha256') or not edit.get('result_sha256'):
                errors.append('Continuous source/result hashes are required')
        keep = edit.get('keep', [])
        starts = {}
        for event in sorted(result['events'], key=lambda e: e['time_s']):
            if event['event'] == 'PHYSICAL_PUSH_START':
                starts[event.get('amr', 0)] = float(event['time_s'])
            if event['event'] != 'PHYSICAL_PUSH':
                continue
            end = float(event['time_s'])
            start = starts.pop(event.get('amr', 0), max(0, end-5))
            if not any(a <= start+1e-6 and b >= end-1e-6 for a,b in keep):
                errors.append(f'Full push interval {start:.2f}–{end:.2f}s omitted')
        for event in result['events']:
            if event['event'] == 'JOB_ARRIVAL' and not any(a <= event['time_s']+.05 and b >= event['time_s'] for a,b in keep):
                errors.append(f"Arrival {event.get('job')} omitted")
        verify_file(edit_path)
        report['edit'] = {'keep_intervals': len(keep), 'cuts': len(edit.get('cuts', [])),
                          'frame_count': edit.get('frame_count'), 'duration_seconds': edit.get('duration_seconds')}
        return edit
    edit = attempt('edit manifest', check_edit)

    def check_video():
        import av
        count = 0
        with av.open(str(video)) as source:
            rate = float(source.streams.video[0].average_rate)
            expected_rate=40 if edit and edit.get('continuous') else 20
            if abs(rate-expected_rate) > .001:
                errors.append(f'Video FPS is {rate}, expected {expected_rate}')
            for frame in source.decode(video=0):
                if frame.width != 1440 or frame.height != 900:
                    raise ValueError('Video frame dimensions must all be 1440x900')
                if edit and edit.get('continuous') and abs(float(frame.time)-count/40)>1e-6:
                    raise ValueError('Continuous output timestamps skip frames')
                count += 1
        duration = count/rate
        report['video'] = dict(frame_count=count, fps=rate, duration_seconds=duration, all_frames_decoded=True)
        if not 1 <= duration <= 180:
            errors.append(f'Video duration {duration:.3f}s outside 1–180s')
        if edit and (edit.get('frame_count') != count or abs(edit.get('duration_seconds', 0)-duration) > .001):
            errors.append('Decoded video frame count/duration disagree with edit manifest')
        verify_file(video)
        if edit and edit.get('continuous'):
            source_count=0
            with av.open(str(folder/'factory_raw.mp4')) as source:
                if abs(float(source.streams.video[0].average_rate)-20)>.001:
                    raise ValueError('Continuous input is not 20 fps')
                for frame in source.decode(video=0):
                    if abs(float(frame.time)-source_count/20)>1e-6:
                        raise ValueError('Continuous source timestamps skip frames')
                    source_count+=1
            if source_count!=count:errors.append('Source and output frame counts differ; continuous video may omit frames')
            report['video'].update(source_frame_count=source_count,all_source_frames_retained=source_count==count,
                                   sim_clock_step_s=.05,continuous=True)
    attempt('video', check_video)

    def check_pdf():
        try:
            from pypdf import PdfReader
            pages = len(PdfReader(str(pdf)).pages)
        except ImportError:
            command = [str(BUNDLED_PYTHON), '-c', 'import sys; from pypdf import PdfReader; print(len(PdfReader(sys.argv[1]).pages))', str(pdf)]
            pages = int(subprocess.check_output(command, text=True).strip())
        report['pdf_pages'] = pages
        if pages != 3:
            errors.append(f'Expected 3 PDF pages, got {pages}')
        verify_file(pdf)
    attempt('PDF', check_pdf)
    report['success'] = not errors
    write_result(destination, report)
    if errors:
        raise RuntimeError('Artifact checks failed: '+ '; '.join(errors))
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, default=ROOT/'output/jeff_factory/jeff_single')
    parser.add_argument('--video', type=Path, default=ROOT/'output/PrintFactory_Jeff_demo_44300.mp4')
    parser.add_argument('--pdf', type=Path, default=ROOT/'output/PrintFactory_Jeff_report.pdf')
    parser.add_argument('--output', type=Path, default=ROOT/'output/jeff_factory/artifact_check.json')
    args = parser.parse_args()
    summary = check(args.folder.resolve(), args.video.resolve(), args.pdf.resolve(), args.output.resolve())
    print(json.dumps({key:value for key,value in summary.items() if key != 'hashes'}, indent=2))
