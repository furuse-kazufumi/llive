"""LLW-03: per-page-type JSON Schema validators."""

from __future__ import annotations

import pytest

from llive.wiki.schemas import KNOWN_PAGE_TYPES, WikiSchemaError, list_page_types, validate_page_fields


def test_known_page_types_match_listed():
    assert sorted(list_page_types()) == sorted(KNOWN_PAGE_TYPES)


def test_unknown_page_type_rejected():
    with pytest.raises(WikiSchemaError):
        validate_page_fields("not-a-type", {})


def test_domain_concept_minimal_ok():
    validate_page_fields("domain_concept", {})  # no required fields


def test_domain_concept_with_fields_ok():
    validate_page_fields(
        "domain_concept",
        {"domain": "memory", "synonyms": ["mem"], "definition": "x", "see_also": ["y"]},
    )


def test_experiment_record_requires_fields():
    with pytest.raises(WikiSchemaError):
        validate_page_fields("experiment_record", {"outcome": "accepted"})


def test_experiment_record_valid():
    validate_page_fields(
        "experiment_record",
        {"candidate_id": "cand_x", "baseline": "base", "outcome": "accepted"},
    )


def test_experiment_record_bad_outcome():
    with pytest.raises(WikiSchemaError):
        validate_page_fields(
            "experiment_record",
            {"candidate_id": "cand_x", "baseline": "base", "outcome": "weird"},
        )


def test_failure_post_mortem_requires_fields():
    with pytest.raises(WikiSchemaError):
        validate_page_fields("failure_post_mortem", {})


def test_failure_post_mortem_valid():
    validate_page_fields(
        "failure_post_mortem",
        {"incident_at": "2026-05-13T10:00:00Z", "failure_mode": "rollback_storm"},
    )


def test_principle_application_requires_fields():
    with pytest.raises(WikiSchemaError):
        validate_page_fields("principle_application", {"principle_id": 1})


def test_principle_application_principle_id_bounds():
    with pytest.raises(WikiSchemaError):
        validate_page_fields(
            "principle_application", {"principle_id": 41, "application": "x"}
        )


def test_principle_application_valid():
    validate_page_fields(
        "principle_application",
        {"principle_id": 1, "application": "segmentation of sub-blocks"},
    )
