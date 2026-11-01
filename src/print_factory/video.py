"""Compose readable Japanese explanation around actual rendered simulation frames."""
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from fractions import Fraction
from functools import lru_cache
import av

FONT = 'C:/Windows/Fonts/YuGothR.ttc'
BOLD = 'C:/Windows/Fonts/YuGothB.ttc'
COLORS = np.array([[18, 27, 39], [220, 55, 202], [30, 165, 245], [245, 65, 58]], np.uint8)


class VideoWriter:
    """In-process encoding avoids Windows std-handle changes made by native runtimes."""
    def __init__(self, path, fps):
        self.container = av.open(str(path), 'w')
        self.stream = self.container.add_stream('libx264', rate=Fraction(str(fps)))
        self.stream.pix_fmt = 'yuv420p'
        self.stream.options = {'crf': '20', 'preset': 'fast'}
        self.started = False

    def append_data(self, rgb):
        if not self.started:
            self.stream.width, self.stream.height = rgb.shape[1], rgb.shape[0]
            self.started = True
        frame = av.VideoFrame.from_ndarray(np.ascontiguousarray(rgb), format='rgb24')
        for packet in self.stream.encode(frame):
            self.container.mux(packet)

    def close(self):
        for packet in self.stream.encode():
            self.container.mux(packet)
        self.container.close()


@lru_cache(maxsize=32)
def font(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, size)


def compose(overview, rgb, mask, route, state, elapsed, note, completed=False):
    canvas = Image.new('RGB', (1440, 900), '#101923')
    d = ImageDraw.Draw(canvas)
    d.text((34, 20), 'PrintFactory AI', font=font(36, True), fill='#f5f7fa')
    d.text((420, 34), '工場全体が、一つの身体になる。', font=font(25), fill='#9edbd4')
    d.text((1220, 35), f'{elapsed:05.1f} s', font=font(24), fill='#d5e0ec')
    canvas.paste(Image.fromarray(overview), (28, 100))
    d.rounded_rectangle((1012, 100, 1412, 700), 15, fill='#1b2a3b')
    d.text((1032, 112), '天井カメラ → AI認識', font=font(22, True), fill='white')
    blended = (rgb.astype(float) * .58 + COLORS[mask] * .42).astype(np.uint8)
    camera = Image.fromarray(blended).resize((352, 352))
    cd = ImageDraw.Draw(camera)
    if len(route) > 1:
        cd.line([(float(c) * 352 / 256, float(r) * 352 / 256) for r, c in route], fill='#83ffd1', width=3)
    canvas.paste(camera, (1036, 155))
    for k, (label, color) in enumerate([('紙束', '#dc37ca'), ('AMR', '#1ea5f5'), ('障害物', '#f5413a')]):
        d.rectangle((1040, 526 + k * 40, 1054, 540 + k * 40), fill=color)
        d.text((1068, 518 + k * 40), label, font=font(20), fill='#e0e8ef')
    d.text((1036, 652), 'RGB入力のみ / 学習済みCNN', font=font(18), fill='#a7bbcf')
    d.rounded_rectangle((28, 720, 1412, 870), 16, fill='#1b2a3b')
    d.text((50, 735), state, font=font(29, True), fill='#83ffd1' if not completed else '#f7d277')
    d.text((50, 786), note, font=font(23), fill='#edf2f7')
    d.text((50, 837), 'Genesis CUDA物理計算 ｜ 吸着＝固定拘束の近似 ｜ 印刷・加工＝状態遷移 ｜ 実時間再生', font=font(16), fill='#a7bbcf')
    # Work-cell labels are explanatory overlays; geometry and motion remain Genesis outputs.
    d.text((45, 112), '目：天井カメラ　 足：AMR　 手：直交型ロボット', font=font(20, True), fill='#f0f6ff', stroke_width=1, stroke_fill='#142232')
    return np.asarray(canvas)
