"""Time-synchronized, read-only compositor for the factory demonstration video.

Both camera frames and all supplied observations must belong to the same simulation
instant. Event filtering prevents a preloaded event log leaking future arrivals.
"""
from __future__ import annotations

import numpy as np
from PIL import Image, ImageDraw, ImageOps

from .video import font


STATIONS = {'press': '印刷機', 'folder': '折り機', 'gather': '丁合',
            'folder_in': '折り機入口', 'stock': '用紙庫', 'finishing': '製本・梱包'}
PHASES = {'idle': '待機', 'carrying': '搬送中', 'moving': '移動中',
          'pickup': '集荷中', 'approach': '集荷へ移動', 'deliver': '納品へ移動',
          'delivery': '納品へ移動', 'unload': '荷下ろし', 'loading': '積載中',
          'blocked': '障害物で停止', 'waiting': '待機'}
PHASES.update(recovering='再接近の準備',returning='待機位置へ戻る',**{'return':'待機位置へ戻る'})
INK = '#edf4fb'
MUTED = '#a6b9cc'
TEAL = '#7ce5c8'
GOLD = '#ffd278'


def _event_text(event):
    kind, job = event.get('event', ''), event.get('job', '')
    form = f" F{event['form']}" if event.get('form') is not None else ''
    station = STATIONS.get(event.get('machine'), event.get('machine', ''))
    if kind in ('NAV_RECOVERY_REQUIRED','NAV_RECOVERY_CHOSEN','LEARNED_NAV_RETRY'):
        action={'NAV_RECOVERY_REQUIRED':'方策の逸脱を検出・停止','NAV_RECOVERY_CHOSEN':'Jeffが再試行を選択','LEARNED_NAV_RETRY':'基盤モデルを再観測・再開'}[kind]
        return f"AMR{int(event['amr'])+1} {action}"
    if kind == 'JOB_ARRIVAL':
        return f'新規受注 {job}'
    if kind in ('PROCESS_START', 'PROCESS_COMPLETE'):
        return f"{job}{form} {station} {'開始' if kind.endswith('START') else '完了'}"
    if kind.startswith('TRANSPORT_'):
        robot = int(event.get('amr', 0)) + 1
        dest = STATIONS.get(event.get('destination'), event.get('destination', ''))
        return f"AMR{robot} {job}{form} → {dest} {'割当' if kind.endswith('ASSIGNED') else '到着'}"
    if kind == 'MACHINE_FAULT':
        return f'{station} 停止'
    if kind == 'MACHINE_RECOVERED':
        return f'{station} 復旧'
    return 'Jeff 判断保留' if kind == 'HOLD' else f'{kind} {job}'


def _choice_text(choice,job_pages=None):
    if not choice or choice == 'wait':
        return '待機 / 次のイベントを観測'
    if isinstance(choice, dict):
        choice = choice.get('id', choice.get('description', ''))
    parts = str(choice).split('@')[0].split(':')
    if len(parts) < 2:
        return str(choice)
    action, job = parts[:2]
    if action=='recover':return f'AMR{int(job)+1} → 再観測して移動を再試行'
    if action == 'finish':
        if (job_pages or {}).get(job)==4:return f'{job} → リーフレット断裁・梱包（綴じ省略）'
        return f'{job} → 丁合・中綴じ・断裁・梱包'
    form = f' F{parts[2]}' if len(parts) > 2 else ''
    if action == 'carry' and len(parts) >= 6:
        return f"AMR{int(parts[-1])+1} / {job}{form} → {STATIONS.get(parts[4], parts[4])}"
    label = {'print': '両面印刷', 'fold': '折り加工'}.get(action, action)
    return f'{job}{form} → {label}'


def dashboard_content(state, decision, events, navigation):
    """Derive readable content without mutating state or revealing future events."""
    now = float(state.get('time_s', 0))
    visible = sorted((e for e in events if float(e.get('time_s', 0)) <= now),
                     key=lambda e: float(e.get('time_s', 0)))
    arrivals = [e for e in visible if e.get('event') == 'JOB_ARRIVAL'
                and 0 <= now - float(e['time_s']) < 5]
    robots = []
    amrs = state.get('amrs', [])
    for i, model in enumerate(('ViNT', 'NoMaD')):
        nav = (navigation[i] or {}) if i < len(navigation) else {}
        task = (amrs[i] or {}) if i < len(amrs) else {}
        cargo = (('積載 ' if task.get('picked_up') else '集荷予定 ')+f"{task['job']} / F{task['form']}") if task else str(nav.get('cargo') or '荷物なし')
        phase = nav.get('phase') or ('carrying' if task else 'idle')
        route = ''
        if task:
            route = f"{STATIONS.get(task.get('source'), task.get('source', ''))} → {STATIONS.get(task.get('destination'), task.get('destination', ''))}"
        latency = nav.get('latency_ms')
        robots.append(dict(title=f'AMR{i+1}  /  {model}', cargo=cargo,
                           phase=PHASES.get(phase, str(phase)), route=route,
                           latency_ms=latency))
    jobs = []
    for job in state.get('jobs', []):
        forms = max(1, int(job.get('pages', 4)) // 4)
        jobs.append(dict(id=job['id'], due=job.get('due', 0),
                         pages=job.get('pages', 0), copies=job.get('copies', 0),
                         forms=forms, gathered=len(job.get('received', [])),
                         done=job.get('completed') is not None,
                         locations=job.get('locations', {})))
    # Show active orders first, then most recently completed orders.
    jobs.sort(key=lambda j: (j['done'], float(j['due'])))
    return dict(now=now, arrivals=arrivals, robots=robots, jobs=jobs,
                choice=_choice_text((decision or {}).get('choice'),{j['id']:j['pages'] for j in jobs}),
                latency_ms=(decision or {}).get('latency_ms'),
                timeline=[f"{e['time_s']:06.1f}s  {_event_text(e)}" for e in visible[-4:][::-1]])


def render_dashboard(overview: np.ndarray, overhead: np.ndarray, state: dict,
                     decision: dict | None, events: list, navigation: list,
                     playback=1) -> Image.Image:
    """Render a 1440×900 RGB dashboard; playback is simulation seconds / video second."""
    data = dashboard_content(state, decision, events, navigation)
    canvas = Image.new('RGB', (1440, 900), '#0d1722')
    draw = ImageDraw.Draw(canvas)

    def text(x, y, value, size=20, color=INK, bold=False, width=None):
        value = str(value)
        face = font(size, bold)
        if width:
            while value and draw.textlength(value, font=face) > width:
                value = value[:-2] + '…' if not value.endswith('…') else value[:-2] + '…'
        draw.text((x, y), value, font=face, fill=color)

    def panel(box):
        draw.rounded_rectangle(box, radius=12, fill='#182838', outline='#2a4054', width=1)

    def camera(rgb, box):
        x, y, w, h = box
        frame = ImageOps.contain(Image.fromarray(np.asarray(rgb, dtype=np.uint8)), (w, h),
                                 method=Image.Resampling.BILINEAR)
        canvas.paste(frame, (x + (w-frame.width)//2, y + (h-frame.height)//2))

    text(24, 13, 'PrintFactory AI', 32, bold=True)
    policy_name='従来ルール（比較用）' if state.get('policy')=='rules' else 'Jeff'
    text(333, 25, f'不定期の受注 → {policy_name}が判断 → AMRが搬送', 20, TEAL)
    text(1094, 15, f"SIM  {data['now']:07.2f} s", 28, bold=True)
    text(1098, 53, f'再生 {playback:g}倍速 / 全画面同期', 16, MUTED)
    text(24, 83, '工場全景  /  Genesis', 20, bold=True)
    text(657, 87, 'AMR1 = ViNT    AMR2 = NoMaD', 17, TEAL)
    panel((24, 114, 944, 684))
    camera(overview, (25, 115, 918, 568))
    if data['arrivals']:
        event = data['arrivals'][-1]
        draw.rounded_rectangle((42, 130, 652, 211), radius=10, fill='#173f3c', outline=TEAL, width=2)
        text(60, 140, f"新規受注  {event.get('job', '')}  /  {float(event['time_s']):.1f}s 到着", 25, TEAL, True, 570)
        text(60, 177, f"{event.get('pages', '—')}ページ × {event.get('copies', '—')}部   生産キューに追加", 19)

    panel((968, 86, 1416, 337))
    text(984, 95, '天井カメラ  /  同じシミュレーション時刻', 19, bold=True)
    camera(overhead, (980, 129, 424, 197))

    panel((968, 351, 1416, 469))
    text(984, 360, f'{policy_name} / 現在の選択', 22, GOLD, True)
    text(984, 396, data['choice'], 21, width=416)
    latency = data['latency_ms']
    text(984, 436, f'推論 {float(latency):.0f} ms' if latency is not None else '判断ログ待ち', 16, MUTED)
    for i, robot in enumerate(data['robots']):
        y = 481 + i * 107
        panel((968, y, 1416, y+96))
        color = '#79c6ff' if i == 0 else '#e3a6ff'
        text(984, y+6, robot['title'], 22, color, True)
        text(1266, y+10, robot['phase'], 18, color, width=136)
        text(984, y+39, robot['cargo'], 21, width=410)
        detail = robot['route'] or '搬送指示を待機'
        if robot['latency_ms'] is not None:
            detail += f"  /  {float(robot['latency_ms']):.0f}ms"
        text(984, y+70, detail, 16, MUTED, width=411)

    panel((24, 701, 708, 859))
    completed = sum(j['done'] for j in data['jobs'])
    text(40, 707, f"受注・進捗  {len(data['jobs'])}件 / 完了 {completed}件", 21, bold=True)
    if not data['jobs']:
        text(40, 755, '受注待ち — 新しい注文が届くとここに追加', 21, MUTED)
    for i, job in enumerate(data['jobs'][:3]):
        y = 744 + 34*i
        status = '完成' if job['done'] else f"丁合 {job['gathered']}/{job['forms']}折"
        product='冊子' if job['pages']>=8 else '二折'
        text(40, y, f"{job['id']}  {product}{job['pages']}p × {job['copies']}部", 18, width=285)
        text(324, y, status, 18, TEAL if job['done'] else INK, width=142)
        text(481, y, f"納期 {float(job['due']):.0f}s", 16, MUTED)
        draw.rounded_rectangle((593, y+10, 686, y+18), radius=4, fill='#31495f')
        ratio = 1 if job['done'] else min(.95, job['gathered']/job['forms']*.8)
        if ratio:
            draw.rounded_rectangle((593, y+10, 593+93*ratio, y+18), radius=4, fill=TEAL)
    if len(data['jobs']) > 3:
        text(575, 714, f"他{len(data['jobs'])-3}件", 16, MUTED)

    panel((724, 701, 1416, 859))
    text(740, 707, 'イベント履歴  /  新しい順', 21, bold=True)
    if not data['timeline']:
        text(740, 751, 'シミュレーション開始 / イベント待ち', 19, MUTED)
    for i, line in enumerate(data['timeline']):
        text(740, 744+i*27, line, 17, TEAL if i == 0 else MUTED, width=654)
    text(24, 873, '物理：Genesis  ｜  印刷・折り・製本：工程の状態遷移による近似  ｜  丁合進捗は受入済みの折数', 16, MUTED)
    return canvas
