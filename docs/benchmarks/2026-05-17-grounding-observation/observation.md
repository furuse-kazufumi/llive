# BriefGrounder 観察レポート (実 Brief サンプル 6 件)

MATH-01/05/08 + TRIZ の citation channel が実 Brief で何を surface するかの観察結果。
**目的**: assertion ではなく観察。次イテレーションの優先順位を決める材料。

## サマリー

| brief_id | TRIZ | calc | units | constants | augmented_goal 字数 |
|---|---|---|---|---|---|
| `phys-drone` | 0 | 1 | 5 | 0 | 492 |
| `energy-photon` | 2 | 0 | 1 | 3 | 693 |
| `trade-off` | 3 | 0 | 0 | 0 | 411 |
| `bookkeep` | 0 | 0 | 4 | 0 | 372 |
| `mixed` | 0 | 1 | 3 | 2 | 611 |
| `prose-only` | 0 | 0 | 0 | 0 | 114 |

## `phys-drone`

**Goal**: Design a delivery drone that maintains 5 m/s during a 30 s window at 100 kg payload, given a 9.81 m/s^2 gravitational acceleration and a 1.2 kg/m^3 air density. Confirm (5 * 30) covers the route.

**Inline calculations (MATH-08)**:
- `(5 * 30)` = 150.0 (ops=1)

**Quantities recognised (MATH-01)**:
- `5 m/s` → value=5.0, dims=m·s^-1
- `30 s` → value=30.0, dims=s
- `100 kg` → value=100.0, dims=kg
- `9.81 m/s^2` → value=9.81, dims=m·s^-2
- `1.2 kg/m^3` → value=1.2, dims=m^-3·kg

## `energy-photon`

**Goal**: Compute the photon energy at 500 nm using the planck constant and the speed of light. Cross-check via the elementary charge to express the result in eV.

**TRIZ citations**:
- #24 Mediator / Intermediary (trigger: `via`)
- #35 Parameter Changes (trigger: `speed`)

**Quantities recognised (MATH-01)**:
- `500 nm` → UNKNOWN: unknown unit symbol 'nm'

**Physical constants grounded (MATH-05)**:
- `speed_of_light` → c = 299792458.0 [m·s^-1] (CODATA 2022 (exact SI definition))
- `planck_constant` → h = 6.62607015e-34 [m^2·kg·s^-1] (CODATA 2022 (exact SI definition))
- `elementary_charge` → e = 1.602176634e-19 [s·A] (CODATA 2022 (exact SI definition))

## `trade-off`

**Goal**: Resolve the trade-off between high precision and speed in our evaluation pipeline. We need a parameter that controls quality without breaking determinism.

**TRIZ citations**:
- #1 Segmentation (trigger: `trade-off`)
- #35 Parameter Changes (trigger: `parameter`)
- #3 Local Quality (trigger: `high precision`)

## `bookkeep`

**Goal**: Ship the report in 5 days, then revisit in 2 weeks. Each chapter should be under 30 pages. Send 1 email per milestone.

**Quantities recognised (MATH-01)**:
- `5 days` → UNKNOWN: unknown unit symbol 'days'
- `2 weeks` → UNKNOWN: unknown unit symbol 'weeks'
- `30 pages` → UNKNOWN: unknown unit symbol 'pages'
- `1 email` → UNKNOWN: unknown unit symbol 'email'

## `mixed`

**Goal**: Use the boltzmann constant to estimate kT at 300 K and compare with (1.38e-23 * 300). Confirm the result lies between 4 J and 5 J for a mole of ideal gas. avogadro should appear too.

**Inline calculations (MATH-08)**:
- `23 * 300` = 6900.0 (ops=1)

**Quantities recognised (MATH-01)**:
- `300 K` → value=300.0, dims=K
- `4 J` → value=4.0, dims=m^2·kg·s^-2
- `5 J` → value=5.0, dims=m^2·kg·s^-2

**Physical constants grounded (MATH-05)**:
- `boltzmann_constant` → k_B = 1.380649e-23 [m^2·kg·s^-2·K^-1] (CODATA 2022 (exact SI definition))
- `avogadro` → N_A = 6.02214076e+23 [1] (CODATA 2022 (exact SI definition))

## `prose-only`

**Goal**: Write the executive summary of the architecture rationale. Focus on auditability and reproducibility, not numbers.

## 集約観察

- 単位 citation: 成功 8 件 / 失敗 5 件
- 計算 citation: 成功 2 件 / 失敗 0 件
- 定数 citation 合計: 5 件