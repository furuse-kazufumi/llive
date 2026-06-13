# low_spec bench mock 実走 (2026-05-21)

15h marathon の前倒し作業として, `low_spec.py` harness を **MockBackend** で
実走し, **bench 経路の生死** と **JSON 出力 shape** を確認した. 実 llama-server
や RWKV.cpp を立ち上げなくても bench 経路が全件通ることを確認するのが目的.

## 実行

```bash
py -3.11 scripts/demo_low_spec_mock.py --backends mock --sizes xs s \
    --json out/low_spec_mock_2026_05_21.json
```

## 結果

| backend | size | latency_s | tok/s | rss_MB | meets_latency | finish_reason |
|---|---|---|---|---|---|---|
| mock | xs | 0.0000 | 5,389,354.7 | n/a (psutil missing) | True | stop |
| mock | s  | 0.0000 | 10,604,857.5 | n/a | True | stop |

**観察**:

- bench 経路は **完全に通る**. xs (≈ 500 tok) / s (≈ 2k tok) で latency ほぼ 0
  (echo backend なので当然).
- `psutil` 未 install のため rss_MB は ``n/a``. これは harness の設計通り
  (optional extra) で, 実 backend 評価時に `pip install psutil` で穴埋め.
- tok/s の異常に高い値 (5M tok/s) は MockBackend の echo が一瞬で終わる
  ため. **honest disclosure**: これは実 backend の数値ではないので **公開
  ベンチには絶対に使わない**.

## ⚠ Honest Disclosure (必読)

本実走は **MockBackend (echo) ベース** のため:

1. **latency ≈ 0** は echo の per-call overhead 程度しか測っていない
2. **tok/s 数 M** は実 LLM の **5-6 桁先**の値. 比較対象として使用禁止
3. **runtime_metadata** (`llama_cpp_sha` 等 6 つ) は **'unknown'** 固定.
   `is_valid_for_publication()` は **False** を返す → 公開ブロック

これは設計通りで, **harness が壊れていない** ことだけ確認した. 実数値は
llama-server / RWKV.cpp 起動後に再実走.

## JSON 出力 shape (1 件抜粋)

```json
{
  "backend": "mock",
  "size": "xs",
  "prompt_chars": 2000,
  "latency_s": 7.5e-05,
  "output_chars": 256,
  "tokens_per_second": 5389354.7,
  "peak_rss_mb": null,
  "target_latency_s": 5.0,
  "target_rss_mb": 4000,
  "meets_latency_target": true,
  "meets_rss_target": null,
  "finish_reason": "stop",
  "notes": []
}
```

実 backend 実走時には:
- `target_latency_s` = 5.0 (xs) / 15.0 (s) と比較した `meets_latency_target` が
  意味を持つ
- `peak_rss_mb` が `target_rss_mb` (xs=4000, s=6000) と比較される
- `runtime_metadata` を `notes` に append する形で拡張する候補 (v0.A 接続)

## 次のステップ

| # | アクション | 所要 | 依存 |
|---|---|---|---|
| 1 | `pip install psutil` (RSS 測定) | 1 min | なし |
| 2 | llama.cpp + Codestral-Mamba GGUF (q4_k_m) を `llama-server --port 8080` で起動 | 30 min | model 確保 |
| 3 | `OPENAI_BASE_URL=http://localhost:8080/v1` + `LLIVE_LLM_BACKEND=mamba` で再実走 | 5 min | step 2 |
| 4 | RWKV.cpp + RWKV-7 World 7B (q4_k_m) で同 harness を再実走 | 30 min | model 確保 |
| 5 | Phase 4: bench 出力 JSON に `runtime_metadata` (v0.A 6 metadata) を埋め込む | 1h | step 2 |
| 6 | 進化型 v0.B `backend_select` demo を実 backend で 5 体並走 | 1h | step 2-4 |

## 関連

- `docs/non-transformer/ROADMAP.md` §0.2 (低スペック PC 性能目標)
- `docs/requirements_v0.A_external_runtime_tracking.md`
- `docs/spec/llamacpp_compat_matrix.md`
- `docs/requirements_v0.B_evolutionary_optimization.md`
- `docs/experiments/evolutionary_v0_B_2026_05_21.md`
- maintainer memory: [[feedback-benchmark-honest-disclosure]],
  [[feedback-llive-measurement-purity]], [[feedback-d-drive-preference]]
