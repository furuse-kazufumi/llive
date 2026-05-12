# `specs/` — 宣言的仕様のホーム

llive のすべての宣言的仕様 (YAML) を集約するディレクトリ。コード実装より仕様が先行する設計（spec-driven）。

## 構成

```
specs/
├── README.md              # このファイル
├── schemas/               # JSON Schema 本体 (yaml_schemas.md の正本)
│   ├── container-spec.v1.json
│   ├── subblock-spec.v1.json
│   └── candidate-diff.v1.json
├── subblocks/             # 標準 SubBlockSpec
│   ├── common.yaml        # pre_norm / residual
│   ├── attention.yaml     # multi_head / grouped_query / cross_memory
│   ├── ffn.yaml           # ffn_swiglu / ffn_gelu_linear / moe_ffn
│   └── llive_extensions.yaml  # memory_read / memory_write / reflective_probe / compress / verifier_head / adapter / lora_switch
├── containers/            # 自前で書いた ContainerSpec
│   └── (TBA)
├── templates/             # 公開 LLM のひな形 ContainerSpec
│   ├── qwen2_5_7b.yaml
│   ├── llama3_1_8b.yaml
│   ├── mistral_7b_v0_3.yaml
│   └── phi_3_5_mini.yaml
├── candidates/            # CandidateDiff 群
│   └── (TBA)
└── tasks/                 # TaskSpec 群
    └── (TBA)
```

## 命名規則

- ContainerSpec: `<purpose>_v<n>.yaml`（例: `adaptive_reasoning_v1.yaml`）
- 公開 LLM テンプレート: `<family>_<size>.yaml`（例: `qwen2_5_7b.yaml`）
- CandidateDiff: `cand_<YYYYMMDD>_<seq>.yaml`
- TaskSpec: `task_<domain>_<name>.yaml`

## バリデーション

```bash
llive schema validate specs/containers/
llive schema validate specs/templates/qwen2_5_7b.yaml
llive schema migrate v0 v1 specs/templates/
```

## 公開 LLM 検証

```bash
python scripts/inspect_hf_model.py            # all
python scripts/inspect_hf_model.py qwen2_5_7b # one
```

## 参考ドキュメント

- [yaml_schemas.md](../docs/yaml_schemas.md) — 全 schema の正本
- [model_templates.md](../docs/model_templates.md) — 公開 LLM テンプレートの解説
- [data_model.md](../docs/data_model.md) — 関連エンティティ
