# SPDX-License-Identifier: Apache-2.0
"""llive.learning — Learning rules and weight update primitives.

現状は **誤差拡散学習法 (EDLA, 金子勇 1999) skeleton** + 比較用の
Backpropagation を含む。詳細は `docs/references/historical/edla_kaneko_1999.md`
と `docs/llmesh_p2p_mesh_rfc.md` の Phase 5 を参照。
"""

from llive.learning.edla import EDLALearner, TwoLayerNet, mse_loss

__all__ = ["EDLALearner", "TwoLayerNet", "mse_loss"]
