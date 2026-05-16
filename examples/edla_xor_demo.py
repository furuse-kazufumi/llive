# SPDX-License-Identifier: Apache-2.0
"""EDLA vs BP — XOR learning curve demo.

`llive.learning` の `BPLearner` と `EDLALearner` で同じ XOR データを学習し、
両者の loss 推移を pure SVG line chart で `docs/scenarios/learning/` に
出力する experiment script.

依存: numpy のみ (matplotlib は使わない、SVG 文字列を手書き).

Usage::

    py -3.11 examples/edla_xor_demo.py [--out=docs/scenarios/learning] [--epochs=8000]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

for stream in (sys.stdout, sys.stderr):
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from llive.learning import BPLearner, EDLALearner, TwoLayerNet, mse_loss  # noqa: E402


def _xor_data() -> tuple[np.ndarray, np.ndarray]:
    x = np.array([[0.0, 0.0], [0.0, 1.0], [1.0, 0.0], [1.0, 1.0]], dtype=np.float64)
    y = np.array([[0.0], [1.0], [1.0], [0.0]], dtype=np.float64)
    return x, y


def train(learner_factory, *, epochs: int, seed: int, lr: float) -> list[float]:
    x, y = _xor_data()
    net = TwoLayerNet.init(in_dim=2, hidden_dim=8, out_dim=1, seed=seed)
    learner = learner_factory(lr)
    losses: list[float] = []
    losses.append(mse_loss(net.forward(x)[1], y))
    for _ in range(epochs):
        losses.append(learner.step(net, x, y))
    return losses


def _svg_chart(
    *,
    bp_losses: list[float],
    edla_losses: list[float],
    width: int = 720,
    height: int = 420,
    margin: int = 50,
    title: str = "XOR Learning Curve — BP vs EDLA",
) -> str:
    plot_w = width - 2 * margin
    plot_h = height - 2 * margin

    all_losses = bp_losses + edla_losses
    y_max = max(all_losses) * 1.05
    y_min = 0.0
    x_max = max(len(bp_losses), len(edla_losses)) - 1

    def coord(epoch: int, loss: float) -> tuple[float, float]:
        x = margin + plot_w * epoch / x_max
        y = margin + plot_h - plot_h * (loss - y_min) / (y_max - y_min)
        return x, y

    def polyline(losses: list[float], color: str, label: str) -> str:
        pts = " ".join(f"{x:.2f},{y:.2f}" for i, l in enumerate(losses) for x, y in [coord(i, l)])
        return f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{pts}"><title>{label}</title></polyline>'

    # axis grid lines
    grid: list[str] = []
    for i in range(6):
        v = y_min + (y_max - y_min) * i / 5
        y = margin + plot_h - plot_h * (v - y_min) / (y_max - y_min)
        grid.append(f'<line x1="{margin}" y1="{y:.2f}" x2="{margin + plot_w}" y2="{y:.2f}" stroke="#e5e7eb" stroke-width="1"/>')
        grid.append(f'<text x="{margin - 8:.2f}" y="{y + 4:.2f}" text-anchor="end" font-family="Inter, sans-serif" font-size="11" fill="#6b7280">{v:.3f}</text>')

    # x axis ticks
    x_ticks: list[str] = []
    for i in range(6):
        ep = int(x_max * i / 5)
        x = margin + plot_w * ep / x_max
        x_ticks.append(f'<line x1="{x:.2f}" y1="{margin + plot_h}" x2="{x:.2f}" y2="{margin + plot_h + 4}" stroke="#6b7280" stroke-width="1"/>')
        x_ticks.append(f'<text x="{x:.2f}" y="{margin + plot_h + 18:.2f}" text-anchor="middle" font-family="Inter, sans-serif" font-size="11" fill="#6b7280">{ep}</text>')

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" preserveAspectRatio="xMidYMid meet" font-family="Inter, sans-serif">'
        f'<rect width="100%" height="100%" fill="#ffffff"/>'
        f'<text x="{width // 2}" y="24" text-anchor="middle" font-size="16" font-weight="bold" fill="#111827">{title}</text>'
        + "".join(grid)
        + "".join(x_ticks)
        + f'<line x1="{margin}" y1="{margin + plot_h}" x2="{margin + plot_w}" y2="{margin + plot_h}" stroke="#374151" stroke-width="1.5"/>'
        + f'<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{margin + plot_h}" stroke="#374151" stroke-width="1.5"/>'
        + f'<text x="{margin + plot_w // 2}" y="{height - 12}" text-anchor="middle" font-size="12" fill="#374151">epoch</text>'
        + f'<text x="14" y="{margin + plot_h // 2}" text-anchor="middle" font-size="12" fill="#374151" transform="rotate(-90 14,{margin + plot_h // 2})">MSE loss</text>'
        + polyline(bp_losses, "#3b82f6", f"BP (final={bp_losses[-1]:.4f})")
        + polyline(edla_losses, "#f59e0b", f"EDLA (final={edla_losses[-1]:.4f})")
        # Legend
        + f'<rect x="{width - margin - 200}" y="{margin + 8}" width="190" height="56" fill="#f9fafb" stroke="#e5e7eb" rx="6"/>'
        + f'<line x1="{width - margin - 188}" y1="{margin + 26}" x2="{width - margin - 168}" y2="{margin + 26}" stroke="#3b82f6" stroke-width="3"/>'
        + f'<text x="{width - margin - 160}" y="{margin + 30}" font-size="12" fill="#111827">BP (final={bp_losses[-1]:.4f})</text>'
        + f'<line x1="{width - margin - 188}" y1="{margin + 48}" x2="{width - margin - 168}" y2="{margin + 48}" stroke="#f59e0b" stroke-width="3"/>'
        + f'<text x="{width - margin - 160}" y="{margin + 52}" font-size="12" fill="#111827">EDLA (final={edla_losses[-1]:.4f})</text>'
        + '</svg>'
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="docs/scenarios/learning", help="output directory")
    parser.add_argument("--epochs", type=int, default=8000, help="training epochs")
    parser.add_argument("--seed", type=int, default=0, help="net init seed")
    parser.add_argument("--bp-lr", type=float, default=0.05, help="BP learning rate")
    parser.add_argument("--edla-lr", type=float, default=0.1, help="EDLA learning rate")
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"training BP    (lr={args.bp_lr}, epochs={args.epochs})...")
    bp_losses = train(lambda lr: BPLearner(lr=lr), epochs=args.epochs, seed=args.seed, lr=args.bp_lr)
    print(f"  BP final loss   = {bp_losses[-1]:.6f}")

    print(f"training EDLA  (lr={args.edla_lr}, epochs={args.epochs})...")
    edla_losses = train(lambda lr: EDLALearner(lr=lr, seed=42), epochs=args.epochs, seed=args.seed, lr=args.edla_lr)
    print(f"  EDLA final loss = {edla_losses[-1]:.6f}")

    # subsample to keep SVG light (~500 points each)
    step = max(1, len(bp_losses) // 500)
    bp_thin = bp_losses[::step]
    edla_thin = edla_losses[::step]

    svg = _svg_chart(bp_losses=bp_thin, edla_losses=edla_thin)
    out_path = out_dir / "edla_xor_loss.svg"
    out_path.write_text(svg, encoding="utf-8")
    print(f"\n✓ wrote {out_path} ({out_path.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
