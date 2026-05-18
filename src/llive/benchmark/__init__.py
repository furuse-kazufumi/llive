# SPDX-License-Identifier: Apache-2.0
"""llive benchmark harness — non-transformer + low-spec PC primary.

Subpackages:

* :mod:`llive.benchmark.low_spec` — progressive matrix (xs/s/m/l/xl) targeted
  at the user's primary deployment env: low-spec personal PC (CPU only or
  small GPU, 8-16 GB RAM). All non-transformer backend candidates must
  surface a result here before they are considered for promotion.

See docs/non-transformer/ROADMAP.md §0.2 for performance targets and
feedback_benchmark_progressive_tokens / feedback_llive_measurement_purity
for the measurement discipline.
"""
