# PrintFactory — 工場を分散した身体として動かす

提出用は **1ジョブを印刷から梱包まで、SIM時刻を飛ばさず収録した連続動画**です。アカウントIDは **44300**。Jeff 2Bが通路画像と工程状態を判断し、ViNT / NoMaDの公開移動ロボット基盤モデルが2台のAMRのwaypointを生成します。Genesisの接触で紙束を移載します。追加学習はありません。

## 提出動画：1分32.85秒、2倍速、カットなし

ジョブB（4ページのA4二つ折りリーフレット100部）をSIM 0秒に投入し、181.69秒に完成しました。原紙在庫400枚から100枚を使用します。枚葉両面UV印刷→硬化・検査・紙揃え信号→折り→仕分け→断裁・梱包を扱い、この製品では針綴じを省略します。

撮影はSIM 0.05〜185.70秒。完了後も実際のSIMを4秒進めて記録しています。20fpsの撮影元の**全3,714フレームを40fpsで保存**して2倍速にし、途中のカット・フレーム間引き・位置補間・静止画カードを使いません。SIM時計は各フレーム0.05秒ずつ進みます。機械の加工時間やAMRの速度を短縮してはいません。

全1ジョブ・100部、4回すべての移載で支持条件を確認しました。Jeffは6回判断し、ViNTは102回、NoMaDは94回実推論しました。Jeffによる逸脱後の再試行は1回です。工場俯瞰・天井画像・ジョブ・担当・積載・判断は同じSIM時刻で表示します。

- [提出用連続動画](output/PrintFactory_Jeff_demo_44300.mp4)
- [提出用PDF](output/説明資料_PAI最終課題_44300.pdf)
- [コード一式](output/submission_jeff_code_44300.zip)
- [連続映像のフレーム対応記録](output/jeff_factory/jeff_single/video_edit.json)
- [成果物検証](output/jeff_factory/artifact_check.json)
- [単一ジョブの実行記録](output/jeff_factory/jeff_single/result.json)

実行は setup-jeff-factory.ps1 → run-jeff.ps1。映像生成は scripts/compose_continuous_jeff_video.py。詳しい手順と制約は [README_JEFF.md](README_JEFF.md) を参照してください。3分を超える結果は映像生成を拒否し、途中を省略して収める処理には切り替えません。

## AIと従来制御の境界

Jeffの視覚段は固定通路RGBから direct / south を判断します。作業選択段は画像判定とジョブ・PLC・候補をテキストで受け、作業・担当AMR・経路を選びます。全景RGBを作業選択段に使ったという主張はしません。ViNT / NoMaDは前方RGB履歴と目標RGBを実際に入力する移動ロボット基盤モデルで、マニピュレータVLAではありません。

指令平滑化・加減速制限、初期/再試行時の向き、精密ドッキング、横押し、排他・安全停止、機械内部のPLC状態は従来制御です。共有通路では1台ずつ走ります。紙は100枚の剛体束で、単葉給紙・インキ・柔軟紙・UV反応・刃・針の内部物理やAIによる印刷品質検査は再現していません。既知地図の工程管理・搬送は従来制御でも実現でき、AIの必然性・最適性・速度優位性は未立証です。

## 複数ジョブ版の参考証跡

元の3ジョブ版も残しています。[実行ログ](output/jeff_factory/jeff/result.json) は778.15 SIM秒で冊子100冊・リーフレット200部、16回の支持済み移載を記録しています。こちらの旧編集動画には時刻の省略があり、新しい提出動画のフレームや成功件数には混ぜません。旧RoboBrain単一ジョブ版は [履歴](docs/superpowers/README_ROBOBRAIN_HISTORY.md) です。

GitHub公開先： https://github.com/rutiruk/physical-ai-print-factory-44300 。この作業でのYouTube公開・OmniCampus提出は未実施です。
