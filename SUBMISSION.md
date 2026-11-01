# 提出メモ — アカウントID 44300

提出動画を単一ジョブの連続映像に変更しました。コード公開先： https://github.com/rutiruk/physical-ai-print-factory-44300 。この作業でのYouTube公開・OmniCampusへのフォーム送信は未実施です。

- 動画：output/PrintFactory_Jeff_demo_44300.mp4（1分32.85秒、2倍速、カットなし）
- 説明資料：output/説明資料_PAI最終課題_44300.pdf
- コード：output/submission_jeff_code_44300.zip
- 主実行ログ：output/jeff_factory/jeff_single/result.json
- 確認：output/jeff_factory/artifact_check.json

## YouTube文面

タイトル：PAI最終課題_44300

PrintFactory — 印刷工場を、分散した身体として動かす。

本動画は1ジョブの印刷開始から梱包までを連続で収録します。ジョブBはA4二つ折りリーフレット（4ページ100部）。枚葉両面UV印刷、硬化・検査信号、紙揃え、折り、仕分け、断裁・梱包へ進みます。この製品は針綴じを省略します。原紙100枚を使用し、100部を完成しました。

公開Jeff 2B v1.2が固定通路RGBから通行可否を判断し、その結果とジョブ・PLC状態から作業・担当AMR・経路を選びます。AMR1はViNT、AMR2はNoMaDの公開基盤モデルを使い、前方RGB履歴と目標RGBから移動waypointを生成します。追加学習・追加学習用データ収集はありません。

撮影元の全3,714フレームを40fpsで保存した2倍速です。SIM時刻は0.05秒ずつ進み、途中のカット・フレーム間引き・位置補間・静止画カードはありません。全185.70 SIM秒を92.85秒で再生します。完了はSIM181.69秒、以後も4 SIM秒の実動作を収録しています。加工時間やAMR速度を短縮していません。

印刷ジョブ1件・100部、支持条件を満たす4回の接触移載、Jeffは6回の判断（各回に画像と作業選択の2段）、ViNTは102回、NoMaDは94回の移動推論を記録しました。逸脱停止後にJeffが1回再試行を選択しています。複数ジョブ版の記録は参考資料として別に残します。

加減速制限・初期/再試行時の向き・精密ドッキング・横押し・製造と安全ゲートは従来制御です。100枚の剛体束を接触で搬送し、インキ・柔軟紙・針・刃・UV反応・機械内部は工程状態で近似します。UVや印刷品質をAIカメラで測定した実験ではありません。共有通路は1台ずつ走行します。

既知地図の搬送は従来制御でも実現できます。AIの必然性や速度・最適性の優位は未立証で、公開モデルの実推論が判断と物理動作へ接続される範囲と限界を報告します。

- コード・証跡：https://github.com/rutiruk/physical-ai-print-factory-44300
- Jeff：https://github.com/firelex/jeff
- ViNT / NoMaD：https://github.com/robodhruv/visualnav-transformer

講義指定は動画1〜3分（2倍速可）、コード、短いPDFです。YouTubeを限定公開以上にして、そのURL・公開コードURLとPDFをOmniCampusへ提出します。元の3ジョブ編集動画にはSIM時刻の省略があるため、今回の提出動画は上記の連続版を使います。
