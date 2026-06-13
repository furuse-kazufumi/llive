# SPDX-License-Identifier: Apache-2.0
"""Strategy variants for SynapticSelector experiments.

このパッケージは「同じ抽象操作の複数 implementation」をまとめて, それぞれ
独立に benchmark / SynapticSelector に load しやすい形で提供する.

各 module は production code を **変更しない** — 既存 hot path への注入
判断は別レイヤで行う.

See: ``docs/experiments/optimize_core_2026_05_20.md`` (Phase B 系列).
"""
