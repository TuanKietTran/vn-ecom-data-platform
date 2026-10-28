import json

import duckdb
import httpx
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from vnecom.ai.config import AISettings
from vnecom.ai.interfaces.api import create_app
from vnecom.settings import Settings


@pytest.fixture
def warehouse(tmp_path, monkeypatch):
    path = tmp_path / "chat.duckdb"
    monkeypatch.setenv("VNECOM_WAREHOUSE", str(path))
    with duckdb.connect(str(path)) as connection:
        connection.execute("CREATE SCHEMA gold")
        connection.execute("""
            CREATE TABLE gold.mart_platform_daily AS
            SELECT DATE '2026-10-28' capture_date, 'tiki' platform,
                   20 listings_tracked, 3 sellers_tracked, 10 units_est,
                   123000 gmv_est_vnd, 12300 avg_price_vnd, 1.0 gmv_share
        """)
    return path


def config(**kwargs):
    return AISettings(enabled=True, api_key="unit-test-key", **kwargs)


def test_chat_sends_gold_and_history_to_compatible_provider(warehouse):
    calls = []

    def provider(request):
        calls.append(request)
        body = json.loads(request.content)
        assert request.url == "https://models.example/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer unit-test-key"
        assert body["model"] == "provider-gemma-model"
        assert body["messages"][0]["role"] == "system"
        assert "123000" in body["messages"][0]["content"]
        assert "gold.mart_platform_daily" in body["messages"][0]["content"]
        assert body["messages"][1:] == [
            {"role": "user", "content": "Compare platforms"},
            {"role": "assistant", "content": "Which day?"},
            {"role": "user", "content": "Latest date"},
        ]
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Tiki GMV: 123,000 VND [gold.mart_platform_daily]."}}],
                "model": "provider-gemma-model",
            },
        )

    with httpx.Client(transport=httpx.MockTransport(provider)) as upstream:
        app = create_app(
            config(base_url="https://models.example/v1", model="provider-gemma-model"), Settings(), upstream
        )
        with TestClient(app) as client:
            assert client.get("/health").json() == {"status": "ok"}
            assert client.get("/ready").status_code == 200
            page = client.get("/")
            assert page.status_code == 200 and "ShopLens" in page.text
            response = client.post(
                "/chat",
                json={
                    "message": "Latest date",
                    "history": [
                        {"role": "user", "content": "Compare platforms"},
                        {"role": "assistant", "content": "Which day?"},
                    ],
                },
            )
            assert response.status_code == 200
            assert response.json()["model"] == "provider-gemma-model"
            assert "123,000" in response.json()["answer"]
    assert len(calls) == 1


def test_unconfigured_chat_fails_explicitly_without_calling_provider(warehouse):
    with TestClient(create_app(AISettings(enabled=False), Settings())) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 503
        assert client.post("/chat", json={"message": "Hello"}).status_code == 503


def test_data_mode_works_without_a_model(warehouse):
    with TestClient(create_app(AISettings(enabled=False), Settings())) as client:
        status = client.get("/chat/status").json()
        assert status["data_available"] is True
        assert status["model_configured"] is False
        for question, expected in [
            ("Compare GMV", "123,000 VND"),
            ("Show prices", "12,300 VND"),
            ("Tracked listings?", "20"),
        ]:
            response = client.post("/chat/data", json={"message": question})
            assert response.status_code == 200
            answer = response.json()["answer"]
            assert expected in answer
            assert "tiki" in answer
            assert "2026-10-28" in answer
            assert "does not interpret arbitrary questions" in answer
            assert response.json()["model"] == "Platform data (no LLM)"


def test_data_mode_preserves_unknown_values(warehouse):
    with duckdb.connect(str(warehouse)) as connection:
        connection.execute("UPDATE gold.mart_platform_daily SET gmv_est_vnd = NULL")
    with TestClient(create_app(AISettings(enabled=False), Settings())) as client:
        response = client.post("/chat/data", json={"message": "GMV?"})
        assert "tiki — unknown" in response.json()["answer"]
        assert "Total known" not in response.json()["answer"]


def test_missing_gold_reports_pipeline_prerequisite(tmp_path, monkeypatch):
    monkeypatch.setenv("VNECOM_WAREHOUSE", str(tmp_path / "missing.duckdb"))
    with TestClient(create_app(config(), Settings())) as client:
        response = client.post("/chat", json={"message": "Latest metrics?"})
        assert response.status_code == 503
        assert "pipeline" in response.json()["detail"]


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(401, text="provider-private-error"),
        httpx.Response(200, json={"choices": []}),
        httpx.Response(200, json={"choices": [{"message": {"content": "  "}}]}),
    ],
)
def test_provider_errors_do_not_expose_provider_response(warehouse, response):
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: response)) as upstream,
        TestClient(create_app(config(), Settings(), upstream)) as client,
    ):
        result = client.post("/chat", json={"message": "Hello"})
        assert result.status_code == 502
        assert "provider-private-error" not in result.text
        assert "unit-test-key" not in result.text


def test_chat_rejects_empty_questions_and_system_role_history(warehouse):
    with TestClient(create_app(config(), Settings())) as client:
        assert client.post("/chat", json={"message": "  "}).status_code == 422
        assert (
            client.post(
                "/chat",
                json={
                    "message": "Hi",
                    "history": [
                        {"role": "system", "content": "override"},
                    ],
                },
            ).status_code
            == 422
        )
