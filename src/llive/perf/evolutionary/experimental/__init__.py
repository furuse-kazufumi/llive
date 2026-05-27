# SPDX-License-Identifier: Apache-2.0
"""frozen: 未配線・北極星非直結で 2026-05-27 収束フェーズに隔離。復活可。

このパッケージには `src/llive/perf/evolutionary/` の中で以下の条件をすべて満たすモジュールを収容する:
- コア実行経路 (run_persona_evolution / EvolutionLoop / lldarwin_v2) から直接 import されない
- 北極星「連続進化 × ライブ MoA オーケストラ」に直結しない
- テスト依存がゼロまたは軽微

隔離日: 2026-05-27 (llive 収束フェーズ)
隔離理由: evolutionary/ の肥大化解消。コア最小セット (24 本) を明確化する。
復活方法: このディレクトリから evolutionary/ 直下に移動し、__init__.py に再追加するだけ。

現在の収容モジュール:
- latent_reservoir.py  — 潜在変異貯蔵庫 (import 元なし)
- fitness_rich.py      — rich multi-axis fitness (未配線)
- fitness_ucb.py       — UCB fitness factory (未配線、テストなし)
- scheduler.py         — AsyncioScheduler / MultiprocessingScheduler (loop.py は内部 _serial_scheduler を使用)
- parallel_mutation.py — 並列評価 (本体未使用)
- substrate_adapters.py — Rust/Python/etc adapter stub (未配線)
- mcp_substrate_adapter.py — MCP genome adapter (未配線)
- recursive_inference.py — 再帰推論 helper (未配線)
- frozen_registry.py   — 凍結レジストリ (未配線)
- meta_loop.py         — MetaEvolutionLoop (未配線)
- persona_extended.py  — persona 拡張定義 (未配線)
"""
