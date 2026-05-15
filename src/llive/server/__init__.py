# SPDX-License-Identifier: Apache-2.0
"""HTTP servers exposing llive to external clients.

Phase C-3 of the RAD epic. The OpenAI-compatible HTTP API lets any OpenAI
client (Ollama, LM Studio, custom code) call llive as if it were a
standard chat completion endpoint, with optional RAD knowledge-base
grounding.

See :mod:`llive.server.openai_api` for details.
"""

from llive.server.openai_api import (
    LLIVE_MODEL_ID,
    OpenAIAPIHandler,
    make_server,
)

__all__ = [
    "LLIVE_MODEL_ID",
    "OpenAIAPIHandler",
    "make_server",
]
