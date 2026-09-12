import json
from collections.abc import Callable
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

import httpx
import pytest
import respx

from spotdata.domain.engine import DecisionEngine
from spotdata.domain.models import ForecastDataset, ForecastDecisionRequest
from spotdata.services.gemini import GeminiClient, GeminiServiceError, build_evidence_packet

TZ = ZoneInfo("Africa/Tunis")
API_KEY = "test-runtime-key-that-is-never-persisted"
MODEL = "gemini-3.8-flash"
BASE_URL = "https://generativelanguage.test/v1beta"


def authoritative_pair(
    dataset_factory: Callable[..., ForecastDataset],
) -> tuple[ForecastDecisionRequest, Any]:
    dataset = dataset_factory(
        count=96,
        start_at=datetime(2026, 9, 4, 0, tzinfo=TZ),
    )
    request = ForecastDecisionRequest(
        location=dataset.location,
        target_date=dataset.target_date,
        spot=dataset.spot,
        angler=dataset.angler,
    )
    return request, DecisionEngine().evaluate(dataset)


def test_writer_packet_is_compact_but_keeps_hourly_categories_and_all_factors(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    request, decision = authoritative_pair(dataset_factory)
    packet = build_evidence_packet(request, decision)
    compact_bytes = len(json.dumps(packet, ensure_ascii=False).encode("utf-8"))
    legacy_bytes = len(
        json.dumps(
            {
                "request": request.model_dump(mode="json"),
                "decision": decision.model_dump(mode="json"),
            },
            ensure_ascii=False,
        ).encode("utf-8")
    )

    assert compact_bytes < 64_000
    assert compact_bytes < legacy_bytes * 0.25
    assert packet["data_minimization"] == {
        "purpose": "categorical prose context only",
        "coordinates_sent_to_writer": False,
        "raw_hourly_numbers_sent_to_writer": False,
        "raw_antecedent_hours_sent_to_writer": False,
        "complete_numbers_remain_server_rendered": True,
    }
    assert "latitude" not in packet["request_context"]  # type: ignore[operator]
    assert "longitude" not in packet["request_context"]  # type: ignore[operator]
    assert "antecedent_hours" not in packet
    assert len(packet["hourly_categorical_context"]) == 24  # type: ignore[arg-type]
    assert len(packet["all_factor_assessments"]) == 63  # type: ignore[arg-type]
    assert all(
        "forecast" not in item and "derived" not in item
        for item in packet["hourly_categorical_context"]  # type: ignore[union-attr]
    )


def narrative_payload(**updates: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "executive_summary_ar": "تفسير موجز ملتزم بحكم المحرك وبحدود البيانات المتاحة.",
        "timing_and_water_ar": ["النافذة المعروضة هي مرجع التوقيت الحتمي."],
        "temporal_analysis_ar": ["النشاط السابق يفسر كاحتمال تراكمي لا كمشاهدة للشاطئ."],
        "factor_interactions_ar": ["تفاعل الريح والموج يقرأ مع اتجاه البحر ومصدره."],
        "field_tactics_ar": ["افحص الكسرة والمخرج وحالة الخيط قبل نصب العتاد."],
        "unknowns_ar": ["الصوفة والعكارة الفعلية Unknown حتى المعاينة الميدانية."],
    }
    payload.update(updates)
    return payload


def gemini_response(payload: dict[str, object]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "candidates": [
                {"content": {"parts": [{"text": json.dumps(payload, ensure_ascii=False)}]}}
            ]
        },
    )


@respx.mock
@pytest.mark.asyncio
async def test_key_verification_uses_runtime_header_only() -> None:
    route = respx.get(f"{BASE_URL}/models/{MODEL}").mock(
        return_value=httpx.Response(200, json={"name": f"models/{MODEL}"})
    )
    async with httpx.AsyncClient() as http_client:
        client = GeminiClient(http_client=http_client, base_url=BASE_URL, model=MODEL)
        result = await client.verify_key(API_KEY)
    assert result.valid is True
    assert route.calls[0].request.headers["x-goog-api-key"] == API_KEY
    assert API_KEY.encode() not in route.calls[0].request.content


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 401, 403])
async def test_rejected_key_is_sanitized_and_never_retried(status_code: int) -> None:
    route = respx.get(f"{BASE_URL}/models/{MODEL}").mock(return_value=httpx.Response(status_code))
    async with httpx.AsyncClient() as http_client:
        client = GeminiClient(http_client=http_client, base_url=BASE_URL, model=MODEL)
        with pytest.raises(GeminiServiceError) as raised:
            await client.verify_key(API_KEY)
    assert route.call_count == 1
    assert raised.value.code == "gemini_key_rejected"
    assert API_KEY not in raised.value.message_ar


@respx.mock
@pytest.mark.asyncio
async def test_structured_report_keeps_numbers_and_decision_server_rendered(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    request, decision = authoritative_pair(dataset_factory)
    route = respx.post(f"{BASE_URL}/models/{MODEL}:generateContent").mock(
        return_value=gemini_response(narrative_payload())
    )
    async with httpx.AsyncClient() as http_client:
        client = GeminiClient(http_client=http_client, base_url=BASE_URL, model=MODEL)
        result = await client.generate_report(API_KEY, request, decision)

    assert result.metadata.decision_was_modified is False
    assert result.metadata.numbers_are_server_rendered is True
    assert len(result.metadata.input_sha256) == 64
    assert decision.decision_label_ar in result.report_text
    assert f"{decision.opportunity_score}/100" in result.report_text
    assert "MATRICE 63 FACTEURS" in result.report_text
    assert len(decision.factor_assessments) == 63
    assert API_KEY not in result.report_text
    sent = route.calls[0].request
    assert API_KEY.encode() not in sent.content
    assert sent.headers["x-goog-api-key"] == API_KEY
    sent_body = json.loads(sent.content)
    prompt_text = sent_body["contents"][0]["parts"][0]["text"]
    assert len(prompt_text.encode("utf-8")) < 50_000
    assert '"latitude"' not in prompt_text
    assert '"longitude"' not in prompt_text
    assert '"antecedent_hours"' not in prompt_text
    config = sent_body["generationConfig"]
    assert config["candidateCount"] == 1
    assert config["thinkingConfig"] == {"thinkingLevel": "low"}
    assert config["maxOutputTokens"] == 8_192
    schema = config["responseJsonSchema"]
    assert schema["propertyOrdering"] == schema["required"]
    for name in schema["required"][1:]:
        assert schema["properties"][name]["minItems"] == 1
        assert schema["properties"][name]["maxItems"] == 4
    packet = build_evidence_packet(request, decision)
    assert packet["authority"]["writer_may_change_decision"] is False  # type: ignore[index]


@respx.mock
@pytest.mark.asyncio
async def test_structured_output_accepts_thoughts_bom_fence_and_double_encoding(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    request, decision = authoritative_pair(dataset_factory)
    raw_json = json.dumps(narrative_payload(), ensure_ascii=False)
    double_encoded = json.dumps(raw_json, ensure_ascii=False)
    route = respx.post(f"{BASE_URL}/models/{MODEL}:generateContent").mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {"thought": True, "text": "internal 99"},
                                {"text": f"\ufeff```json\n{double_encoded}\n```"},
                            ]
                        },
                    }
                ]
            },
        )
    )

    async with httpx.AsyncClient() as http_client:
        client = GeminiClient(http_client=http_client, base_url=BASE_URL, model=MODEL)
        result = await client.generate_report(API_KEY, request, decision)

    assert route.call_count == 1
    assert result.narrative.executive_summary_ar == narrative_payload()["executive_summary_ar"]
    assert "internal 99" not in result.report_text


@respx.mock
@pytest.mark.asyncio
async def test_schema_mismatch_is_regenerated_once_without_exceeding_the_call_budget(
    dataset_factory: Callable[..., ForecastDataset],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, decision = authoritative_pair(dataset_factory)
    responses = iter(
        [
            gemini_response(
                {
                    "executive_summary_ar": "خرج صالح كصيغة لكنه ناقص الحقول المطلوبة.",
                }
            ),
            httpx.Response(503),
            httpx.Response(503),
            gemini_response(narrative_payload()),
        ]
    )
    route = respx.post(f"{BASE_URL}/models/{MODEL}:generateContent").mock(
        side_effect=lambda _request: next(responses)
    )
    sleep = AsyncMock()
    monkeypatch.setattr("spotdata.services.gemini.asyncio.sleep", sleep)
    monkeypatch.setattr("spotdata.services.gemini.random.uniform", lambda _a, _b: 0.0)

    async with httpx.AsyncClient() as http_client:
        client = GeminiClient(http_client=http_client, base_url=BASE_URL, model=MODEL)
        result = await client.generate_report(API_KEY, request, decision)

    assert route.call_count == 4
    assert sleep.await_count == 2
    assert result.metadata.model == MODEL
    retry_body = json.loads(route.calls[1].request.content)
    assert "إعادة توليد من الصفر" in retry_body["contents"][0]["parts"][0]["text"]


@respx.mock
@pytest.mark.asyncio
async def test_max_tokens_truncated_json_is_regenerated_once(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    request, decision = authoritative_pair(dataset_factory)
    responses = iter(
        [
            httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "finishReason": "MAX_TOKENS",
                            "content": {"parts": [{"text": '{"executive_summary_ar":'}]},
                        }
                    ]
                },
            ),
            gemini_response(narrative_payload()),
        ]
    )
    route = respx.post(f"{BASE_URL}/models/{MODEL}:generateContent").mock(
        side_effect=lambda _request: next(responses)
    )

    async with httpx.AsyncClient() as http_client:
        client = GeminiClient(http_client=http_client, base_url=BASE_URL, model=MODEL)
        result = await client.generate_report(API_KEY, request, decision)

    assert route.call_count == 2
    retry_body = json.loads(route.calls[1].request.content)
    assert retry_body["generationConfig"]["temperature"] == 0.0
    assert result.metadata.prompt_version == "peche-tn-writer-v6"


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "finish_reason",
    ["SAFETY", "RECITATION", "LANGUAGE", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"],
)
async def test_blocked_finish_reasons_fail_without_regeneration(
    dataset_factory: Callable[..., ForecastDataset],
    finish_reason: str,
) -> None:
    request, decision = authoritative_pair(dataset_factory)
    route = respx.post(f"{BASE_URL}/models/{MODEL}:generateContent").mock(
        return_value=httpx.Response(
            200,
            json={
                "candidates": [
                    {
                        "finishReason": finish_reason,
                        "content": {"parts": [{"text": "blocked"}]},
                    }
                ]
            },
        )
    )

    async with httpx.AsyncClient() as http_client:
        client = GeminiClient(http_client=http_client, base_url=BASE_URL, model=MODEL)
        with pytest.raises(GeminiServiceError) as raised:
            await client.generate_report(API_KEY, request, decision)

    assert route.call_count == 1
    assert raised.value.code == "gemini_generation_blocked"
    assert raised.value.status_code == 422


@respx.mock
@pytest.mark.asyncio
async def test_persistent_max_tokens_without_final_text_is_classified(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    request, decision = authoritative_pair(dataset_factory)
    responses = iter(
        [
            httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "finishReason": "MAX_TOKENS",
                            "content": {"parts": [{"thought": True, "text": "internal"}]},
                        }
                    ]
                },
            ),
            httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "finishReason": "MAX_TOKENS",
                            "content": {"parts": [{"text": "{"}]},
                        }
                    ]
                },
            ),
        ]
    )
    route = respx.post(f"{BASE_URL}/models/{MODEL}:generateContent").mock(
        side_effect=lambda _request: next(responses)
    )

    async with httpx.AsyncClient() as http_client:
        client = GeminiClient(http_client=http_client, base_url=BASE_URL, model=MODEL)
        with pytest.raises(GeminiServiceError) as raised:
            await client.generate_report(API_KEY, request, decision)

    assert route.call_count == 2
    assert raised.value.code == "gemini_output_truncated"
    assert raised.value.status_code == 502


@respx.mock
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("updates", "expected_code"),
    [
        ({"executive_summary_ar": "سرد يضيف 99 بالمائة بلا سلطة."}, "gemini_added_numbers"),
        ({"executive_summary_ar": "لا تذهب وفق رأي الكاتب المخالف."}, "gemini_repeated_decision"),
        (
            {"executive_summary_ar": "لا تخرج إلى الشاطئ وفق رأي الكاتب."},
            "gemini_repeated_decision",
        ),
    ],
)
async def test_semantic_guard_rejects_numbers_or_decision_commands(
    dataset_factory: Callable[..., ForecastDataset],
    updates: dict[str, object],
    expected_code: str,
) -> None:
    request, decision = authoritative_pair(dataset_factory)
    route = respx.post(f"{BASE_URL}/models/{MODEL}:generateContent").mock(
        return_value=gemini_response(narrative_payload(**updates))
    )
    async with httpx.AsyncClient() as http_client:
        client = GeminiClient(http_client=http_client, base_url=BASE_URL, model=MODEL)
        with pytest.raises(GeminiServiceError) as raised:
            await client.generate_report(API_KEY, request, decision)
    assert route.call_count == 1
    assert raised.value.code == expected_code


@respx.mock
@pytest.mark.asyncio
async def test_generation_deadline_stops_transport_retries_with_explicit_timeout(
    dataset_factory: Callable[..., ForecastDataset],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, decision = authoritative_pair(dataset_factory)
    route = respx.post(f"{BASE_URL}/models/{MODEL}:generateContent").mock(
        side_effect=httpx.ReadTimeout("slow provider")
    )
    times = iter([0.0, 0.0, 40.0])
    monkeypatch.setattr("spotdata.services.gemini.monotonic", lambda: next(times))
    sleep = AsyncMock()
    monkeypatch.setattr("spotdata.services.gemini.asyncio.sleep", sleep)

    async with httpx.AsyncClient() as http_client:
        client = GeminiClient(http_client=http_client, base_url=BASE_URL, model=MODEL)
        with pytest.raises(GeminiServiceError) as raised:
            await client.generate_report(API_KEY, request, decision)

    assert route.call_count == 1
    assert sleep.await_count == 0
    assert raised.value.code == "gemini_timeout"
    assert raised.value.status_code == 504


@respx.mock
@pytest.mark.asyncio
async def test_transient_503_retries_then_returns_valid_report(
    dataset_factory: Callable[..., ForecastDataset],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, decision = authoritative_pair(dataset_factory)
    responses = iter(
        [
            httpx.Response(503),
            httpx.Response(503),
            gemini_response(narrative_payload()),
        ]
    )
    route = respx.post(f"{BASE_URL}/models/{MODEL}:generateContent").mock(
        side_effect=lambda _request: next(responses)
    )
    sleep = AsyncMock()
    monkeypatch.setattr("spotdata.services.gemini.asyncio.sleep", sleep)
    monkeypatch.setattr("spotdata.services.gemini.random.uniform", lambda _a, _b: 0.0)

    async with httpx.AsyncClient() as http_client:
        client = GeminiClient(http_client=http_client, base_url=BASE_URL, model=MODEL)
        result = await client.generate_report(API_KEY, request, decision)

    assert route.call_count == 3
    assert sleep.await_count == 2
    assert result.metadata.model == MODEL
    assert API_KEY not in result.report_text


@respx.mock
@pytest.mark.asyncio
async def test_persistent_503_is_returned_only_after_bounded_retries(
    dataset_factory: Callable[..., ForecastDataset],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request, decision = authoritative_pair(dataset_factory)
    route = respx.post(f"{BASE_URL}/models/{MODEL}:generateContent").mock(
        return_value=httpx.Response(503)
    )
    sleep = AsyncMock()
    monkeypatch.setattr("spotdata.services.gemini.asyncio.sleep", sleep)
    monkeypatch.setattr("spotdata.services.gemini.random.uniform", lambda _a, _b: 0.0)

    async with httpx.AsyncClient() as http_client:
        client = GeminiClient(http_client=http_client, base_url=BASE_URL, model=MODEL)
        with pytest.raises(GeminiServiceError) as raised:
            await client.generate_report(API_KEY, request, decision)

    assert route.call_count == 4
    assert sleep.await_count == 3
    assert raised.value.code == "gemini_provider_error"
    assert raised.value.status_code == 503
    assert "بعد إعادة المحاولة" in raised.value.message_ar
    assert API_KEY not in raised.value.message_ar


@respx.mock
@pytest.mark.asyncio
async def test_invalid_structured_json_falls_back_cleanly(
    dataset_factory: Callable[..., ForecastDataset],
) -> None:
    request, decision = authoritative_pair(dataset_factory)
    route = respx.post(f"{BASE_URL}/models/{MODEL}:generateContent").mock(
        return_value=httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": [{"text": "not-json"}]}}]},
        )
    )
    async with httpx.AsyncClient() as http_client:
        client = GeminiClient(http_client=http_client, base_url=BASE_URL, model=MODEL)
        with pytest.raises(GeminiServiceError) as raised:
            await client.generate_report(API_KEY, request, decision)
    assert route.call_count == 2
    assert raised.value.code == "gemini_schema_validation_failed"
    assert "إعادة محدودة" in raised.value.message_ar
