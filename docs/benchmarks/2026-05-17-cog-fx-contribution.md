# COG-FX 9 因子 寄与率レポート (ablation)

- baseline status: `completed`
- baseline confidence: **0.925**
- baseline perspectives: support=**0.863** risk=**0.250** consensus=`proceed`
- baseline governance_total: **0.868**

## Factor presence check (baseline)

| Factor | Required events | Present? |
|---|---|---|
| structure | `stimulus_built` | ✓ |
| recomposition | `grounding_applied` | ✓ |
| closed_loop | `loop_completed, decision, outcome` | ✓ |
| self_extension | `tool_invoked` | ✓ |
| uncertainty | `outcome` | ✓ |
| exploration | `perspectives_observed` | ✓ |
| alignment | `governance_scored, approval_resolved` | ✓ |
| provenance | `outcome` | ✓ |
| multi_perspective | `perspectives_observed` | ✓ |

## Ablation deltas (baseline − factor OFF)

| Factor OFF | Δconfidence | Δsupport | Δrisk | Δgovernance | consensus changed | events lost |
|---|---|---|---|---|---|---|
| `structure` | 0.0 | -0.05 | 0.0 | -0.05 | no | — |
| `recomposition` | 0.0 | 0.0 | 0.0 | 0.0 | no | `grounding_applied` |
| `self_extension` | -0.5 | -0.15 | 0.0 | -0.1475 | no | `tool_invoked` |
| `exploration` | 0.0 | 0.0 | 0.0 | 0.0 | no | — |
| `alignment` | 0.0 | -0.0375 | 0.0 | None | no | `approval_requested`, `approval_resolved`, `governance_scored` |
| `multi_perspective` | 0.0 | None | None | 0.0 | yes | `perspectives_observed` |

## Notes

closed_loop / uncertainty / provenance are not ablated — they are structural invariants of the Brief pipeline. The other 6 factors are toggled individually and compared against the 9-factor baseline.
