---
name: add-grounding-channel
description: |
  llive BriefGrounder に新 citation channel (MATH-08 calc / MATH-01 units /
  MATH-05 constants の系譜) を追加するためのテンプレ skill。dataclass →
  _lookup_X → augmented_goal block → runner ledger payload → テスト →
  observer renderer の 7 ステップを毎回同じ順序で実施する。
  Auto-trigger when: ユーザーが「新しい citation」「grounding channel 追加」
  「新しい MATH-XX 配線」「BriefGrounder に X を足す」等を発話、または
  Brief grounding の新規 channel を実装する必要が surface したとき。
---

# add-grounding-channel — 新 citation channel 追加テンプレ

## 何を解く skill か

BriefGrounder には既に 5 channel (TRIZ / RAD / calc / units / constants)
が乗っている。新規 channel を追加する手順を毎回再導出すると、配線抜けや
規約破り (silently drop、frozen 違反) が起きる。本スキルは
7 ステップのチェックリストで均一な品質を担保する。

## ステップ (順序固定)

### 1. `<Channel>Citation` frozen dataclass を追加

`src/llive/brief/grounding.py` の既存 Citation 群 (`TrizCitation` /
`RadCitation` / `CalcCitation` / `UnitCitation` / `ConstantCitation`)
の隣に追加。`@dataclass(frozen=True)` 必須。

```python
@dataclass(frozen=True)
class FooCitation:
    raw_text: str
    # ... channel 固有 fields
    error: str | None = None   # 拡張余地の保持 (silently drop しない)
```

### 2. `GroundedBrief` に新フィールド追加

```python
foo: tuple[FooCitation, ...] = ()
```

### 3. `GroundingConfig` に上限を追加

```python
max_foo: int = N   # N は prompt 膨張回避の目安
```

### 4. `BriefGrounder._lookup_foo(brief)` を実装

```python
def _lookup_foo(self, brief: Brief) -> tuple[FooCitation, ...]:
    if self.config.max_foo <= 0:
        return ()
    text = self._brief_text(brief)
    # ... extraction logic
    # error citation を残す (silently drop 禁止)
    # 上限到達で break
    return tuple(out)
```

### 5. `ground()` から呼び出し、`_build_augmented_goal` にブロック追加

```python
def ground(self, brief):
    triz = self._lookup_triz(brief)
    ...
    foo = self._lookup_foo(brief)
    augmented = self._build_augmented_goal(brief, triz, rad, calc, units, constants, foo)
    return GroundedBrief(..., foo=foo)
```

`_build_augmented_goal` に `[Foo recognised (MATH-XX)]` ブロック:
- 成功時: `- {raw_text} → key=value, ...`
- error 時: `- {raw_text} → UNKNOWN/ERROR: {error}`

### 6. `BriefRunner` の grounding_applied event payload に追加

`src/llive/brief/runner.py` で `grounded.foo` を dict 化して payload へ。
これで ledger 上で監査可能になる。

### 7. テスト (5-6 件、最低限)

`tests/unit/test_brief_grounding.py` に以下を最低限追加:

- `test_grounder_<channel>_emits_for_<positive_case>` — 正例
- `test_grounder_<channel>_handles_error_safely` — error 時 (silently drop しないか)
- `test_grounder_respects_max_<channel>_cap` — 上限
- `test_grounder_no_<channel>_when_no_match` — 否定例
- `test_<channel>_citation_is_frozen` — frozen 違反検出
- `test_runner_records_<channel>_in_ledger` — ledger 統合

### 8. observe_grounding.py renderer 更新

`scripts/observe_grounding.py::_render_markdown` にブロック追加:
```python
if r["foo"]:
    lines.append("**Foo recognised (MATH-XX)**:")
    for c in r["foo"]:
        ...
```

サマリー table の列にも `foo` を追加。

### 9. 観察スクリプト再実行 → REQUIREMENTS Status 更新 → commit

`[[skill: record-implementation]]` に従って RBC + memory 反映。

## チェックリスト (PR review 風)

- [ ] dataclass は `frozen=True`
- [ ] error は silently drop していない (citation に残している)
- [ ] `max_<channel>` で上限を持つ
- [ ] runner ledger payload に対応 dict
- [ ] テスト 5-6 件 (正例/error/cap/否定/frozen/ledger)
- [ ] observer renderer 更新
- [ ] commit メッセージに「得られた見識」セクション

## 設計原則

- **Quantity / Brief 等の既存 API は触らない** — citation 層で完結する設計を保つ (互換性破壊回避)
- **silently drop しない** — error citation で拡張候補を ledger に残す
- **minimal 主義** — 1 イテレーションで配線完成。精緻化は実 Brief 観察で必要性が surface してから

## 関連

- `[[src/llive/brief/grounding.py]]` — 配線本体
- `[[src/llive/brief/runner.py]]` — ledger payload
- `[[scripts/observe_grounding.py]]` — 観察スクリプト
- `[[skill: observe-cycle]]` — 配線後の検証サイクル
- `[[skill: record-implementation]]` — Status + memory 反映
