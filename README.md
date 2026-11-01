# PrintFactory — 工場を分散した身体として動かす

現在の実装は **Jeff 2Bによる通路画像判断・非同期の工程統制と、ViNT / NoMaDによる2台のAMR移動**です。不定期に到着する3つの印刷ジョブを、Genesis上で印刷から中綴じ・断裁・梱包まで扱います。追加学習は行いません。提出アカウントIDは **44300** です。

実行手順、AIと従来制御の境界、設備条件、検証方法は [README_JEFF.md](README_JEFF.md) を参照してください。起動は setup-jeff-factory.ps1 → run-jeff.ps1 です。

AMR改修後の通し実行は778.15 SIM秒で冊子100冊とリーフレット200部を完成し、16回すべての移載で支持条件を確認しました。Jeffは20回判断し、ViNTは402回、NoMaDは366回の移動推論を実行しました。逸脱後の再試行をJeffが1回選択しています。納期からの遅れは A: 0.00秒 / B: 32.65秒 / C: 28.14秒 です。

AMRには通常走行の指令平滑化と加減速制限を加え、直線途中の画像目標21回を停止せずにつないでいます。27,189サンプルの適用指令は設定内でした。切替前後±0.1秒の位置ログでも最小速度0.398 m/sで、途中停止がないことを確認しました。曲がり角・積み降ろしでは停止します。これは従来のアクチュエータ制御で、基盤モデルのwaypointを置き換えません。

動画は工場俯瞰、ジョブ到着、Jeffの選択、各AMRの担当・積載物、工程進捗を共通SIM時刻で表示します。提出用は175.95秒（2分55.95秒）、2倍速と省略を明記しています。全16移載を残し、走行の一部を省略しています。全3519フレームを復号して確認し、PDFは3ページすべて描画・目視確認しました。AMR2の連続走行を確認する等速・カットなしの別動画もあります。

- [提出用同期動画](output/PrintFactory_Jeff_demo_44300.mp4)
- [AMR2の連続動作確認（等速・カットなし）](output/AMR_motion_check_44300.mp4)
- [提出用PDF](output/説明資料_PAI最終課題_44300.pdf)
- [コード一式](output/submission_jeff_code_44300.zip)
- [検証記録](output/jeff_factory/artifact_check.json)
- [指令の検証](output/jeff_factory/jeff/motion_audit.json)
- [中間目標切替時の実測速度](output/jeff_factory/jeff/handoff_motion_check.json)

ViNT / NoMaDは移動ロボット基盤モデルです。指令平滑化・加減速制限、初期/再試行時の向き、最大0.40mのドッキング、横押し、加工機内部、製造・安全ゲートは従来制御です。既知地図の搬送をAIなしで実装できること、AIの必然性・最適性・速度優位性を示していないことを明記します。

旧RoboBrain単一ジョブ版は [履歴](docs/superpowers/README_ROBOBRAIN_HISTORY.md) に保存しています。旧動画・PDF・ZIPを今回のJeff版の完成証拠に使いません。コード公開先は [https://github.com/rutiruk/physical-ai-print-factory-44300](https://github.com/rutiruk/physical-ai-print-factory-44300) です。YouTube公開・OmniCampusへの提出は未実施です。
