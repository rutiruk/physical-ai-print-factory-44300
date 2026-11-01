# 参考資料・依存ライブラリ

## アイデアの背景

- HEIDELBERG: 印刷後工程のロボット化の産業事例。
  https://www.heidelberg.com/global/en/print_and_packaging/finishing/robotics_1/postpress_robotics.jsp
- Open-RMF: 異種ロボット群と設備の連携という考え方の参考。
  https://www.open-rmf.org/

本作はOpen-RMFを組み込んだ製品ではありません。工場全体を身体と捉える着想を、小規模な独自シーンで実装します。

## 実装資料

- Genesis installation: https://genesis-world.readthedocs.io/en/v1.4.5/user_guide/overview/installation.html
- Genesis robot control: https://genesis-world.readthedocs.io/en/latest/user_guide/getting_started/control_your_robot.html
- Genesis runtime weld constraints: https://genesis-world.readthedocs.io/en/latest/user_guide/robot_control/constraints.html
- Genesis rendering: https://genesis-world.readthedocs.io/en/latest/user_guide/rendering/index.html
- PyTorch: https://pytorch.org/docs/stable/index.html

## 主なライセンス

- 印刷工程版のロボティクス基盤モデル: [BAAI/RoboBrain2.5-4B](https://huggingface.co/BAAI/RoboBrain2.5-4B)、公式revision `ec4b3bf5e969b48ad17df432b479c10402a0079b`、Apache-2.0。視覚理解・AMR/経路選択を担当。低レベル連続動作VLAとは区別。重みはZIP外で公式配布から取得。
- 印刷工程の知識: DNP工場見学#1/#2/#3、JAGATポストプレス、KOMORI H-UV、Horizonの中綴じ機資料。出典と採用/不採用の工程を `docs/superpowers/specs/2026-11-01-print-process-design.md` に整理。図や写真は転載せず、工場形状・紙面模式図は独自作成。

- LeRobot / SmolVLA: Apache-2.0。公開モデル `lerobot/smolvla_libero` revision `a24f1f380461b665158d52acd140152c79e8b36d`。モデル重みはZIP外で取得。
- LIBERO: MIT。公式repository revision `8f1084e3132a39270c3a13ebe37270a43ece2a01`。環境・Panda・公開初期状態・オブジェクトはこの資産を参照。各サブ資産のライセンスも元リポジトリを参照。ZIPにはこれらを含めず公式から取得。
- robosuite 1.4.1: MIT。OSCの規約に対応したコード、およびWindows DLL/GLFWの限定的互換パッチを使用。
- MuJoCo: Apache-2.0。最終版で描画・運動学・逆動力学を担当。物理の時間更新はGenesis。

- Genesis World: Apache-2.0（依存パッケージはそれぞれのライセンス）。
- PyTorch: BSD-style。
- NumPy / SciPy: BSD-style。
- Pillow: HPND。
- ReportLab: BSD-style。
- imageio / imageio-ffmpeg: BSD-2-Clause。動画エンコーダのライセンスは配布バイナリの構成に依存。
- PyAV: BSD-3-Clause。録画にはPyAV経由でFFmpegのH.264エンコーダを利用。

AMRと直交型ロボットのMJCF、および工場の形状は本プロジェクトで作成したものです。
配布講義資料とRoboOps ZIPは参照のみで、提出用コードZIPには含めません。
動画の日本語フォントはWindows搭載の游ゴシックを利用します。フォントファイルは再配布しません。
PDFはReportLabの日本語CIDフォント参照を使用します。
# Jeff / ViNT / NoMaD（非同期版）

Jeff code: https://github.com/firelex/jeff at `3720e7c66d73b79a6e90189f3d5b0d6ecf03ddc0`, MIT (Mathias Strasser / Denis Yarats). Official 2B v1.2 weights: `jeff-legacy/Jeff-Qwen3.5-2B`, revision `d2ffa3a22f3dea8cfdd67bac595d4e8ad3681b2e`; downloaded model LICENSE is Apache-2.0. Weights are not included in the source archive. Upstream English/text-only caveat and the narrow camera evaluations are retained in the runtime README.

ViNT / NoMaD inference source: https://github.com/robodhruv/visualnav-transformer at `dca79815b704e5aa9c6bdc3082351f9e3b2848c2` (MIT). Diffusion architecture dependency: https://github.com/real-stanford/diffusion_policy at `5ba07ac6661db573af695b419a7947ecb704690f` (MIT). Checkpoints are downloaded from the authors' linked Google Drive; they are not redistributed. File IDs, hashes and runtime conventions are in `assets/navigation/README.md`.

