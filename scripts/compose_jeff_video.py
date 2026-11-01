"""Edit the completed Jeff run, retaining synchronized source dashboards.

Importing this module performs no encoding. Run only after the simulation exits:
    .venv/Scripts/python.exe scripts/compose_jeff_video.py
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def merge_intervals(intervals, duration):
    merged = []
    for start, end in sorted((max(0., float(a)), min(float(duration), float(b))) for a, b in intervals):
        if end <= start:
            continue
        if merged and start <= merged[-1][1] + 1e-8:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def _cuts(keep, duration):
    cuts, previous = [], 0.
    for start, end in keep:
        if start > previous:
            cuts.append((previous, start))
        previous = end
    if previous < duration:
        cuts.append((previous, duration))
    return cuts


def closing_summary(result):
    """Count logged completions; no inference from a potentially earlier camera frame."""
    jobs = [job for job in result.get('state', {}).get('jobs', [])
            if job.get('completed') is not None]
    return dict(completed_jobs=len(jobs), copies=sum(job.get('copies', 0) for job in jobs),
                simulation_seconds=float(result['simulation_seconds']),
                completion_times=[(job['id'], float(job['completed'])) for job in jobs])


def select_intervals(events, decisions, duration, max_seconds=175):
    """Prefer full navigation; trim it to explicit endpoints if over budget.

    Every physical push stays intact. Older logs lack a start event: retain
    five seconds before completion, covering the runner's 4.25s contact cycle.
    A budget too small for mandatory evidence raises rather than hiding actions.
    """
    mandatory, navigation, pushes = [(0, 3), (duration-3, duration)], [], []
    starts, nav_starts = {}, {}
    for event in sorted(events, key=lambda e: e['time_s']):
        instant, kind = float(event['time_s']), event['event']
        amr = event.get('amr', 0)
        if kind == 'PHYSICAL_PUSH_START':
            starts[amr] = instant
        elif kind == 'PHYSICAL_PUSH':
            inferred = amr not in starts
            start = starts.pop(amr, max(0., instant-5.))
            mandatory.append((start-.15 if not inferred else start, instant+.5))
            pushes.append(dict(start=start, end=instant, amr=amr, start_inferred=inferred))
        elif kind == 'LEARNED_NAV_START':
            nav_starts[amr] = instant
        elif kind == 'LEARNED_NAV_END':
            start = nav_starts.pop(amr, instant)
            navigation.append((start, instant))
        elif kind == 'JOB_ARRIVAL':
            mandatory.append((instant-1.5, instant+1.5))
        elif kind in ('TRANSPORT_ASSIGNED', 'TRANSPORT_COMPLETE', 'PACKED_OUTPUT',
                      'PROCESS_START', 'PROCESS_COMPLETE', 'MACHINE_FAULT', 'MACHINE_RECOVERED'):
            mandatory.append((instant-.3, instant+.8))
    for start in starts.values():
        mandatory.append((start, duration))
    for start in nav_starts.values():
        navigation.append((start, duration))
    previous = None
    for decision in sorted(decisions, key=lambda d: d.get('time_s', 0)):
        choice = decision.get('choice')
        if choice != previous or choice != 'wait':
            instant = float(decision.get('time_s', 0))
            mandatory.append((instant-.25, instant+1.))
        previous = choice
    budget = max_seconds * 2
    full = merge_intervals(mandatory + navigation, duration)
    mode = 'full_navigation'
    endpoint_seconds = None
    if sum(b-a for a,b in full) > budget:
        mode = 'navigation_endpoints'
        # Retain both beginnings and endings, including each model's loaded legs.
        for endpoint_seconds in (1.5, 1., .5):
            chunks = [(a, min(b, a+endpoint_seconds)) for a,b in navigation]
            chunks += [(max(a, b-endpoint_seconds), b+.2) for a,b in navigation]
            full = merge_intervals(mandatory+chunks, duration)
            if sum(b-a for a,b in full) <= budget:
                break
    if sum(b-a for a,b in full) > budget:
        raise ValueError('Mandatory evidence exceeds requested duration; increase --max-seconds. No pushes were omitted.')
    # Spend spare time restoring longest useful navigation portions first.
    for interval in sorted(navigation, key=lambda item: item[1]-item[0], reverse=True):
        candidate = merge_intervals(full+[interval], duration)
        if sum(b-a for a,b in candidate) <= budget:
            full = candidate
    return dict(keep=full, cuts=_cuts(full, duration), pushes=pushes, selection_mode=mode,
                navigation_endpoint_seconds=endpoint_seconds,
                playback_speed=2, predicted_seconds=sum(b-a for a,b in full)/2)


def compose(folder, output, max_seconds=175):
    import av
    import numpy as np
    from PIL import Image, ImageDraw
    sys.path.insert(0, str(ROOT/'src'))
    from print_factory.video import VideoWriter, font

    result_path, raw = folder/'result.json', folder/'factory_raw.mp4'
    result = json.loads(result_path.read_text(encoding='utf-8'))
    if result.get('status') == 'running':
        raise RuntimeError('The simulation is still running; wait for its process to exit.')
    if not result.get('success') or result.get('status') != 'complete':
        raise RuntimeError('Only a successful complete run can become the final submission.')
    duration = float(result['simulation_seconds'])
    closing_seconds = 3
    if max_seconds <= closing_seconds:
        raise ValueError('--max-seconds must leave room for the 3-second closing summary')
    plan = select_intervals(result['events'], result.get('decisions', []), duration, max_seconds-closing_seconds)
    temp = output.with_name(output.stem+'.encoding.mp4')
    writer = VideoWriter(temp, 20)
    index, count, source_count, last_interval, marker = 0, 0, 0, None, 0
    last = None
    try:
        with av.open(str(raw)) as source:
            rate = float(source.streams.video[0].average_rate)
            if abs(rate-20) > .01:
                raise ValueError(f'Expected 20fps source, got {rate}')
            for raw_index, frame in enumerate(source.decode(video=0)):
                source_count += 1
                sim_time = (raw_index+1)/20  # Runner captures ticks 5,10,... at dt=.01.
                while index < len(plan['keep']) and sim_time > plan['keep'][index][1]+1e-7:
                    index += 1
                if index >= len(plan['keep']):
                    continue
                start, end = plan['keep'][index]
                if sim_time+1e-7 < start or raw_index % 2:
                    continue
                if last_interval is not None and index != last_interval:
                    marker = 30
                last_interval = index
                canvas = Image.fromarray(frame.to_ndarray(format='rgb24'))
                draw = ImageDraw.Draw(canvas)
                # Cover only the previous footer; source SIM clock remains untouched.
                draw.rectangle((0, 866, 1439, 899), fill='#0d1722')
                draw.text((24, 873), '2倍速 / 移動・待機の一部を省略 / SIM時刻で同期', font=font(17, True), fill='#ffd278')
                draw.text((690, 875), '印刷・折り・製本の内部は状態遷移モデル', font=font(15), fill='#a6b9cc')
                # Source dashboard was rendered at 1×; correct its speed caption.
                draw.rectangle((1090, 50, 1410, 77), fill='#0d1722')
                draw.text((1098, 53), '再生 2倍速 / 全画面同期', font=font(16), fill='#a6b9cc')
                if marker:
                    draw.rounded_rectangle((350, 77, 950, 113), radius=6, fill='#543f20')
                    draw.text((365, 81), f'編集点：移動・待機を省略 → SIM {sim_time:.2f}s', font=font(18, True), fill='#ffe3a5')
                    marker -= 1
                writer.append_data(np.asarray(canvas))
                count += 1
                last = canvas
        if not count or abs(source_count/20-duration) > .15:
            raise RuntimeError('Source video is empty or incomplete relative to result.json; final output not replaced.')
        # The simulation may finish between camera captures. Keep the last real
        # frame as a backdrop and label completion counts strictly as log data.
        summary = closing_summary(result)
        from PIL import ImageEnhance
        last = ImageEnhance.Brightness(last).enhance(.28)
        draw = ImageDraw.Draw(last)
        draw.rounded_rectangle((220, 180, 1220, 710), radius=18, fill='#142535', outline='#7ce5c8', width=2)
        draw.text((265, 210), '完了ログ確認', font=font(38, True), fill='#7ce5c8')
        draw.text((265, 271), '完了ログによる集計（静止画）', font=font(26, True), fill='#ffd278')
        draw.text((265, 332), f"完了 {summary['completed_jobs']}件 / 合計 {summary['copies']}部", font=font(34, True), fill='#edf4fb')
        draw.text((265, 394), f"実行終了ログ：SIM {summary['simulation_seconds']:.2f}s", font=font(24), fill='#edf4fb')
        for offset, (job, timestamp) in enumerate(summary['completion_times']):
            draw.text((265, 442+offset*43), f'{job}  完了時刻：SIM {timestamp:.2f}s', font=font(23), fill='#a6b9cc')
        draw.text((265, 632), '背景は最後に記録した実際のカメラ画像です。', font=font(20), fill='#a6b9cc')
        draw.text((265, 665), '上記の集計は result.json の完了ログに基づきます。', font=font(20), fill='#a6b9cc')
        # Replace the backdrop clock explicitly rather than implying a new capture.
        draw.rectangle((1085, 0, 1439, 78), fill='#0d1722')
        draw.text((1095, 17), '完了ログ集計 / 静止画', font=font(21, True), fill='#ffd278')
        for _ in range(closing_seconds*20):
            writer.append_data(np.asarray(last))
            count += 1
    finally:
        writer.close()
    temp.replace(output)
    if last:
        last.save(folder/'completed_jeff.png')
    plan.update(source=str(raw), output=str(output), source_frame_count=source_count,
                frame_count=count, fps=20, duration_seconds=count/20,
                closing_summary_seconds=closing_seconds, closing_summary=summary,
                completed_image_description='Log-summary closing card on darkened last actual camera frame; not a new simulation capture.',
                cuts_sim_seconds=plan['cuts'], source_sim_first_frame_s=.05,
                description='Actual synchronized Genesis dashboard frames. No synthetic task completion. Push windows preserved.')
    (folder/'video_edit.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')
    return plan


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder', type=Path, default=ROOT/'output/jeff_factory/jeff')
    parser.add_argument('--output', type=Path, default=ROOT/'output/PrintFactory_Jeff_demo.mp4')
    parser.add_argument('--max-seconds', type=float, default=175)
    args = parser.parse_args()
    manifest = compose(args.folder, args.output, args.max_seconds)
    print(json.dumps({'output': str(args.output), 'duration_seconds': manifest['duration_seconds'],
                      'frame_count': manifest['frame_count'], 'pushes_preserved': len(manifest['pushes'])}, indent=2))
