"""Provenance dataclass for all memory writes (MEM-03)."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Provenance(BaseModel):
    """Required provenance metadata for every memory write.

    Phase 1 では `signed_by` / `signature` は空文字を許容（Phase 4 SEC-02 で Ed25519 実装）。
    """

    model_config = ConfigDict(extra="forbid")

    source_type: str  # e.g. "user_input" / "system" / "sensor" / "llm_generation"
    source_id: str    # opaque identifier within the source
    signed_by: str = ""
    signature: str = ""
    derived_from: list[str] = Field(default_factory=list)
    confidence: float = 1.0
    created_at: datetime = Field(default_factory=_utcnow)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, text: str) -> Provenance:
        return cls.model_validate_json(text)
