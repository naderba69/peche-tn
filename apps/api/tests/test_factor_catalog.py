from collections import Counter

from spotdata.domain.enums import CatalogStatus
from spotdata.domain.factor_catalog import (
    CATALOG_VERSION,
    MATRIX_FACTORS,
    factor_catalog_summary,
    serialized_factor_catalog,
)


def test_matrix_v3_catalog_retains_every_numbered_factor_once() -> None:
    assert len(MATRIX_FACTORS) == 63
    assert len({item.matrix_id for item in MATRIX_FACTORS}) == 63
    assert [item.matrix_id for item in MATRIX_FACTORS[:3]] == ["1.1", "1.2", "1.3"]
    assert [item.matrix_id for item in MATRIX_FACTORS[-3:]] == ["8.4", "8.5", "8.6"]


def test_catalog_summary_resolves_source_count_for_operations_and_keeps_provenance() -> None:
    summary = factor_catalog_summary()
    counts = Counter(item.status for item in MATRIX_FACTORS)
    assert summary.catalog_version == CATALOG_VERSION
    assert summary.source_claimed_total == 62
    assert summary.audited_total == 63
    assert "العدد من 62" in summary.note_ar
    assert "63 عاملاً تشغيلياً" in summary.note_ar
    assert summary.automated_decision == counts[CatalogStatus.AUTOMATED_DECISION]
    assert summary.automated_context == counts[CatalogStatus.AUTOMATED_CONTEXT]
    assert summary.proxy_requires_field_check == counts[CatalogStatus.PROXY_REQUIRES_FIELD_CHECK]
    assert summary.field_or_external_required == counts[CatalogStatus.FIELD_OR_EXTERNAL_REQUIRED]
    assert summary.excluded_unsupported == counts[CatalogStatus.EXCLUDED_UNSUPPORTED]
    assert (
        sum(
            (
                summary.automated_decision,
                summary.automated_context,
                summary.proxy_requires_field_check,
                summary.field_or_external_required,
                summary.excluded_unsupported,
            )
        )
        == 63
    )


def test_serialized_catalog_uses_json_safe_status_and_variables() -> None:
    payload = serialized_factor_catalog()
    assert payload[0]["status"] == "automated_decision"
    assert isinstance(payload[0]["variables"], list)
    assert next(item for item in payload if item["matrix_id"] == "4.2")["status"] == (
        "field_or_external_required"
    )
    assert next(item for item in payload if item["matrix_id"] == "3.6")["status"] == (
        "excluded_unsupported"
    )
