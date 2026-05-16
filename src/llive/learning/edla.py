# SPDX-License-Identifier: Apache-2.0
"""Error Diffusion Learning Algorithm (EDLA) — skeleton implementation.

歴史的経緯は `docs/references/historical/edla_kaneko_1999.md` を参照。
金子勇氏 1999 の原 EDLA の正確な再現ではなく、その**精神**(BP の大域的
逆伝播を避け、誤差を局所的に拡散して各層を更新する) を 2-layer net で
最小実装したもの。比較対象として **Backpropagation (BP)** も同じ
インタフェースで提供する。

設計:
  * `TwoLayerNet`: 入力→隠れ層 (tanh) →出力 (linear) の最小 net.
  * `BPLearner`: 標準的 BP. 教師信号からの誤差を chain rule で全層に伝播.
  * `EDLALearner`: 出力層と隠れ層で **同じ出力誤差信号** を使い、
    隠れ層には固定 random matrix (Direct Feedback Alignment 的) を
    かけて誤差を「拡散」する.

`EDLA` は厳密な意味で生物学的妥当な学習則の **一族の一例** であり、
正確な金子勇式 1999 EDLA とは異なる可能性がある (1999 原論文の
詳細式は要追加調査). しかし「BP の局所代替」という枠組みは共通。

Pure numpy. PyTorch / Rust 依存なし.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


def mse_loss(y_pred: np.ndarray, y_true: np.ndarray) -> float:
    """Mean squared error."""
    diff = y_pred - y_true
    return float(np.mean(diff * diff))


def _xavier(rng: np.random.Generator, in_dim: int, out_dim: int) -> np.ndarray:
    bound = float(np.sqrt(6.0 / (in_dim + out_dim)))
    return rng.uniform(-bound, bound, size=(in_dim, out_dim)).astype(np.float64)


@dataclass
class TwoLayerNet:
    """Input → hidden (tanh) → output (linear) feedforward net.

    Attributes:
        W1: (in_dim, hidden_dim)
        b1: (hidden_dim,)
        W2: (hidden_dim, out_dim)
        b2: (out_dim,)
    """

    W1: np.ndarray
    b1: np.ndarray
    W2: np.ndarray
    b2: np.ndarray

    @classmethod
    def init(cls, *, in_dim: int, hidden_dim: int, out_dim: int, seed: int = 0) -> TwoLayerNet:
        rng = np.random.default_rng(seed)
        return cls(
            W1=_xavier(rng, in_dim, hidden_dim),
            b1=np.zeros(hidden_dim, dtype=np.float64),
            W2=_xavier(rng, hidden_dim, out_dim),
            b2=np.zeros(out_dim, dtype=np.float64),
        )

    def forward(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Return (h, y) where h is the hidden activation and y is the output."""
        h = np.tanh(x @ self.W1 + self.b1)
        y = h @ self.W2 + self.b2
        return h, y


@dataclass
class BPLearner:
    """Reference: standard backpropagation."""

    lr: float = 0.1

    def step(self, net: TwoLayerNet, x: np.ndarray, y_true: np.ndarray) -> float:
        """Single SGD step. Mutates net in place. Returns post-step loss."""
        h, y_pred = net.forward(x)
        n = x.shape[0]
        # output layer gradients
        dy = 2.0 * (y_pred - y_true) / n  # d MSE / d y_pred
        dW2 = h.T @ dy
        db2 = dy.sum(axis=0)
        # hidden layer gradients via chain rule (the part EDLA avoids)
        dh = dy @ net.W2.T
        dh_pre = dh * (1.0 - h * h)
        dW1 = x.T @ dh_pre
        db1 = dh_pre.sum(axis=0)
        # update
        net.W1 -= self.lr * dW1
        net.b1 -= self.lr * db1
        net.W2 -= self.lr * dW2
        net.b2 -= self.lr * db2
        _, y_new = net.forward(x)
        return mse_loss(y_new, y_true)


@dataclass
class EDLALearner:
    """Skeleton EDLA — error diffused locally without full backpropagation.

    隠れ層への誤差は ``W2.T`` の代わりに固定 random matrix B を使って
    伝播する (Direct Feedback Alignment 的). これにより chain rule の
    大域演算が不要になり、各層は **局所信号のみで** 更新できる.

    Attributes:
        lr: learning rate.
        B: 固定 random feedback matrix (out_dim, hidden_dim). None なら
           step() 初回呼出し時に生成.
        seed: B 生成用の seed.
    """

    lr: float = 0.1
    B: np.ndarray | None = None
    seed: int = 7
    _initialised: bool = field(default=False, init=False)

    def step(self, net: TwoLayerNet, x: np.ndarray, y_true: np.ndarray) -> float:
        h, y_pred = net.forward(x)
        n = x.shape[0]
        out_dim = y_pred.shape[1] if y_pred.ndim == 2 else 1
        hidden_dim = h.shape[1]

        if not self._initialised:
            if self.B is None:
                rng = np.random.default_rng(self.seed)
                self.B = rng.standard_normal((out_dim, hidden_dim)).astype(np.float64) * 0.5
            self._initialised = True
        assert self.B is not None  # for type checkers

        # Output layer: same as BP (誤差はその場で計算可)
        dy = 2.0 * (y_pred - y_true) / n
        dW2 = h.T @ dy
        db2 = dy.sum(axis=0)

        # Hidden layer: **固定 random matrix B で誤差を「拡散」**
        # (DFA 流。完全に局所 — net.W2 を参照しない)
        dh = dy @ self.B
        dh_pre = dh * (1.0 - h * h)
        dW1 = x.T @ dh_pre
        db1 = dh_pre.sum(axis=0)

        net.W1 -= self.lr * dW1
        net.b1 -= self.lr * db1
        net.W2 -= self.lr * dW2
        net.b2 -= self.lr * db2

        _, y_new = net.forward(x)
        return mse_loss(y_new, y_true)


__all__ = ["BPLearner", "EDLALearner", "TwoLayerNet", "mse_loss"]
