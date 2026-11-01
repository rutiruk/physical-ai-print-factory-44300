# PrintFactory — 印刷工程を持つ工場の分散した身体

天井カメラを目、AMR2台を足、水平移載ローダーを手として、**印刷から冊子の後加工まで**をGenesisで協調させる最終課題です。公開ロボティクス基盤モデル **BAAI/RoboBrain2.5-4B** を実GPU推論し、工場画像と設備/自己状態からAMRと搬送経路を選びます。追加学習用データの収集・追加学習はありません。

器を移載する旧SmolVLAデモは印刷工場の完成品として扱わず、今回の提出ZIPにも含めません。

## 製品と印刷プロセス

対象は **A4縦・左綴じ・16ページ・共紙中綴じ冊子100冊**。原紙SRA3（450×320mm）、100g/m²。4種類のフォームを各100枚、表裏に印刷します。

```text
入稿・校了 → 面付け・刷版承認 → 枚葉両面UV印刷
→ UV硬化完了・検査 → 紙揃え・天地確認 → 折り
→ 折丁丁合 → 中綴じ → 三方断裁 → 検品・梱包
```

今回は独立した折り機で折丁を作ってから丁合する方式です。平らな刷本を丁合してから折る製本ラインとは区別します。輪転の巻取・熱風乾燥、油性印刷の乾燥待ち、無線綴じもこの工程へ混ぜていません。

| フォーム | 表（左｜右） | 裏（左｜右） | 枚数 |
|---|---|---|---:|
| F1 外側 | 16｜1 | 2｜15 | 100 |
| F2 | 14｜3 | 4｜13 | 100 |
| F3 | 12｜5 | 6｜11 | 100 |
| F4 内側 | 10｜7 | 8｜9 | 100 |

丁合への供給は内側F4→F3→F2→外側F1。折り後225×320mm、綴じ後に背を残して天地と小口を210×297mmへ仕上げます。400枚から100冊を作り、紙の収支は5.7600kg＝製品4.9896kg＋断裁屑0.7704kgです。針金と梱包材の質量は含めません。

## 工程ゲートと物理の境界

- 校了/面付け承認なしでは印刷しません。裏面未印刷、未硬化、検査不良、未揃え、天地逆の束は折りへ渡しません。
- ジョブ・版違い、落丁、重複、誤順、枚数/紙質違いを丁合で止めます。未綴じは仕上げ断裁しません。
- AMR、リフト、パイルリフト、移載橋、受動ガイド、押し板と紙束の接触はGenesis物理です。搬送中の紙へ位置指令やweldを与えません。積み下ろしはXY・高さ・直立/天地・支持面との接触で採点します。
- 紙は100枚をまとめた剛体束です。印刷、UV反応、検査信号、紙揃え、折り、開いて入れ子にする丁合、針金、切断、梱包の内部は工程モデルです。折り/丁合/断裁の代理形状への切替は機械内で行います。
- UV完了・検査承認・ジョブ読取は模擬PLC/読取器信号。色差の画像検査、バーコード画像復号、単葉分離・柔軟紙・実機は未実装です。機種の完全なデジタルツインや実際の生産速度は主張しません。

## 基盤モデルは何をするか

天井RGBと、既知の候補軌道・車幅から作る通行帯画像をRoboBrainへ渡します。モデルの視覚判定を、同モデルのAMR/経路選択へつなぎ、その指示で実際のGenesisロボットを動かして再観測します。通行帯の切出しに障害物の正解座標やIDは使いません。

製造レシピ、工程ゲート、現在実行可能なタスク、関節PD、押し板は従来制御です。実行可能な搬送タスクは物理パイル/工程順の制約により各時点1件で、基盤モデルが製造順序を決めたとは言いません。選んだ経路の幾何干渉チェックは完全な位置センサー相当の状態を利用して拒否しますが、モデルの代わりに経路を選び直しません。

**RoboBrainはロボティクス向け視覚・行動計画基盤モデルです。関節の連続行動を直接生成する低レベルVLAとは区別します。** 公式checkpointを厳密にロードし、revision・重みSHA256・観測画像hash・生の応答・判断・推論時間を保存します。

「それPhysical AIでなくてもよい？」：この構造化した工程は従来制御でも実装できます。基盤モデルの必然性や、強い従来手法への優位性は未証明です。全体画像だけの初期推論では閉塞経路を選ぶ失敗があり、候補通行帯を提示する構成へ修正しました。失敗のJSONも残しています。

## 実行・成果物

このPCはWindows、Python3.10、RTX A4000 16GB×2です。GenesisはGPU0、約44.38億パラメータの基盤モデルはGPU1を使用します。`.venv` と `.venv-policy` は作成済みです。

`run.ps1` の既定動作も新しい印刷工程版です。`run.ps1 printing-rules` で従来方式を実行できます。

```powershell
$env:PYTHONUTF8 = '1'
.\.venv\Scripts\python.exe scripts/print_process_demo.py --policy robobrain
# 従来方式の独立した参照実行（モデル失敗時の自動代役ではありません）
.\.venv\Scripts\python.exe scripts/print_process_demo.py --policy rules
```

別環境では、CUDA対応PyTorchを入れたPython3.10の `.venv` へ `requirements.txt` をインストール後、`setup-printing.ps1` で独立した方策環境と公式モデルを用意します。モデルは約9GBで、重みをコードZIPに含めません。2GPU構成とWindowsの游ゴシックを前提とします。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cu128
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
powershell -ExecutionPolicy Bypass -File .\setup-printing.ps1
```

- 提出動画：`output/PrintFactory_Printing_demo.mp4`（本編は物理時間2倍速、空車移動・工程待機を一部編集、推論待ちを除外）
- 説明資料：`output/PrintFactory_Printing_report.pdf`
- コード・測定記録：`output/submission_code.zip`
- 通し実行：`output/printing/result_robobrain.json` / `result_rules.json`
- 条件変更の静止画推論：`output/printing/policy_comparison.json`（製造全体の成功率とは区別）
- 仕上げ失敗を含む過去の記録：`output/printing/*failed_finishing.json`、初期推論の `brain_*probe.json` 等

最終の基盤モデル版は物理時間360.34秒で工程完了、AMR1/2を使用、搬送判断8回、積み下ろし16/16回が支持・高さ・姿勢条件を満たしました。従来方式の参照も完了。関連テストは環境を分けて計52件通過しました。過去の調整失敗を含む選択したデモであり、一般的な製造成功率ではありません。

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_printing.py tests/test_factory_policy.py tests/test_print_workshop.py tests/test_finishing.py tests/test_run_artifacts.py -q
```

上記は新しい印刷工程版25件です。本PCの計52件には旧版の検証も含みます。旧VLA用の公開資産がない環境では、その追加検証をスキップします。

## 学習した印刷工程の出典

[DNP：版](https://www.dnp.co.jp/media/detail/20168683_1563.html)、[DNP：印刷](https://www.dnp.co.jp/media/detail/20169183_1563.html)、[DNP：製本](https://www.dnp.co.jp/media/detail/20169338_1563.html)、[JAGAT：ポストプレス](https://www.jagat.or.jp/cat5/dtp/exam/curriculum/3-7)、[KOMORI：H-UV](https://www.komori.com/ja/jp/information/news/2019/0130_217.html)、[Horizon：製本ライン](https://www.horizon.co.jp/products/catalog/j_pdf/j001st/01sl_pdf/icestitchilinermarkiv_j.pdf)。調査と設計上の判断は `docs/superpowers/specs/2026-11-01-print-process-design.md` に記録しました。

モデル：[BAAI/RoboBrain2.5-4B](https://huggingface.co/BAAI/RoboBrain2.5-4B)、[公式コード](https://github.com/FlagOpen/RoboBrain2.5)。Apache-2.0、revision `ec4b3bf5e969b48ad17df432b479c10402a0079b`。
