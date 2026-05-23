# SPDX-License-Identifier: Apache-2.0
"""GraphRAG memory layer — knowledge-graph augmented long-term retrieval.

See ``design.md`` in this directory for the goal, scope, and the
trade-off table comparing networkx / kùzu / neo4j as future backends.
"""

from llive.memory.graph_rag.edge import Edge
from llive.memory.graph_rag.factor_bridge import (
    factor_strength,
    factor_strength_mutation_bias,
    factor_strength_prior,
)
from llive.memory.graph_rag.node import Node
from llive.memory.graph_rag.store import GraphRAGStore

__all__ = [
    "Edge",
    "GraphRAGStore",
    "Node",
    "factor_strength",
    "factor_strength_mutation_bias",
    "factor_strength_prior",
]
