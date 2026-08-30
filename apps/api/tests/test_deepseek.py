import asyncio
import json
from pathlib import Path

import httpx
from pydantic import SecretStr

from process_architect_api.config import Settings
from process_architect_api.deepseek import DeepSeekClient
from process_architect_api.services.llm_credentials import ResolvedLLMConnection


ROOT = Path(__file__).resolve().parents[3]
LEAD_FIXTURE = json.loads(
    (ROOT / "02_architecture" / "examples" / "lead-intake.process-ir.json").read_text(
        encoding="utf-8"
    )
)


def test_deepseek_client_requests_json_process_ir():
    async def run_test():
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            assert request.url == "https://api.deepseek.com/chat/completions"
            assert request.headers["Authorization"] == "Bearer test-key"
            assert payload["model"] == "deepseek-v4-flash"
            assert payload["response_format"] == {"type": "json_object"}
            assert payload["thinking"] == {"type": "disabled"}
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": json.dumps(LEAD_FIXTURE)}}
                    ]
                },
            )

        settings = Settings(deepseek_api_key=SecretStr("test-key"))
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as http_client:
            result = await DeepSeekClient(settings, http_client).create_process_ir(
                "Create a lead in CRM after qualification."
            )
        assert result["process"]["id"] == "process_lead_intake"

    asyncio.run(run_test())


def test_settings_accepts_ai_process_api_alias(monkeypatch):
    monkeypatch.setenv("AI_PROCESS_API", "alias-test-key")

    settings = Settings(_env_file=None)

    assert settings.deepseek_configured is True
    assert settings.deepseek_api_key is not None
    assert settings.deepseek_api_key.get_secret_value() == "alias-test-key"


def test_client_uses_provider_neutral_openai_compatible_connection():
    async def run_test():
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            assert request.url == "http://ollama:11434/v1/chat/completions"
            assert "Authorization" not in request.headers
            assert payload["model"] == "qwen3"
            assert "thinking" not in payload
            return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(LEAD_FIXTURE)}}]})

        connection = ResolvedLLMConnection(
            provider="openai_compatible",
            api_key=None,
            base_url="http://ollama:11434/v1",
            model="qwen3",
            source="user",
        )
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await DeepSeekClient(Settings(_env_file=None), client, connection).create_process_ir("Lead intake")
        assert result["process"]["id"] == "process_lead_intake"

    asyncio.run(run_test())


def test_deepseek_client_parses_analyst_turn():
    async def run_test():
        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            assert payload["messages"][-1] == {"role": "user", "content": "Clarify the name"}
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "message": "I can clarify the name.",
                                        "summary": "Clarify process name",
                                        "patch": [
                                            {
                                                "op": "replace",
                                                "path": "/process/name",
                                                "value": "Qualified Lead Intake",
                                            }
                                        ],
                                    }
                                )
                            }
                        }
                    ]
                },
            )

        settings = Settings(deepseek_api_key=SecretStr("test-key"))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            deepseek = DeepSeekClient(settings, client)
            result = await deepseek.propose_process_patch(
                [{"role": "user", "content": "Clarify the name"}]
            )
        assert result.patch[0]["path"] == "/process/name"
        assert len(deepseek.usage_observations) == 1
        assert deepseek.usage_observations[0]["outcome"] == "success"

    asyncio.run(run_test())


def test_deepseek_client_repairs_malformed_analyst_json_once():
    async def run_test():
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            payload = json.loads(request.content)
            calls.append(payload["messages"])
            if len(calls) == 1:
                content = '{"message":"Recorded" "summary":"Update","patch":[]}'
            else:
                assert "not a valid JSON object" in payload["messages"][-1]["content"]
                content = json.dumps(
                    {"message": "Recorded", "summary": "Update", "patch": []}
                )
            return httpx.Response(200, json={
                "choices": [{"message": {"content": content}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 4},
            })

        settings = Settings(deepseek_api_key=SecretStr("test-key"))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            deepseek = DeepSeekClient(settings, client)
            result = await deepseek.propose_process_patch(
                [{"role": "user", "content": "Automate the manager's work."}]
            )

        assert len(calls) == 2
        assert result.message == "Recorded"
        assert len(deepseek.usage_observations) == 2
        assert sum(item["usage"]["prompt_tokens"] for item in deepseek.usage_observations) == 20

    asyncio.run(run_test())


def test_deepseek_client_retries_empty_analyst_response_once():
    async def run_test():
        calls = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal calls
            calls += 1
            content = "" if calls == 1 else json.dumps(
                {"message": "Recorded", "summary": "", "patch": []}
            )
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": content}}]},
            )

        settings = Settings(deepseek_api_key=SecretStr("test-key"))
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await DeepSeekClient(settings, client).propose_process_patch(
                [{"role": "user", "content": "Continue."}]
            )

        assert calls == 2
        assert result.message == "Recorded"

    asyncio.run(run_test())
