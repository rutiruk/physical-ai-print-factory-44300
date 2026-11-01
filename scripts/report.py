"""Generate the Japanese submission report from recorded experimental results."""
from pathlib import Path
import json
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
from reportlab.lib.pagesizes import A4

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'output'
pdfmetrics.registerFont(UnicodeCIDFont('HeiseiKakuGo-W5'))
styles = {
    'title': ParagraphStyle('title', fontName='HeiseiKakuGo-W5', fontSize=27, leading=35, textColor=colors.HexColor('#123744'), spaceAfter=12),
    'sub': ParagraphStyle('sub', fontName='HeiseiKakuGo-W5', fontSize=13, leading=20, textColor=colors.HexColor('#177f80'), spaceAfter=14),
    'h': ParagraphStyle('h', fontName='HeiseiKakuGo-W5', fontSize=14, leading=21, textColor=colors.HexColor('#123744'), spaceBefore=15, spaceAfter=7),
    'p': ParagraphStyle('p', fontName='HeiseiKakuGo-W5', fontSize=10, leading=17, wordWrap='CJK', spaceAfter=7),
    'small': ParagraphStyle('small', fontName='HeiseiKakuGo-W5', fontSize=8, leading=12, wordWrap='CJK', spaceAfter=4),
}


def p(text, kind='p'):
    return Paragraph(text, styles[kind])


def table(rows, widths):
    cells = [[p(str(c), 'small') for c in row] for row in rows]
    t = Table(cells, colWidths=widths, hAlign='LEFT', repeatRows=1)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e3f0ef')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8), ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LINEBELOW', (0, 0), (-1, -1), .3, colors.HexColor('#c9d9df')),
    ]))
    return t


def footer(canvas, doc):
    canvas.setStrokeColor(colors.HexColor('#c9d9df'))
    canvas.line(42, 39, A4[0] - 42, 39)
    canvas.setFont('HeiseiKakuGo-W5', 8)
    canvas.setFillColor(colors.HexColor('#587181'))
    canvas.drawString(42, 25, 'Physical AI 応用1 最終課題 | ID 44300 | 2026-11-02')
    canvas.drawRightString(A4[0] - 42, 25, str(doc.page))


def main():
    vision = json.loads((OUT / 'vision_metrics.json').read_text())
    trials = json.loads((OUT / 'evaluation.json').read_text())
    summary = json.loads((OUT / 'evaluation_summary.json').read_text())
    width = A4[0] - 84
    flow = [p('PrintFactory AI', 'title'), p('工場全体が、一つの身体になる。', 'sub')]
    flow += [p('1. 課題と着想', 'h'), p('人型ロボットに形を限定せず、天井カメラを「目」、AMRを「足」、固定ロボットを「手」と捉える。共通の観測と工程状態によって印刷物を後工程へ受け渡す、小規模な印刷工場をGenesis上に構築した。')]
    flow += [table([['身体の役割', '本作の構成', '担う機能'], ['目', '固定天井カメラ＋CNN', 'RGB画像から紙束・AMR・障害物を認識'], ['足', '全方向移動AMR 1台', '紙束の積載・搬送・障害物迂回'], ['手', '3軸直交型ロボット＋吸着', 'カメラ推定位置から後工程トレイへ移載'], ['協調', '状態機械・A*・PD制御', '工程順序、再計画、関節と走行の実行']], [74, 169, width-243])]
    flow += [p('実演：印刷完了 → 積載 → 搬送 → 障害物の認識・迂回 → 吸着移載 → 後工程完了', 'h')]
    image = OUT / 'completed.png'
    if not image.exists():
        image = OUT / 'preview.png'
    if image.exists():
        flow += [Image(str(image), width=width*.82, height=width*.82*900/1440)]
    flow += [p('画面はGenesisの実際の描画に説明と認識結果を重ねたもの。加工機内部は状態遷移として簡略化している。', 'small'), PageBreak()]
    flow += [p('2. AIと物理の接続', 'title'), p('観測が、次の運動を変える。', 'sub')]
    flow += [p('AIの担当と学習', 'h'), p('PyTorchの1×1畳み込みCNN（3→24→24→4）を使用。GenesisのRGB画像と、レンダラのインスタンスIDを正しく変換した教師ラベルで学習した。学習時だけ正解ラベルを使い、実行時のモデル入力はRGBのみ。色分けされた実験環境での認識であり、実工場の一般物体認識を主張するものではない。')]
    iou = vision['class_iou']
    flow += [table([['未見配置での認識評価', '実測値'], ['学習 / 評価シーン数', f"{len(vision['train_seeds'])} / {vision['heldout_count']}（seed分離）"], ['紙束 / AMR / 障害物のIoU', f'{iou[1]:.3f} / {iou[2]:.3f} / {iou[3]:.3f}'], ['紙束検出数', f"{vision['detected_heldout']} / {vision['heldout_count']}"], ['紙束の平均位置誤差', f"{vision['bundle_position_error_mean_m']*100:.2f} cm"], ['CNN推論時間（平均）', f"{vision['inference_mean_ms']:.2f} ms（GPU同期計測）"]], [width*.53, width*.47])]
    flow += [p('認識 → 計画 → 制御', 'h'), p('固定・校正済みカメラの領域中心を既知高さの平面へ投影し、紙束の位置を推定する。障害物領域を車体幅と余裕分で膨張し、既知の搬送通路内でA*経路を作る。通路が変化すると観測を更新し、一度停止して再計画する。AMRの走行と直交ロボットの関節はPD制御で物理ソルバーに入力する。認識の未検出時は搬送を停止する。')]
    flow += [p('簡略化と実装上の工夫', 'h'), p('紙束は色分けされた剛体ブロック。AMRは床面内の3自由度を持つ全方向移動の近似で、車輪接触からの駆動は再現しない。手は3軸直交ロボットで、幾何学的な逆運動学を使う。吸着は近接判定後の固定拘束で近似し、トレイ上で解除する。印刷は開始信号と積載、断裁・製本は時間付き工程状態で表現する。')]
    flow += [p('再現性と限界', 'h'), p('GPU：RTX A4000 16GB。Genesis 1.4.5、PyTorch 2.8.0+cu128。合成データの位置・撮影条件・色の範囲内で評価しており、実世界への転移、紙の変形、複数AMR、遮蔽や照明の大きな変化は今後の課題。学習したのは認識モデルで、経路探索・工程順序・運動制御は従来手法である。'), PageBreak()]
    flow += [p('3. 実験結果と再現方法', 'title')]
    rows = [['条件 / seed', '完了', '時間 [s]', '障害物接触ステップ', '再計画']]
    for r in trials:
        duration = '未計測' if r['duration_s'] is None else f"{r['duration_s']:.2f}"
        contacts = '未計測' if r['obstacle_contact_steps'] is None else str(r['obstacle_contact_steps'])
        replans = '未計測' if r['replans'] is None else str(r['replans'])
        rows.append([f"{'障害物' if r['obstacle'] else '通常'} / {r['seed']}", '成功' if r['completed'] else '失敗', duration, contacts, replans])
    flow += [table(rows, [150, 50, 75, 140, width-415])]
    for label, key in [('通常', 'normal'), ('障害物追加', 'obstacle')]:
        r = summary[key]
        duration = '未計測' if r['mean_duration_s'] is None else f"{r['mean_duration_s']:.2f}秒"
        flow += [p(f"{label}：{r['completed']}/{r['trials']}件完了、平均{duration}、障害物接触{r['obstacle_contact_steps']}ステップ（計測可能{r.get('contact_metrics_available_trials',r['trials'])}試行）。例外{r.get('errors',0)}件。", 'small')]
    for r in trials:
        if 'error' in r:
            from xml.sax.saxutils import escape
            flow += [p(f"例外記録 seed={r['seed']} / 障害物={r['obstacle']}：{escape(r['error'])}", 'small')]
    flow += [p('成功判定と測定範囲', 'h'), p('吸着解除後、紙束が後工程トレイ内に残れば成功。時間は工程完了までで、失敗は100秒で打ち切り、成功後の表示7秒を除く。平均は失敗を含む全計測試行から算出。接触値はAMRと追加障害物の接触ステップ数で、工場全体の安全性は保証しない。全10試行を保存した。')]
    failures = [r for r in trials if not r['completed']]
    if failures:
        lost = [r for r in failures if r.get('trajectory') and r['trajectory'][-1]['detection_age_s'] > .6]
        flow += [p(f"失敗の考察：全{len(failures)}件の失敗のうち、{len(lost)}件では最終観測が古くなり、把持前の認識喪失が記録された。架台・ハンドによる遮蔽の影響が疑われる。見失ったまま処理を続けず停止する挙動は確認できた。複数視点のカメラや遮蔽を避ける接近経路が改善候補である。", 'small')]
    flow += [p('実行と提出', 'h'), p('READMEの手順で専用環境を準備後、run.ps1 train / demo / evaluate を実行。学習済み重みvision.pt、評価JSON、依存版一覧、ソースとテストを同梱。提出用MP4をYouTubeへアップロードし、公開GitHub URLと本PDFをOmniCampusで提出する。アカウント名・IDは提出時に指定する。')]
    flow += [p('参考資料', 'h')]
    for text in [
        'Genesis公式：genesis-world.readthedocs.io（導入、ロボット制御、描画、固定拘束）',
        'HEIDELBERG：heidelberg.com / Postpress robotics（印刷後工程ロボットの事例）',
        'Open-RMF：www.open-rmf.org（異種ロボットと設備の連携という考え方）',
        'PyTorch：pytorch.org/docs（CNN学習とGPU推論）。詳細URLとライセンスはTHIRD_PARTY.md。',
    ]:
        flow.append(p(text, 'small'))
    SimpleDocTemplate(str(OUT / 'PrintFactory_AI_report.pdf'), pagesize=A4, rightMargin=42, leftMargin=42,
                      topMargin=42, bottomMargin=55, title='PrintFactory AI - Physical AI Final Assignment', author='').build(flow, onFirstPage=footer, onLaterPages=footer)
    print(OUT / 'PrintFactory_AI_report.pdf')


if __name__ == '__main__':
    main()
