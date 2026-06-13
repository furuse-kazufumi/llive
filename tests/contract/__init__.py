# SPDX-License-Identifier: Apache-2.0
"""External runtime contract tests (llive v0.A ER-PROC-03).

これらの test は **default で skip** (環境変数 ``OPENAI_BASE_URL`` が
セットされ, かつ llama-server が動いているときのみ run). 月次 cadence で
operator が手動 ON にして, llama.cpp 新 SHA の互換性を smoke する.

CI で自動実行はしない (heavy + 外部 runtime 依存).
"""
