"""Three-page Japanese report; read current run evidence, never infer completion.

Default: output/jeff_factory/report_draft.pdf.  Pass --output for a reviewed
submission destination. This generator neither runs GPU models nor simulations.
"""
from pathlib import Path
import argparse
import json
import statistics
from xml.sax.saxutils import escape

from report import (A4, OUT, ROOT, Image, PageBreak, SimpleDocTemplate, Spacer,
                    colors, footer, p, styles, table)

FOLDER = OUT / 'jeff_factory'
WIDTH = A4[0] - 84


def read(path):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


def median(items):
    return f'{statistics.median(items):.1f} ms' if items else '未計測'


def safe(value):
    return escape(str(value))


def probe_row(filename, label):
    data = read(FOLDER / filename)
    trials = data.get('trials', data.get('image_trials', []))
    correct = sum(t.get('choice') == t.get('expected') for t in trials)
    return [label, f'{correct}/{len(trials)}' if trials else '未計測',
            median([t['latency_ms'] for t in trials if 'latency_ms' in t])]


def condition_probability(filename, condition, choice):
    data = read(FOLDER / filename)
    trials = data.get('trials', data.get('image_trials', []))
    values = [t.get('probabilities', {}).get(choice) for t in trials
              if t.get('condition') == condition]
    values = [v for v in values if v is not None]
    return f'{statistics.mean(values):.4f}' if values else '未計測'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=FOLDER / 'report_draft.pdf')
    args = parser.parse_args()
    run = read(FOLDER / 'jeff/result.json')
    events, decisions, nav = (run.get(k, []) for k in ('events', 'decisions', 'navigation'))
    jobs = run.get('state', {}).get('jobs', [])
    done = [j for j in jobs if j.get('completed') is not None]
    verified = run.get('status') == 'complete' and run.get('success') is True and len(done) == 3
    badge = '全ジョブ完了（ログ確認）' if verified else '検証中 / 全工程の成功は未確定'
    pushes = [e for e in events if e.get('event') == 'PHYSICAL_PUSH']
    models = run.get('models', {})
    jeff = models.get('jeff', {}).get('model', {})
    nav_models = models.get('navigation', {}).get('models', {})
    styles['title'].fontSize = 24; styles['title'].leading = 31
    styles['p'].fontSize = 9.1; styles['p'].leading = 14.7; styles['p'].spaceAfter = 6
    styles['h'].fontSize = 12.5; styles['h'].leading = 18; styles['h'].spaceBefore = 10
    styles['small'].fontSize = 7.6; styles['small'].leading = 11.2
    flow = [p('Jeff PrintFactory / 44300', 'title'),
            p('非同期の印刷工程を、基盤モデルと物理でつなぐ。', 'sub'),
            p(badge, 'h'),
            p('固定通路カメラを目、異なる移動基盤モデルで動く2台のAMRを足、接触式の横押しローダーを手とするGenesis工場。後着の短納期ジョブと設備状態を見て、Jeffが実行可能な作業から次の作業・担当・経路を選ぶ。公開重みをそのまま推論し、追加学習・追加学習データ収集・アダプタ適用は行わない。'),
            table([['ジョブ','到着 [s]','製品 / 部数','締切 [s]'],
                   ['A','0.0','8p冊子 / 100冊','600'],['B','8.5','4p二つ折り / 100部','350'],
                   ['C','23.7','4p二つ折り / 100部','750']], [90,95,WIDTH-280,95]),
            p('工程と設備が決める制約', 'h'),
            p('校了・面付け承認 → 枚葉両面UV印刷 → UV完了・検査信号・紙揃え → 二つ折り → ジョブ別仕分け → 冊子は丁合・中綴じ、1枚折りのリーフレットは綴じ省略 → 断裁 → 梱包。原紙400枚をAの2フォーム・B/C各1フォームへ割り当て、合計300部（冊子100冊・リーフレット200部）を作る。白紙在庫は印刷開始時にジョブへ割り当てる。'),
            p('折り出口が1カセットのため各ジョブの内側折丁を先に処理する。丁合はx=1.6 / 2.0 / 2.4 mの3カセットで分離し、別ジョブの折丁を混ぜない。通路の排他トークンは同時に動くAMRを1台に制限する。加工と判断は並行するが、2台が同時走行する実験ではない。')]
    image = FOLDER / 'jeff/latest.png'
    if image.exists():
        from PIL import Image as PILImage
        with PILImage.open(image) as im:
            w, h = im.size
        flow += [Image(str(image), width=min(WIDTH, 170*w/h), height=min(170, WIDTH*h/w)),
                 p('実行ログのGenesis描画。俯瞰画像は動画・証跡に保存し、Jeffの作業選択段の入力とはしない。','small')]
    flow += [PageBreak(), p('AIの役割と実行証跡', 'title'),
             table([['担当','実際の入力 → 出力'],
                    ['Jeff 2B v1.2 / 視覚段','固定通路RGB → direct / southの確率と選択。手書きの色判定器は使わない。'],
                    ['Jeff / 作業選択段','通路判定＋ジョブ/PLC状態＋候補の効果をテキストで入力 → 作業・AMR・経路。俯瞰画像は消費しない。'],
                    ['AMR1 ViNT / AMR2 NoMaD','前方RGB履歴＋目標RGB → 学習済み局所waypoint → PD追従。公開チェックポイントを実推論。'],
                    ['従来制御・工程モデル','加減速制限、初期/再試行時の向き、最大0.40 mの精密ドッキング、横押し、排他/接触停止、加工時間・PLC品質ゲート。']], [118,WIDTH-118]),
             p('ViNT / NoMaDは移動ロボットのナビゲーション基盤モデルであり、マニピュレータのVLAではない。既知地図の短区間ごとに目標RGBを与える。逸脱監視は停止だけを行い、Jeffが再試行を選ぶと向きを整え、再観測した基盤モデルの移動を再開する。各目標で最大4回とし、従来軌道で代行しない。紙束の移載はGenesisの押し板・橋・受台との接触を用い、加工機内部のインキ、柔軟紙の折り、針、刃は状態遷移の近似である。UV完了や印刷品質をカメラで測定できたという主張はしない。'),
             p('保存ログからの実測（生成時点）','h'),
             table([['項目','記録値'],
                    ['実行状態', f"{safe(run.get('status','未開始'))} / SIM {run.get('simulation_seconds',0):.2f} s / {badge}"],
                    ['実行の実時間',f'{run.get("wall_seconds",0):.2f} s（初期化後の実行ループ、映像編集前）'],
                    ['ジョブ・完成部数',f'{len(done)}/3ジョブ、{sum(j.get("copies",0) for j in done)}/300部'],
                    ['移載支持条件', f'{sum(bool(e.get("supported")) for e in pushes)}/{len(pushes)}件（支持・高さ・向きの実装判定）'],
                    ['Jeff判断',f'{len(decisions)}回、推論中央値 '+median([d['latency_ms'] for d in decisions if 'latency_ms' in d])],
                    ['Jeffの再試行選択',f'{sum(e.get("event")=="NAV_RECOVERY_CHOSEN" for e in events)}回（停止後の再試行も作業/待機とともに選択）'],
                    ['移動モデル推論', ' / '.join(f'{m}: {sum(str(n.get("model", "")).lower()==m for n in nav)}回' for m in ('vint','nomad'))],
                    ['完了時刻 / 遅れ', ' / '.join(f'{j["id"]}: {j["completed"]:.2f}s / {max(0,j["completed"]-j["due"]):.2f}s' for j in done) or '完了ジョブなし']], [118,WIDTH-118]),
             p('仕上げの記録：'+(' / '.join(f'{e["job"]}: {safe(e.get("binding"))}, stitched={e.get("stitched")}' for e in events if e.get('event')=='PROCESS_COMPLETE' and e.get('machine')=='finishing') or '未完了')+'。締切を超えたジョブは遅れを上表に明記する。','small'),
             p('判断中もSIM時計・加工タイマを進める。観測世代を記録し、古い判断を拒否する。実行可能候補の生成と安全制約は従来コード、候補間の選択はJeffが担う。未完了・失敗・初期試行を完了デモへ置き換えない。','small'),
             p('公開モデルの固定と再現性','h'),
             p('Jeff revision: '+safe(jeff.get('revision','未記録'))+'<br/>Jeffコード: '+safe(jeff.get('vendor_revision','未記録')),'small')]
    for key, value in jeff.get('checkpoint_sha256', {}).items():
        flow += [p(safe(key)+': '+safe(value),'small')]
    for key, value in nav_models.items():
        flow += [p(safe(key)+' SHA256: '+safe(value.get('checkpoint_sha256','未記録')),'small')]
    flow += [PageBreak(),p('評価・限界・提出状況','title'),
             p('入力を変えた小規模の機能評価','h'),
             table([['閉塞 / 非閉塞 × 各2回','正しい経路選択','推論中央値'],
                    probe_row('jeff_probe_controlled.json','Jeff 0.8B / 全体RGB'),
                    probe_row('jeff_probe_2b_controlled.json','Jeff 2B / 全体RGB'),
                    probe_row('jeff_probe_2b_roi.json','Jeff 2B / 固定通路ROI')], [WIDTH-185,85,100]),
             p('2Bでも全体画像の閉塞時SOUTH確率は'+condition_probability('jeff_probe_2b_controlled.json','blocked','south')+'と僅差だった。固定ROIでは非閉塞DIRECT '+condition_probability('jeff_probe_2b_roi.json','clear','direct')+'、閉塞SOUTH '+condition_probability('jeff_probe_2b_roi.json','blocked','south')+'。実際の固定通路カメラの初回閉塞観測はSOUTH '+(f"{decisions[0].get('visual',{}).get('probabilities',{}).get('south',0):.4f}" if decisions else '未計測')+'。反復は同じ2画像であり、一般的な視覚精度・工場全体の成功率を意味しない。'),
             p('全体RGBを作業選択にも渡した初期版は、障害物を理由に安全な局所加工まで待機した。待機では障害物を除去できないことを候補効果へ反映し、作業選択をテキスト入力に分離した。修正入力の再推論で折り開始の確率0.7288を記録した。これは単一状態の再評価で、複数条件の成功保証ではない。'),
             p('Jeff上流のv1.2資料はEnglish / text-onlyと注意している。画像テンソルを受け取れることだけで視覚性能を保証せず、本実験の入力条件で限定検証する。失敗した0.8Bや移動目標の疎さ・単一丁合カセットによる途中試行も履歴として残す。'),
             p('「従来制御でもよいのでは？」への回答','h'),
             p('その通りである。既知地図の搬送・工程管理は従来手法で実装でき、AIの不可欠性・速度優位性・最適性は未立証。本作の検証点は、公開モデルの実推論が観測から作業選択と移動waypointへ接続されることにある。目標画像・既知通路・候補記述への依存、単一試行、未知工場・実機転移、柔軟紙・単葉給紙、品質検査AIは未検証。'),
             p('講義要件と提出の確認','h'),
             p('物理シミュレータ：Genesis。基盤モデル：Jeff / ViNT / NoMaDの公開重み。学習：追加なし。動画：俯瞰・到着通知・判断・AMR積載を共通SIM時刻に同期し、2倍速と省略区間を明記する。完成判定はresult.json、映像編集はmanifestを照合してから行う。提出名：説明資料_PAI最終課題_44300.pdf。YouTube・公開GitHub・OmniCampusへの公開/提出は未実施。'),
             p('一次資料・同梱証跡','h'),
             p('<link href="https://github.com/firelex/jeff">Jeff公式コード</link> / <link href="https://huggingface.co/jeff-legacy/Jeff-Qwen3.5-2B">Jeff 2B v1.2公開重み</link> / <link href="https://github.com/robodhruv/visualnav-transformer">ViNT / NoMaD公式実装</link><br/><link href="https://www.dnp.co.jp/media/detail/20168683_1563.html">DNP 製版</link> / <link href="https://www.dnp.co.jp/media/detail/20169183_1563.html">DNP 印刷</link> / <link href="https://www.dnp.co.jp/media/detail/20169338_1563.html">DNP 製本</link><br/>再実行：setup-jeff-factory.ps1、scripts/jeff_factory_demo.py。証跡：output/jeff_factory/jeff/result.json、各probe JSON、画像hash、モデルrevision。詳細はdocs/superpowers/README_JEFF_RUNTIME.md。評価表は集計途中のevaluation.jsonを転記せず、保存結果を直接読む。モデル重み・仮想環境・講義資料はソース提出ZIP外。','small')]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(str(args.output),pagesize=A4,leftMargin=42,rightMargin=42,
                      topMargin=34,bottomMargin=52,title='Jeff PrintFactory - Physical AI Final Assignment').build(flow,onFirstPage=footer,onLaterPages=footer)
    print(args.output)


if __name__ == '__main__':
    main()
