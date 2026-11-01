# Jeff印刷工場の提出メモ

通し実行、同期動画の全フレーム、PDF全3ページ、モデル・画像・数量・レシピ・移載の照合を確認済みです。GitHub公開先：https://github.com/rutiruk/physical-ai-print-factory-44300 。YouTube公開とフォーム送信は未実施です。

- 同期動画：output/PrintFactory_Jeff_demo_44300.mp4
- 説明資料：output/説明資料_PAI最終課題_44300.pdf
- ソースと記録：output/submission_jeff_code_44300.zip
- 検証結果：output/jeff_factory/artifact_check.json
- 実行手順：README_JEFF.md、setup-jeff-factory.ps1、run-jeff.ps1

講義指定の提出名は「説明資料_PAI最終課題_44300.pdf」です。内部確認用に同内容の PrintFactory_Jeff_report.pdf も保存します。

## YouTube文面案

タイトル：PAI最終課題_44300

PrintFactory — 印刷工場を、分散した身体として動かす。

不定期に到着するA4冊子（8ページ100冊）と二つ折りリーフレット（4ページ100部×2）のジョブをGenesis工場で扱います。枚葉両面UV印刷、硬化・検査信号、紙揃え、折り、ジョブ別仕分けを行い、冊子は中綴じ、リーフレットは綴じを省略して断裁・梱包へ進みます。原紙は計400枚、完成は計300部です。

公開Jeff 2B v1.2が固定通路RGBから通行可否を判断し、その結果とジョブ・PLC状態から次の作業・AMR・経路を選びます。AMR1はViNT、AMR2はNoMaDの公開ロボット基盤モデルで、前方RGB履歴と目標RGBから移動waypointを生成します。追加学習・追加学習用データ収集はありません。

加減速制限、初期/再試行時の向き、最大0.40mの精密ドッキング、横押しと安全・製造ゲートは従来制御です。100枚の剛体束を接触で搬送し、インキ・柔軟紙・針・刃・UV反応・機械内部は工程状態で近似します。UVや印刷品質をAIカメラで測定した実験ではありません。共有通路は排他利用し、加工・判断と搬送は並行します。

映像は共通SIM時刻で工場俯瞰、到着通知、判断、AMRの担当・積載物、工程を同期しています。2倍速と一部の移動・待機省略を表示し、編集区間を記録します。モデルロードは動画外で、推論中も物理時計は進みます。実機生産速度の再現ではありません。

既知地図の搬送は従来制御でも実現できます。AIの必然性や速度・最適性の優位は主張せず、公開モデルの実推論が判断と物理動作に接続される範囲と限界を報告します。

- Jeff：https://github.com/firelex/jeff
- ViNT / NoMaD：https://github.com/robodhruv/visualnav-transformer
- コード：https://github.com/rutiruk/physical-ai-print-factory-44300

## 公開・提出

講義指定は動画1〜3分（2倍速可）、コード、短いPDFです。動画をYouTubeの限定公開以上へ、コードを公開GitHubへ配置し、そのURLとPDFをOmniCampusへ提出します。GitHubでコード・動画・PDFを公開します。YouTube公開・OmniCampusへのフォーム送信は未実施です。

旧RoboBrain版は docs/superpowers/SUBMISSION_ROBOBRAIN_HISTORY.md に分けています。今回の提出はJeff版の検証済み成果物を使います。講義資料・モデル重み・仮想環境はソースZIPへ含めません。
