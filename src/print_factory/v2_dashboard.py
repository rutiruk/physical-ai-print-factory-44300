"""Pillow-only composition of V2 telemetry and unaltered simulation cameras.

No inference or simulation is performed here. Waypoints are plotted in their
original local coordinates, without projecting them onto camera pixels.
"""
from pathlib import Path
import math
import numpy as np
from PIL import Image, ImageDraw, ImageOps
from .video import font

SIZE = (1800, 1100)
BG, PANEL, INK, MUTED = '#101923', '#1b2b3a', '#f1f5fa', '#b4c7d8'
TEAL, GOLD, RED = '#79e3d2', '#f5ce76', '#ff8b89'


def _number(value, default=0.):
    try:
        value = float(value)
        return value if math.isfinite(value) else default
    except (TypeError, ValueError):
        return default


def _capture(value):
    return '入力SIM 未取得' if value is None else f'入力SIM {_number(value):.2f} s'


def _event_text(event):
    kind = event.get('event', '')
    model = event.get('model') or '学習モデル'
    labels = {
        'LEARNED_NAV_START': f'{model}による局所経路予測を開始',
        'LEARNED_NAV_RETRY': f'{model}による局所経路予測を再開',
        'LEARNED_NAV_END': '学習モデルの局所目標に到達',
        'NAV_LOCAL_GOAL_THROUGH': '局所目標を通過・次の経路予測へ',
        'NAV_NEEDS_RECOVERY': '走行が停滞・復帰判断を待機',
        'CONVENTIONAL_HEADING_START': '従来制御で向き合わせを開始',
        'CONVENTIONAL_HEADING_END': '従来制御の向き合わせが完了',
        'CONVENTIONAL_PRECISION_START': '従来制御で精密な着岸を開始',
        'CONVENTIONAL_PRECISION_END': '従来制御の精密な着岸が完了',
        'CONTACT_UNLOAD': '荷物を降ろして支持状態を確認',
        'MACHINE_RECEIVE': '加工機の送り・固定を開始',
        'AMBIGUOUS_JEFF': 'Jeffの候補が拮抗・通行許可を保留',
        'STALE_JEFF': '古い観測の判断は適用せず再観測',
    }
    # Supplied Japanese details retain the runtime's more specific explanation.
    detail = event.get('detail')
    text = str(detail) if detail and any('\u3040' <= ch <= '\u9fff' for ch in str(detail)) else labels.get(kind, detail or kind)
    prefix = f'AMR{int(event["amr"])+1} ' if event.get('amr') is not None and not str(text).startswith('AMR') else ''
    return f'{_number(event.get("time_s")):.1f}s  {prefix}{text}'


def dashboard_content(data):
    """Visible factual strings, also usable for synchronization verification."""
    now = _number(data.get('now'))
    jeff = data.get('jeff') or {}
    labels = jeff.get('labels') or {}
    label = lambda key: str(labels.get(key, labels.get(str(key), key)))
    probabilities = jeff.get('probabilities') or {}
    candidates = sorted(((label(k), _number(v)) for k, v in probabilities.items()),
                        key=lambda item: item[1], reverse=True)[:3]
    robots = []
    source = data.get('robots') or []
    jobs = {str(job.get('id')): job for job in data.get('jobs', [])}
    job_states = {'queued': '工程待ち', 'printing': '印刷中', 'printed': '印刷済',
                  'in_transit': '搬送中', 'folding': '折り加工中', 'folded': '折り済',
                  'trimming': '断裁中', 'finished': '仕上がり'}
    for i, model in enumerate(('ViNT', 'NoMaD')):
        robot = source[i] if i < len(source) and source[i] else {}
        job_id = str(robot.get('job') or ('A', 'B')[i])
        job = jobs.get(job_id)
        job_status = None
        if job:
            state = job_states.get(job.get('state'), '状態未取得')
            job_status = f'{job_id}：{state} / {job.get("source", "未指定")} → {job.get("destination", "未指定")}'
        robots.append({'title': f'AMR {i+1} / {robot.get("model", model)}',
                       'job_status': job_status,
                       'capture': _capture(robot.get('input_time_s')),
                       'policy_usage': 'AI予測を走行に使用中' if robot.get('policy_active') else '直前のAI予測（現在は従来制御/待機）',
                       'stop': f'非常停止：{robot["stop_reason"]}' if robot.get('stop_reason') else '非常停止なし',
                       'phase': str(robot.get('phase') or '状態未取得')})
    traffic = data.get('traffic') or {}
    winner = traffic.get('winner')
    winner_label = f'AMR{winner+1}' if type(winner) is int else str(winner) if winner is not None else '未決定'
    granted, crossed = traffic.get('granted'), traffic.get('crossed')
    if isinstance(granted, (list, tuple, set)):
        names = lambda indices: '・'.join(f'AMR{int(i)+1}' for i in indices) or 'なし'
        permission = f'許可 {names(granted)} / 通過 {names(crossed or [])}'
    else:
        permission = '通行許可' if granted else '許可待ち'
        if crossed:
            permission = '通過済み'
    initial = data.get('initial_condition') or ('開始条件は工程表示を参照' if data.get('process_summary') else '初期WIPから開始')
    footer = '車輪・接触・駆動部は物理 / 紙変形・インキ・切断は近似 / '+str(initial)
    footer += ' / 全編一律2倍・カットなし' if data.get('playback_speed') == 2 else ' / 等速再生'
    events = [e for e in data.get('events', []) if _number(e.get('time_s')) <= now]
    gantry = data.get('gantry') or {}
    pose, target = gantry.get('pose') or [], gantry.get('target') or []
    force, limit = gantry.get('force') or [], gantry.get('force_limit') or []
    saturated = gantry.get('force_saturated') or []
    gantry_y = '門型Y：実測未取得'
    if min(map(len, (pose, target, force, limit))) > 1:
        suffix = ' 飽和' if len(saturated) > 1 and saturated[1] else ' 他軸飽和' if any(saturated) else ''
        gantry_y = (f'Y 実測{_number(pose[1]):.3f} → 目標{_number(target[1]):.3f} m'
                    f' / 駆動{_number(force[1]):.1f} / {_number(limit[1]):.0f} N{suffix}')
    clearance = _number(data.get('min_clearance'), float('nan'))
    center = _number(data.get('min_distance'), float('nan'))
    clearance_label = (f'車体間余裕 ≥ {clearance:.3f} m' if math.isfinite(clearance)
                       else f'中心間距離 {center:.2f} m' if math.isfinite(center) else '車体間余裕 未計測')
    return {'current': f'現在SIM {now:.2f} s', 'robots': robots,
            'jeff_capture': _capture(jeff.get('input_time_s')),
            'jeff_image_label': 'Jeffの入力画像' if jeff.get('image_path') is not None else 'Jeff入力待ち',
            'jeff_choice': label(jeff['choice']) if jeff.get('choice') is not None else '判断待ち',
            'candidates': candidates,
            'traffic': f'優先 {winner_label} / {permission}',
            'events': [_event_text(e) for e in events[-2:]],
            'gantry_y': gantry_y, 'clearance': clearance_label,
            'process_summary': data.get('process_summary') or '初期の仕掛品から開始  A：印刷済100枚 → 折り機     B：折り済100枚 → 断裁機',
            'footer': footer}


def _text(draw, xy, text, size=20, fill=INK, bold=False, width=None):
    text = str(text)
    f = font(size, bold)
    if width:
        while size > 13 and draw.textbbox((0, 0), text, font=f)[2] > width:
            size -= 1
            f = font(size, bold)
        while text and draw.textbbox((0, 0), text, font=f)[2] > width:
            text = text[:-2] + '…' if len(text) > 2 else ''
    draw.text(xy, text, font=f, fill=fill)


def _panel(draw, box):
    draw.rounded_rectangle(box, 14, fill=PANEL)


def _photo(canvas, source, box):
    """Letterbox actual images; never crop a simulation camera."""
    x, y, w, h = box
    if source is None:
        return False
    try:
        if isinstance(source, (str, Path)):
            with Image.open(source) as opened:
                picture = opened.convert('RGB')
        elif isinstance(source, Image.Image):
            picture = source.convert('RGB')
        else:
            picture = Image.fromarray(np.asarray(source, dtype=np.uint8)).convert('RGB')
        picture = ImageOps.contain(picture, (w, h), Image.Resampling.LANCZOS)
        canvas.paste(picture, (x + (w-picture.width)//2, y+(h-picture.height)//2))
        return True
    except (OSError, ValueError, TypeError):
        return False


def _waypoints(draw, box, raw, color):
    x, y, w, h = box
    draw.rounded_rectangle((x, y, x+w, y+h), 6, fill='#101c28')
    _text(draw, (x+8, y+5), '予測点 / ローカル座標', 15, MUTED)
    try:
        points = np.asarray(raw, dtype=float).reshape(-1, 2)
        points = points[np.isfinite(points).all(axis=1)]
    except (ValueError, TypeError):
        points = np.empty((0, 2))
    if not len(points):
        _text(draw, (x+22, y+70), '予測点なし', 16, MUTED)
        return
    low = np.minimum(points.min(axis=0), 0.)
    high = np.maximum(points.max(axis=0), 0.)
    span = np.maximum(high-low, .1)
    scale = min((w-45)/span[0], (h-65)/span[1])
    def pixel(p):
        return (x+24+(p[0]-low[0])*scale, y+h-30-(p[1]-low[1])*scale)
    origin = pixel(np.zeros(2))
    draw.line((x+20, origin[1], x+w-10, origin[1]), fill='#56697c')
    draw.line((origin[0], y+32, origin[0], y+h-25), fill='#56697c')
    coords = [pixel(p) for p in points]
    if len(coords) > 1:
        draw.line(coords, fill=color, width=3)
    for px, py in coords:
        draw.ellipse((px-3, py-3, px+3, py+3), fill=color)
    draw.ellipse((origin[0]-4, origin[1]-4, origin[0]+4, origin[1]+4), outline=INK, width=2)
    _text(draw, (x+7, y+h-23), f'x {low[0]:.2f}…{high[0]:.2f}  y {low[1]:.2f}…{high[1]:.2f}', 12, MUTED, width=w-12)


def _robot(canvas, draw, x, robot, content, color):
    y, w = 710, 864
    _panel(draw, (x, y, x+w, 1044))
    _text(draw, (x+16, y+8), content['title'], 25, color, True)
    cargo = str(robot.get('cargo', '荷物情報なし'))
    job_line = content['job_status']+' / '+cargo if content.get('job_status') else f'搬送 {robot.get("job", "—")}：{cargo}'
    _text(draw, (x+255, y+14), job_line, 21, width=590)
    _text(draw, (x+16, y+46), content['phase'], 23, INK, True, width=830)
    _text(draw, (x+16, y+80), content['policy_usage'], 18, color if robot.get('policy_active') else GOLD, True, width=830)
    _text(draw, (x+16, y+108), content['capture'], 16, MUTED)
    _text(draw, (x+267, y+108), f'推論 {_number(robot.get("latency_ms")):.0f} ms', 16, MUTED)
    if not _photo(canvas, robot.get('input_image'), (x+16, y+138, 238, 134)):
        _text(draw, (x+32, y+173), '前方入力画像 未取得', 17, MUTED)
    _waypoints(draw, (x+267, y+138, 220, 134), robot.get('waypoints', []), color)
    actual = robot.get('actual') or {}
    velocity = actual.get('velocity') or [0., 0., 0.]
    speed = math.hypot(*[_number(v) for v in velocity[:2]]) if len(velocity) >= 2 else 0.
    tx = x+505
    _text(draw, (tx, y+113), '車輪の指令 → 物理の実測', 19, color, True)
    _text(draw, (tx, y+148), f'速度 {_number(actual.get("command_v")):.2f} → {speed:.2f} m/s', 20)
    _text(draw, (tx, y+179), f'旋回指令 {_number(actual.get("command_w")):+.2f} rad/s', 17, MUTED)
    torque = actual.get('wheel_torque') or []
    peak = max([abs(_number(v)) for v in torque], default=0.)
    _text(draw, (tx, y+210), f'駆動トルク 最大 {peak:.2f} / 6 Nm', 18)
    draw.rounded_rectangle((tx, y+242, tx+330, y+251), 4, fill='#3b4d5f')
    draw.rounded_rectangle((tx, y+242, tx+max(1, 330*min(peak/6, 1)), y+251), 4, fill=RED if peak > 6 else color)
    _text(draw, (x+16, y+285), content['stop'], 20, RED if robot.get('stop_reason') else MUTED, width=830)
    goal = robot.get('goal')
    goal_label = '未指定'
    if goal is not None and len(goal) >= 2:
        goal_label = f'({_number(goal[0]):.2f}, {_number(goal[1]):.2f}) m'
    _text(draw, (x+16, y+313), f'画像 → 局所経路予測 / 目標 {goal_label}', 14, MUTED, width=480)
    _text(draw, (tx, y+285), f'昇降 {_number(actual.get("lift_position")):.3f} m / {_number(actual.get("lift_force")):.1f} N', 16, MUTED, width=340)


def render_v2_dashboard(overview: np.ndarray, overhead: np.ndarray, data: dict) -> Image.Image:
    """Return a 1800×1100 RGB dashboard from current cameras and runtime data."""
    canvas = Image.new('RGB', SIZE, BG)
    draw = ImageDraw.Draw(canvas)
    c = dashboard_content(data)
    _text(draw, (24, 12), 'PRINT FACTORY  /  2台が荷物を運ぶ工場', 32, INK, True)
    _text(draw, (1420, 20), c['current'], 25, TEAL, True)
    _text(draw, (25, 65), c['process_summary'], 23, GOLD, width=1748)
    _panel(draw, (24, 110, 1070, 693))
    _text(draw, (42, 119), '現在の工場 / 2台の対向搬送・退避・加工', 23, TEAL, True)
    _photo(canvas, overview, (34, 160, 1026, 522))
    _panel(draw, (1088, 110, 1404, 431))
    jeff = data.get('jeff') or {}
    _text(draw, (1102, 120), c['jeff_image_label'], 21, GOLD, True)
    if not _photo(canvas, jeff.get('image_path'), (1098, 159, 296, 228)):
        _text(draw, (1144, 263), 'Jeff入力待ち', 21, MUTED)
    _text(draw, (1102, 393), c['jeff_capture'], 18, MUTED)
    _panel(draw, (1420, 110, 1776, 431))
    _text(draw, (1436, 120), 'Jeff / 工場の行動を選択', 22, GOLD, True, width=324)
    _text(draw, (1436, 158), c['jeff_capture'], 17, MUTED)
    _text(draw, (1436, 185), f'推論 {_number(jeff.get("latency_ms")):.0f} ms', 17, MUTED)
    _text(draw, (1436, 217), '選択：'+c['jeff_choice'], 23, GOLD, True, width=324)
    _text(draw, (1436, 254), '候補の確率 / 上位3件', 16, MUTED)
    for i, (label, probability) in enumerate(c['candidates']):
        _text(draw, (1436, 283+i*39), label, 18, width=235)
        _text(draw, (1685, 283+i*39), f'{probability:.0%}', 18, GOLD)
    _panel(draw, (1088, 445, 1776, 557))
    traffic = data.get('traffic') or {}
    aisle, robot_width = _number(traffic.get('aisle_width'), .90), _number(traffic.get('robot_width'), .56)
    _text(draw, (1104, 452), f'狭路 {aisle:.2f} m < 2台 × {robot_width:.2f} m：すれ違い不可', 22, GOLD, True, width=654)
    _text(draw, (1104, 487), 'Jeffの退避・解放判断 → '+c['traffic'], 21, TEAL, width=654)
    _text(draw, (1104, 522), f'従来の安全停止は別系統 / 発動 {_number(data.get("safety_stops")):.0f}回', 18, MUTED)
    _panel(draw, (1088, 570, 1776, 693))
    gantry = data.get('gantry') or {}
    _text(draw, (1104, 572), f'門型ロボット：{gantry.get("phase", "状態未取得")}', 19, width=650)
    _text(draw, (1104, 598), c['gantry_y'], 17, RED if '飽和' in c['gantry_y'] else MUTED, width=650)
    names = {'press': '印刷機', 'folder': '折り機', 'trim': '断裁機'}
    modes = {'idle': '待機', 'feed': '送り', 'clamp': '固定', 'release': '解放',
             'stop': '停止', 'reset': '復帰', 'fault': '異常'}
    machine_labels = []
    for name, machine in (data.get('machines') or {}).items():
        machine = machine or {}
        kind = machine.get('kind', name)
        mode = '異常' if machine.get('fault') else modes.get(machine.get('mode'), machine.get('mode', '未取得'))
        forces = machine.get('force') or []
        clamp = f' 固定{abs(_number(forces[2])):.0f}N' if len(forces) >= 3 else ''
        machine_labels.append(f'{names.get(kind, name)} {mode}{clamp}')
    _text(draw, (1104, 622), ' / '.join(machine_labels) or '加工機：状態未取得', 16, MUTED, width=650)
    delivered = data.get('delivered') or [False, False]
    done = sum(bool(v) for v in delivered)
    _text(draw, (1104, 646), f'納入 {done}/2  同時走行 {_number(data.get("concurrent_seconds")):.1f}s  {c["clearance"]}', 16, MUTED, width=650)
    event = c['events'][-1] if c['events'] else '工程イベント待ち'
    _text(draw, (1104, 670), event, 14, MUTED, width=650)
    robots = data.get('robots') or []
    for i, x in enumerate((24, 912)):
        robot = robots[i] if i < len(robots) and robots[i] else {}
        _robot(canvas, draw, x, robot, c['robots'][i], (TEAL, '#91c5ff')[i])
    _text(draw, (26, 1060), c['footer'], 21, MUTED, width=1748)
    return canvas
