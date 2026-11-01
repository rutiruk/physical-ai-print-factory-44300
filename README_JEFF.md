# Jeff PrintFactory — 非同期印刷工場

印刷ジョブの到着に応じて、Jeffが作業・AMR・経路を選び、ViNTとNoMaDが各AMRの移動waypointを生成するGenesisシミュレーションです。公開重みの推論のみを使い、追加学習・追加学習データ収集は行いません。

## 実行

Windows / NVIDIA RTX A4000 16GB ×2 / CUDA 12.8で検証しています。GPU0はGenesis、GPU1はJeffと移動モデルです。

```powershell
# 基本環境がない場合のみ。既存の環境を上書きしないこと。
py -3.10 -m venv .venv
.venv\Scripts\python.exe -m pip install torch==2.8.0 torchvision==0.23.0 --index-url https://download.pytorch.org/whl/cu128
.venv\Scripts\python.exe -m pip install -r requirements.txt

.\setup-jeff-factory.ps1
.\run-jeff.ps1
```

再実行は同じポリシーの最新成果物を更新します。実行結果は `output/jeff_factory/jeff/result.json` です。`success: true`、`status: complete`、3ジョブ完成、支持条件を満たす16回の移載を確認して完成と判定します。実行途中の動画・JSONは完成品ではありません。

## 誰が何をするか

| 担当 | 入力と出力 |
|---|---|
| Jeff 2B v1.2・視覚段 | 固定通路のRGB → 通路の使用可否。画素の手書き判定器は使いません |
| Jeff・作業選択段 | 視覚段の結果、投入済みジョブ、PLC、全候補 → 印刷・折り・搬送・仕上げ・待機の選択 |
| AMR1・ViNT | 前方RGB履歴と目標RGB → 学習済みwaypoint |
| AMR2・NoMaD | 前方RGB履歴と目標RGB → 拡散方策のwaypoint |
| 従来制御 | waypointのPD追従、加減速制限、初期/再試行時の向き、最大0.40mの精密ドッキング、横押し、逸脱停止・通路排他 |
| 加工機モデル | 枚葉両面UV印刷、硬化・検査・紙揃え、折り、丁合、中綴じ、三方断裁、梱包の工程状態 |

俯瞰RGBは同期動画と観測証跡に使います。Jeffの作業選択段はテキスト入力で、通路の視覚段とは入力を分けています。ViNT / NoMaDは移動ロボット基盤モデルで、マニピュレータVLAではありません。紙束の搬送・支持・横押しは物理ですが、インキ、柔軟な紙、刃、針、単葉給紙は物理計算していません。原紙はジョブに共通の100枚束で、印刷開始時に割り当てます。模様は表示用の代理表現です。

## 印刷ジョブと設備

| ジョブ | 到着 [秒] | 製品 | 締切 [秒] |
|---|---:|---|---:|
| A | 0 | A4・8ページ中綴じ100冊 | 600 |
| B | 8.5 | A4・4ページ二つ折りリーフレット100部 | 350 |
| C | 23.7 | A4・4ページ二つ折りリーフレット100部 | 750 |

SRA3 100g/m²、計400枚から冊子100冊とリーフレット200部を製造します。Aは中綴じ、1枚を折るB/Cは綴じを省略して断裁・梱包します。折り出口は1カセット、丁合置場はジョブ別3カセットです。内側折丁から丁合し、数量・版・順序の混在を拒否します。印刷済みAが残る間でもBを先に製本できます。共有通路は1台分の排他資源であり、2台同時走行の実験ではありません。加工・推論・ジョブ到着は走行と並行します。

## 同期動画・提出物の作成

通し実行終了後に実施します。

```powershell
.venv\Scripts\python.exe scripts/summarize_jeff_factory.py
.venv\Scripts\python.exe scripts/compose_jeff_video.py
Copy-Item output/PrintFactory_Jeff_demo.mp4 output/PrintFactory_Jeff_demo_44300.mp4
.venv\Scripts\python.exe scripts/compose_amr_motion_check.py
.venv\Scripts\python.exe scripts/report_jeff.py --output output/PrintFactory_Jeff_report.pdf
Copy-Item output/PrintFactory_Jeff_report.pdf output/説明資料_PAI最終課題_44300.pdf
.venv\Scripts\python.exe scripts/check_jeff_artifacts.py
.venv\Scripts\python.exe scripts/package_jeff.py
Copy-Item output/submission_jeff_code.zip output/submission_jeff_code_44300.zip
```

動画は工場俯瞰、到着通知、Jeffの判断、AMRの担当・積載物、工程進捗を共通SIM時刻で表示します。2倍速と省略を明記し、全移載を残した1〜3分へ編集します。編集区間は `video_edit.json` に記録します。ソースZIPには重み・仮想環境・講義資料を含めません。

移動モデルが通路から逸脱した場合、従来の監視が停止だけを行います。Jeffが再試行を選んだ場合にのみ、向きを整え、RGB履歴と目標画像を更新して同じ基盤モデルの移動を再開します。再試行は局所目標ごとに最大4回です。従来の直線軌道で失敗を代行しません。

## 「従来制御でもよいのでは？」

既知地図の搬送と工程管理は従来手法でも実装できます。本実験はAIの不可欠性や最適性・速度優位性を証明するものではありません。検証点は、実際の公開モデル推論が画像から判断・移動に接続され、後着ジョブに応じて作業を選ぶことです。規則による製造ゲート・排他制御とAIによる候補選択を区別します。移動モデルの転移失敗、画像を見せた作業選択での不適切な待機など、途中失敗も保存しています。

Jeff上流のEnglish / text-only注意書きは継承します。2Bが同じ閉塞・非閉塞画像を選び分けた少数テストを、一般精度や未知工場の成功率とは扱いません。詳細な出典・モデル固定・再現手順は [実行環境](docs/superpowers/README_JEFF_RUNTIME.md)、[移動モデル](assets/navigation/README.md)、[印刷工程](docs/superpowers/specs/2026-11-01-print-process-design.md) を参照してください。

## AMRの動作修正（2026-11-02）

推論ごとの速度・旋回指令を100 Hzで平滑化し、通常走行で適用する速度指令の変化を0.6 m/s²、旋回速度指令の変化を0.9 rad/s²以下に制限します（剛体の実測加速度の上限保証ではありません）。直線途中の画像目標では停止せず次の画像目標へ進み、曲がり角・積み降ろしでは停止します。安全停止は平滑化より優先します。これは従来のアクチュエータ制御であり、ViNT / NoMaDのwaypointやJeffの経路選択を置き換えません。実行時の適用指令は motion_samples.json、集計は motion_audit.json に保存します。改修後の通し実行は778.15 SIM秒で全3件・300部を完了し、16回の移載すべてで支持条件を確認しました。27,189サンプルの指令ログで通常の加減速制限違反は0件、21回の直線内の画像目標を非ゼロの移動指令のまま通過しました。
