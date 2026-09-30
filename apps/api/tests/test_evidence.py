from collections.abc import Callable
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from spotdata.domain.engine import DecisionEngine
from spotdata.domain.enums import DecisionReasonCode
from spotdata.domain.models import FieldReport, ForecastDataset, TestCast

engine = DecisionEngine()
TZ = ZoneInfo("Africa/Tunis")


def _report(
    *,
    hours_ago: float,
    kind: str = "fouling",
    severity: str = "dense",
    source: str = "user",
    fetched_at: datetime,
) -> FieldReport:
    return FieldReport(
        kind=kind,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        source=source,  # type: ignore[arg-type]
        reported_at=fetched_at - timedelta(hours=hours_ago),
    )


def _dataset_with(
    dataset: ForecastDataset,
    *,
    reports: list[FieldReport] | None = None,
    test_cast: TestCast | None = None,
) -> ForecastDataset:
    return dataset.model_copy(update={"field_reports": reports or [], "test_cast": test_cast})


def test_proxy_only_never_reaches_force_majeure(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    dataset = dataset_factory(
        hour_updates={
            "wave_height_m": 0.9,
            "wave_period_s": 7.0,
            "wave_direction_deg": 0.0,
            "ocean_current_velocity_kmh": 1.1,
            "wind_speed_kmh": 12.0,
        },
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
    )
    result = engine.evaluate(dataset)
    assert result.fouling_evidence is not None
    assert result.fouling_evidence.level <= 2
    assert result.fouling_evidence.is_force_majeure is False
    assert result.decision_reason_code != DecisionReasonCode.FOULING_CONFIRMED


@pytest.mark.parametrize(
    "evidence_kind", ["report", "official_report", "test_cast", "official_warning"]
)
def test_manual_evidence_is_ignored_by_decision_engine(
    dataset_factory: Callable[..., ForecastDataset], evidence_kind: str
) -> None:
    from spotdata.domain.models import OfficialWarning

    base = dataset_factory(count=96, start_at=datetime(2026, 9, 4, 0, tzinfo=TZ))
    if evidence_kind in {"report", "official_report"}:
        source = "official" if evidence_kind == "official_report" else "user"
        manual = _dataset_with(
            base, reports=[_report(hours_ago=1, fetched_at=base.fetched_at, source=source)]
        )
    elif evidence_kind == "test_cast":
        manual = _dataset_with(
            base,
            test_cast=TestCast(cast_at=base.fetched_at - timedelta(minutes=10), hooked=True),
        )
    else:
        manual = base.model_copy(
            update={
                "official_warning": OfficialWarning(
                    source="inm",
                    kind="strong_wind",
                    level="alert",
                    issued_at=base.fetched_at,
                )
            }
        )

    baseline_result = engine.evaluate(base)
    result = engine.evaluate(manual)
    assert result.decision == baseline_result.decision
    assert result.decision_reason_code == baseline_result.decision_reason_code
    assert result.fouling_evidence.level == baseline_result.fouling_evidence.level
    assert (
        result.fouling_evidence.is_force_majeure
        == baseline_result.fouling_evidence.is_force_majeure
    )
    assert [factor.model_dump() for factor in result.trip_ruin_factors] == [
        factor.model_dump() for factor in baseline_result.trip_ruin_factors
    ]
    assert any("GO النهائي يتطلب تحققاً آلياً حديثاً" in item for item in result.limitations_ar)


def test_spring_neap_is_classified_and_flagged_in_gabes(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    # A Gabès-area spot with a pronounced daily range vs. the rest of the series.
    import math

    def per_hour(index: int, values: dict) -> None:
        day = index // 24
        base_level = 1.2 if day == 3 else 0.3
        values["sea_level_height_msl_m"] = round(
            base_level * math.sin(2 * math.pi * index / 12.4), 3
        )

    dataset = dataset_factory(
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
        per_hour=per_hour,
        spot_updates={"seaward_orientation_deg": 90},
    )
    gabes_dataset = dataset.model_copy(
        update={
            "location": dataset.location.model_copy(update={"latitude": 33.9, "longitude": 10.5})
        }
    )
    result = engine.evaluate(gabes_dataset)
    assert result.spring_neap is not None
    assert result.spring_neap.classification == "spring"
    assert result.spring_neap.folk_label_ar == "حيّة"
    assert result.spring_neap.gabes_zone is True
    assert result.spring_neap.confidence <= 12


def test_spring_neap_is_present_without_reports_or_cast(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    result = engine.evaluate(dataset_factory(count=96, start_at=datetime(2026, 9, 4, 0, tzinfo=TZ)))
    assert result.spring_neap is not None
    assert result.spring_neap.classification in {"spring", "neap", "intermediate", "unknown"}
    assert result.fouling_evidence is not None
