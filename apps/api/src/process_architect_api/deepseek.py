import json
from time import perf_counter
from typing import Any

import httpx
from pydantic import BaseModel, Field, ValidationError

from .config import Settings
from .models import CrossInterviewConflictAnalysis, InterviewAnalysisResult
from .monitoring import record_llm_contract_error, record_llm_request
from .paths import PROCESS_IR_SCHEMA_PATH
from .services.llm_credentials import ResolvedLLMConnection


class DeepSeekConfigurationError(RuntimeError):
    pass


class DeepSeekResponseError(RuntimeError):
    pass


class DeepSeekAnalystTurn(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    summary: str = Field(default="", max_length=4_000)
    patch: list[dict[str, Any]] = Field(default_factory=list, max_length=500)


class DeepSeekClient:
    def __init__(
        self,
        settings: Settings,
        http_client: httpx.AsyncClient,
        connection: ResolvedLLMConnection | None = None,
    ):
        self.settings = settings
        self.http_client = http_client
        self.connection = connection or ResolvedLLMConnection(
            provider="deepseek",
            api_key=(settings.deepseek_api_key.get_secret_value() if settings.deepseek_api_key else None),
            base_url=str(settings.deepseek_base_url).rstrip("/"),
            model=settings.deepseek_model,
            source="system",
        )
        self.usage_observations: list[dict[str, Any]] = []

    def _record_llm_request(
        self,
        operation: str,
        *,
        outcome: str,
        duration_seconds: float,
        usage: dict[str, Any] | None = None,
    ) -> None:
        record_llm_request(
            operation,
            outcome=outcome,
            duration_seconds=duration_seconds,
            usage=usage,
        )
        self.usage_observations.append({
            "operation": operation,
            "outcome": outcome,
            "durationSeconds": max(duration_seconds, 0),
            "usage": {
                key: value for key, value in (usage or {}).items()
                if key in {
                    "prompt_tokens", "completion_tokens", "total_tokens",
                    "prompt_cache_hit_tokens", "prompt_cache_miss_tokens",
                } and isinstance(value, int) and value >= 0
            },
        })

    @property
    def provider(self) -> str:
        return self.connection.provider

    @property
    def model(self) -> str:
        return self.connection.model

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.connection.api_key:
            headers["Authorization"] = f"Bearer {self.connection.api_key}"
        return headers

    def _payload(self, *, messages: list[dict[str, str]], max_tokens: int) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.connection.model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
            "max_tokens": max_tokens,
        }
        if self.connection.provider == "deepseek":
            payload["thinking"] = {"type": "disabled"}
        return payload

    async def create_process_ir(self, description: str) -> dict[str, Any]:
        if not self.connection.configured:
            raise DeepSeekConfigurationError("Configure an LLM provider in your account settings.")

        schema = PROCESS_IR_SCHEMA_PATH.read_text(encoding="utf-8")
        started = perf_counter()
        try:
            response = await self.http_client.post(
                f"{self.connection.base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "You are AI Process Analyst. Convert the user's business process "
                                "description into one valid JSON object matching the supplied Process IR "
                                "schema. Never invent integration details, credentials, identifiers, or "
                                "business rules. Represent unknowns in missingFields and openQuestions. "
                                "Return JSON only.\n\nPROCESS IR JSON SCHEMA:\n" + schema
                            ),
                        },
                        {"role": "user", "content": description},
                    ],
                    max_tokens=8192,
                ),
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            self._record_llm_request(
                "process_draft",
                outcome="provider_error",
                duration_seconds=perf_counter() - started,
            )
            raise
        usage = payload.get("usage") if isinstance(payload, dict) else None

        try:
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise DeepSeekResponseError("The LLM provider returned empty message content.")
            process_ir = json.loads(content)
            if not isinstance(process_ir, dict):
                raise DeepSeekResponseError("The LLM JSON output must be an object.")
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as error:
            self._record_llm_request(
                "process_draft",
                outcome="invalid_response",
                duration_seconds=perf_counter() - started,
                usage=usage,
            )
            if isinstance(error, (KeyError, IndexError, TypeError)):
                raise DeepSeekResponseError(
                    "The LLM response does not contain message content."
                ) from error
            raise DeepSeekResponseError("The LLM provider returned malformed JSON.") from error
        except DeepSeekResponseError:
            self._record_llm_request(
                "process_draft",
                outcome="invalid_response",
                duration_seconds=perf_counter() - started,
                usage=usage,
            )
            raise
        self._record_llm_request(
            "process_draft",
            outcome="success",
            duration_seconds=perf_counter() - started,
            usage=usage,
        )
        return process_ir

    async def propose_process_patch(
        self,
        messages: list[dict[str, str]],
    ) -> DeepSeekAnalystTurn:
        if not self.connection.configured:
            raise DeepSeekConfigurationError("Configure an LLM provider in your account settings.")
        content: str | None = None
        try:
            content = await self._request_analyst_content(messages, "analyst_turn")
            return self._parse_analyst_turn(content)
        except DeepSeekResponseError:
            repair_messages = [*messages]
            if content:
                repair_messages.append({"role": "assistant", "content": content})
            repair_messages.append(
                {
                    "role": "user",
                    "content": (
                        "The previous response is not a valid JSON object matching the required "
                        "Analyst output contract. Correct JSON syntax, preserve the intended facts "
                        "and patch operations, and return only one valid JSON object with message, "
                        "summary, and patch."
                    ),
                },
            )
            repaired_content = await self._request_analyst_content(repair_messages, "analyst_turn")
            return self._parse_analyst_turn(repaired_content)

    async def analyze_interview(self, messages: list[dict[str, str]]) -> InterviewAnalysisResult:
        if not self.connection.configured:
            raise DeepSeekConfigurationError("Configure an LLM provider in your account settings.")
        content: str | None = None
        try:
            content = await self._request_analyst_content(messages, "interview_analysis")
            return self._parse_interview_analysis(content)
        except DeepSeekResponseError:
            repair_messages = [*messages]
            if content:
                repair_messages.append({"role": "assistant", "content": content})
            repair_messages.append({"role": "user", "content": "The previous response violates the interview-analysis JSON contract. Correct the JSON and classifications. Every item must cite only supplied segment IDs; contradictions need at least two segment IDs. Return JSON only."})
            return self._parse_interview_analysis(
                await self._request_analyst_content(repair_messages, "interview_analysis")
            )

    async def analyze_cross_interview_conflicts(self, messages: list[dict[str, str]]) -> CrossInterviewConflictAnalysis:
        if not self.connection.configured:
            raise DeepSeekConfigurationError("Configure an LLM provider in your account settings.")
        content: str | None = None
        try:
            content = await self._request_analyst_content(messages, "cross_interview_conflicts")
            return self._parse_cross_interview_conflicts(content)
        except DeepSeekResponseError:
            repair_messages = [*messages]
            if content:
                repair_messages.append({"role": "assistant", "content": content})
            repair_messages.append({"role": "user", "content": "The previous response violates the cross-interview conflict JSON contract. Use only supplied analysis_id and fact_index pairs, cite at least two different analyses per conflict, and return JSON only."})
            return self._parse_cross_interview_conflicts(
                await self._request_analyst_content(
                    repair_messages, "cross_interview_conflicts"
                )
            )

    async def _request_analyst_content(
        self,
        messages: list[dict[str, str]],
        operation: str,
    ) -> str:
        started = perf_counter()
        try:
            response = await self.http_client.post(
                f"{self.connection.base_url}/chat/completions",
                headers=self._headers(),
                json=self._payload(messages=messages, max_tokens=4096),
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            self._record_llm_request(
                operation,
                outcome="provider_error",
                duration_seconds=perf_counter() - started,
            )
            raise
        usage = payload.get("usage") if isinstance(payload, dict) else None
        try:
            content = payload["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise DeepSeekResponseError("The LLM provider returned empty message content.")
        except (KeyError, IndexError, TypeError, DeepSeekResponseError) as error:
            self._record_llm_request(
                operation,
                outcome="invalid_response",
                duration_seconds=perf_counter() - started,
                usage=usage,
            )
            if isinstance(error, DeepSeekResponseError):
                raise
            raise DeepSeekResponseError(
                "The LLM response does not contain message content."
            ) from error
        self._record_llm_request(
            operation,
            outcome="success",
            duration_seconds=perf_counter() - started,
            usage=usage,
        )
        return content

    @staticmethod
    def _parse_analyst_turn(content: str) -> DeepSeekAnalystTurn:
        try:
            parsed = json.loads(content)
            return DeepSeekAnalystTurn.model_validate(parsed)
        except (TypeError, json.JSONDecodeError, ValidationError) as error:
            record_llm_contract_error("analyst_turn")
            raise DeepSeekResponseError("The LLM provider returned an invalid Analyst turn.") from error

    @staticmethod
    def _parse_interview_analysis(content: str) -> InterviewAnalysisResult:
        try:
            return InterviewAnalysisResult.model_validate(json.loads(content))
        except (TypeError, json.JSONDecodeError, ValidationError) as error:
            record_llm_contract_error("interview_analysis")
            raise DeepSeekResponseError("The LLM provider returned an invalid interview analysis.") from error

    @staticmethod
    def _parse_cross_interview_conflicts(content: str) -> CrossInterviewConflictAnalysis:
        try:
            return CrossInterviewConflictAnalysis.model_validate(json.loads(content))
        except (TypeError, json.JSONDecodeError, ValidationError) as error:
            record_llm_contract_error("cross_interview_conflicts")
            raise DeepSeekResponseError("The LLM provider returned invalid cross-interview conflicts.") from error
