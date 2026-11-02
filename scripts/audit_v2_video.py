"""Decode every frame; check one-to-one SIM telemetry and uniform playback."""
import argparse,hashlib,json,math,sys
from pathlib import Path
import av


def audit(folder):
    folder=Path(folder);result=json.loads((folder/'result.json').read_text(encoding='utf8'))
    times=[];active=set();snapshots=[];learned_motion={'vint':0.,'nomad':0.}
    with (folder/'frames.jsonl').open(encoding='utf8') as source:
        for line in source:
            row=json.loads(line);times.append(row['now'])
            for robot in row['robots']:
                model=robot['model'].lower()
                if robot.get('policy_active'):
                    active.add(model)
                    velocity=robot.get('actual',{}).get('velocity',[0.,0.,0.])
                    if robot.get('input_time_s') is not None and math.hypot(*velocity[:2])>.03:
                        learned_motion[model]=learned_motion.get(model,0.)+.05
            if len(snapshots)<1:snapshots.append(row)
            last=row
    errors=[]
    if any(abs(t-(i+1)*.05)>1e-6 for i,t in enumerate(times)):errors.append('non-contiguous simulation capture')
    count=0;bad_pts=0
    with av.open(str(folder/'demo.mp4')) as video:
        stream=video.streams.video[0];fps=float(stream.average_rate)
        for frame in video.decode(video=0):
            if abs(float(frame.pts*frame.time_base)-count/40)>1e-6:bad_pts+=1
            count+=1
    if count!=len(times):errors.append('video/telemetry frame count mismatch')
    if fps!=40 or bad_pts:errors.append('non-uniform 40fps timestamps')
    if count and not math.isclose(times[-1]/(count/40),2.):errors.append('not uniform2x playback')
    if result['success'] and not all(last['delivered']):errors.append('successful run without visible deliveries')
    if result['success'] and not all(learned_motion.values()):errors.append('successful run without visible learned motion from both models')
    if result['success']:
        if count/40>180:errors.append('video exceeds three-minute limit')
        if result['robot_contacts'] or result['equipment_contacts']:errors.append('successful run contains robot collision contacts')
        if result['concurrent_loaded_translation_seconds']<1:errors.append('insufficient physically supported loaded concurrence')
        if 'jobs' in result:
            jobs={j['job_id']:j for j in result['jobs']}
            if [h['machine'] for h in jobs['A']['history']]!=['press','folder'] or jobs['A']['stage']!='folded':
                errors.append('jobA did not follow printing-to-folding sequence')
            if [h['machine'] for h in jobs['B']['history']]!=['trim'] or jobs['B']['stage']!='finished':
                errors.append('jobB did not finish folded-WIP-to-trim sequence')
    manifest=json.loads((folder/'source_manifest.json').read_text(encoding='utf8'))
    source_errors=[name for name,digest in manifest.items()
                   if hashlib.sha256((folder/'source'/name).read_bytes()).hexdigest()!=digest]
    if source_errors:errors.append('startup source snapshot checksum mismatch')
    output=dict(valid=not errors,errors=errors,frames=count,telemetry_frames=len(times),fps=fps,
                video_seconds=count/40,first_sim_s=times[0] if times else None,
                final_sim_s=times[-1] if times else None,nonuniform_pts=bad_pts,
                visible_active_models=sorted(active),learned_translation_seconds=learned_motion,
                source_snapshot_files=len(manifest),source_snapshot_checksum_errors=source_errors,
                experiment_success=result['success'])
    (folder/'video_audit.json').write_text(json.dumps(output,indent=2),encoding='utf8')
    print(json.dumps(output,indent=2));return not errors


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder');args=p.parse_args()
    sys.exit(0 if audit(args.folder) else 1)
