from __future__ import annotations

import json
from typing import Any


FRAMEWORK_VERSIONS = {
    "langgraph": "1.2.11",
    "crewai": "1.15.15",
    "agno": "2.8.7",
}


def runtime_contract_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://process-architect.local/contracts/python-runtime.schema.json",
        "title": "Governed Python agent execution",
        "type": "object",
        "required": ["request", "result"],
        "properties": {
            "request": {
                "type": "object",
                "required": ["request_id", "agent_id", "task_id", "process_state", "input_refs", "idempotency_key"],
                "properties": {
                    "request_id": {"type": "string", "minLength": 1},
                    "agent_id": {"type": "string", "minLength": 1},
                    "task_id": {"type": "string", "minLength": 1},
                    "process_state": {"type": "string", "minLength": 1},
                    "input_refs": {"type": "array", "items": {"type": "string"}},
                    "payload": {"type": "object"},
                    "idempotency_key": {"type": "string", "minLength": 1},
                    "approval": {
                        "type": ["object", "null"],
                        "properties": {"status": {"const": "approved"}, "approval_id": {"type": "string", "minLength": 1}},
                        "required": ["status", "approval_id"],
                        "additionalProperties": False,
                    },
                },
                "additionalProperties": False,
            },
            "result": {
                "type": "object",
                "required": ["status", "result", "source_ids", "confidence", "risk_flags", "state_change_requested"],
                "properties": {
                    "status": {"enum": ["proposal", "awaiting_approval", "escalated", "failed"]},
                    "result": {"type": "object"},
                    "source_ids": {"type": "array", "items": {"type": "string"}},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "risk_flags": {"type": "array", "items": {"type": "string"}},
                    "state_change_requested": {"const": False},
                    "reason_code": {"type": ["string", "null"]},
                },
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }


def _runtime_core_source() -> str:
    return '''from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from harness.guard import AgentRunGuard, PermissionDenied


class ContractError(ValueError):
    """The execution request or model proposal violates the runtime contract."""


@dataclass(frozen=True)
class ExecutionRequest:
    request_id: str
    agent_id: str
    task_id: str
    process_state: str
    input_refs: tuple[str, ...]
    idempotency_key: str
    payload: dict[str, Any] = field(default_factory=dict)
    approval: dict[str, Any] | None = None

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "ExecutionRequest":
        allowed = {"request_id", "agent_id", "task_id", "process_state", "input_refs", "idempotency_key", "payload", "approval"}
        unknown = set(value) - allowed
        required = ("request_id", "agent_id", "task_id", "process_state", "input_refs", "idempotency_key")
        missing = [name for name in required if name not in value]
        if unknown or missing:
            raise ContractError(f"Invalid request fields; missing={missing}, unknown={sorted(unknown)}")
        if any(not isinstance(value[name], str) or not value[name] for name in ("request_id", "agent_id", "task_id", "process_state", "idempotency_key")):
            raise ContractError("Request identifiers and process_state must be non-empty strings")
        refs = value["input_refs"]
        if not isinstance(refs, list) or not all(isinstance(item, str) for item in refs):
            raise ContractError("input_refs must be a list of strings")
        payload = value.get("payload", {})
        if not isinstance(payload, dict):
            raise ContractError("payload must be an object")
        approval = value.get("approval")
        if approval is not None and (
            not isinstance(approval, dict)
            or set(approval) != {"status", "approval_id"}
            or approval.get("status") != "approved"
            or not approval.get("approval_id")
        ):
            raise ContractError("approval must contain an approved status and approval_id")
        return cls(
            request_id=str(value["request_id"]), agent_id=str(value["agent_id"]),
            task_id=str(value["task_id"]), process_state=str(value["process_state"]),
            input_refs=tuple(refs), idempotency_key=str(value["idempotency_key"]),
            payload=payload, approval=approval,
        )


class GovernedExecutor:
    """Framework-neutral boundary. It returns proposals and never mutates process state."""

    def __init__(self, root: str | Path, model_call: Callable[[dict[str, Any], ExecutionRequest, "GovernedExecutor"], Mapping[str, Any]]):
        self.root = Path(root)
        self.contract = json.loads((self.root / "agent-contract.json").read_text(encoding="utf-8"))
        self.guard = AgentRunGuard.from_file(self.root / "contracts" / "tool-permissions.json")
        self.model_call = model_call
        self.agents = {agent["id"]: agent for agent in self.contract.get("agents", [])}

    def execute(self, raw_request: Mapping[str, Any]) -> dict[str, Any]:
        request = ExecutionRequest.from_mapping(raw_request)
        agent = self.agents.get(request.agent_id)
        if not agent:
            raise ContractError(f"Unknown agent_id: {request.agent_id}")
        if request.task_id not in {task["id"] for task in self.contract.get("tasks", [])}:
            raise ContractError(f"Unknown task_id: {request.task_id}")
        if request.agent_id != f"agent_{request.task_id}":
            raise ContractError("agent_id is not assigned to task_id")
        proposal = dict(self.model_call(agent, request, self))
        return self.validate_proposal(proposal)

    def call_tool(self, request: ExecutionRequest, tool_id: str, operation: str, invoke: Callable[[], Any]) -> Any:
        decision = self.guard.authorize_tool_call({
            "agent_id": request.agent_id, "task_id": request.task_id,
            "tool_id": tool_id, "operation": operation,
            "process_state": request.process_state, "idempotency_key": request.idempotency_key,
            "approval": request.approval,
        })
        if decision.get("state_change_allowed"):
            raise PermissionDenied("Agent must never own process-state transitions")
        value = invoke()
        self.guard.record_success(request.idempotency_key)
        return value

    @staticmethod
    def validate_proposal(value: Mapping[str, Any]) -> dict[str, Any]:
        required = {"status", "result", "source_ids", "confidence", "risk_flags"}
        missing = sorted(required - set(value))
        allowed = required | {"reason_code"}
        unknown = sorted(set(value) - allowed)
        if missing or unknown:
            raise ContractError(f"Invalid proposal fields; missing={missing}, unknown={unknown}")
        if value["status"] not in {"proposal", "awaiting_approval", "escalated", "failed"}:
            raise ContractError("Invalid proposal status")
        if not isinstance(value["result"], dict) or not isinstance(value["source_ids"], list) or not isinstance(value["risk_flags"], list):
            raise ContractError("Proposal result, source_ids and risk_flags have invalid types")
        if not all(isinstance(item, str) for item in [*value["source_ids"], *value["risk_flags"]]):
            raise ContractError("source_ids and risk_flags must contain strings")
        confidence = value["confidence"]
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 1:
            raise ContractError("confidence must be between 0 and 1")
        if value.get("reason_code") is not None and not isinstance(value["reason_code"], str):
            raise ContractError("reason_code must be a string or null")
        return {
            "status": value["status"], "result": value["result"],
            "source_ids": value["source_ids"], "confidence": confidence,
            "risk_flags": value["risk_flags"], "state_change_requested": False,
            "reason_code": value.get("reason_code"),
        }
'''


def _runtime_core_tests() -> str:
    return '''import json
import tempfile
import unittest
from pathlib import Path

from runtime_core import ContractError, GovernedExecutor


class RuntimeContractTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        (root / "contracts").mkdir()
        (root / "agent-contract.json").write_text(json.dumps({"agents": [{"id": "agent_task"}], "tasks": [{"id": "task"}]}))
        (root / "contracts" / "tool-permissions.json").write_text(json.dumps({"default": "deny", "permissions": []}))
        self.executor = GovernedExecutor(root, lambda agent, request, runtime: {
            "status": "proposal", "result": {"ok": True}, "source_ids": list(request.input_refs),
            "confidence": 0.9, "risk_flags": [],
        })

    def tearDown(self):
        self.temp.cleanup()

    def request(self):
        return {"request_id": "req-1", "agent_id": "agent_task", "task_id": "task", "process_state": "task", "input_refs": ["source-1"], "idempotency_key": "key-1", "payload": {}}

    def test_returns_proposal_without_state_authority(self):
        result = self.executor.execute(self.request())
        self.assertEqual(result["status"], "proposal")
        self.assertFalse(result["state_change_requested"])

    def test_rejects_unknown_fields_and_invalid_confidence(self):
        with self.assertRaises(ContractError):
            self.executor.execute({**self.request(), "unexpected": True})
        broken = GovernedExecutor(self.temp.name, lambda *_: {"status": "proposal", "result": {}, "source_ids": [], "confidence": 4, "risk_flags": []})
        with self.assertRaises(ContractError):
            broken.execute(self.request())


if __name__ == "__main__":
    unittest.main()
'''


def runtime_core_files() -> dict[str, str]:
    return {
        "contracts/python-runtime.schema.json": json.dumps(runtime_contract_schema(), ensure_ascii=False, indent=2) + "\n",
        "runtime_core/__init__.py": "from .contract import ContractError, ExecutionRequest, GovernedExecutor\n\n__all__ = [\"ContractError\", \"ExecutionRequest\", \"GovernedExecutor\"]\n",
        "runtime_core/contract.py": _runtime_core_source(),
        "runtime_core/tests/__init__.py": "",
        "runtime_core/tests/test_contract.py": _runtime_core_tests(),
        "runtime_core/README.md": "# Governed Python runtime contract\n\n`GovernedExecutor` validates the request and result around any supported framework. Tool calls pass through the deny-by-default guard. The executor returns proposals only; workflow/backend applies validated state transitions. Run `python -m unittest discover -s runtime_core/tests`.\n",
    }


def _common_project_files(target: str) -> dict[str, str]:
    version = FRAMEWORK_VERSIONS[target]
    return {
        f"{target}/requirements.lock": f"{target}=={version}\n",
        f"{target}/.env.example": "MODEL_PROVIDER=\nMODEL_NAME=\nMODEL_API_KEY=\n",
        f"{target}/run.py": "from adapter import create_app\n\n\nif __name__ == '__main__':\n    raise SystemExit('Import create_app and pass a configured model. See README.md.')\n",
    }


def _langgraph_files() -> dict[str, str]:
    files = _common_project_files("langgraph")
    files.update({
        "langgraph/adapter/__init__.py": "from .app import create_app\n\n__all__ = [\"create_app\"]\n",
        "langgraph/adapter/app.py": '''from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from runtime_core import GovernedExecutor


class RuntimeState(TypedDict):
    request: dict[str, Any]
    result: dict[str, Any]


def _model_not_configured(*_args):
    raise RuntimeError("Configure a model_call before executing the graph")


def create_app(model_call: Callable | None = None, root: str | Path = "."):
    executor = GovernedExecutor(root, model_call or _model_not_configured)

    def execute(state: RuntimeState) -> dict[str, Any]:
        return {"result": executor.execute(state["request"])}

    graph = StateGraph(RuntimeState)
    graph.add_node("execute_under_contract", execute)
    graph.add_edge(START, "execute_under_contract")
    graph.add_edge("execute_under_contract", END)
    return graph.compile()


graph = create_app()
''',
        "langgraph/langgraph.json": json.dumps({"dependencies": ["."], "graphs": {"process_agent": "./adapter/app.py:graph"}, "env": ".env"}, indent=2) + "\n",
        "langgraph/README.md": "# LangGraph adapter\n\nInstall Python 3.11+, run `pip install -r requirements.lock`, configure a model callable, then call `create_app(model_call).invoke({'request': request})`. The callable receives `(agent_contract, execution_request, governed_executor)` and must return the runtime result shape. Tool access must use `governed_executor.call_tool`. The exported `graph` loads in LangGraph tooling but fails closed until a model callable is configured.\n",
    })
    return files


def _crewai_files() -> dict[str, str]:
    files = _common_project_files("crewai")
    files.update({
        "crewai/adapter/__init__.py": "from .app import create_app\n\n__all__ = [\"create_app\"]\n",
        "crewai/adapter/app.py": '''from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from crewai import Agent, Crew, Process, Task
from runtime_core import GovernedExecutor


def create_app(llm: Any, root: str | Path = "."):
    root = Path(root)

    def model_call(agent_contract, request, runtime):
        agent = Agent(role=agent_contract["role"], goal=agent_contract["primaryGoal"], backstory="Operate only under the supplied Agent Contract.", llm=llm, allow_delegation=False, verbose=False)
        task = Task(description="Return JSON only. Do not change process state. Request: " + json.dumps(request.payload), expected_output="JSON with status, result, source_ids, confidence, and risk_flags", agent=agent)
        output = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=False).kickoff()
        raw = getattr(output, "raw", str(output))
        return json.loads(raw)

    return GovernedExecutor(root, model_call)
''',
        "crewai/README.md": "# CrewAI adapter\n\nInstall Python 3.11+ and `pip install -r requirements.lock`. Build a provider-specific CrewAI LLM, pass it to `create_app(llm)`, then call `.execute(request)`. Delegation is disabled; process sequencing and state remain outside CrewAI.\n",
    })
    return files


def _agno_files() -> dict[str, str]:
    files = _common_project_files("agno")
    files.update({
        "agno/adapter/__init__.py": "from .app import create_app\n\n__all__ = [\"create_app\"]\n",
        "agno/adapter/app.py": '''from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agno.agent import Agent
from runtime_core import GovernedExecutor


def create_app(model: Any, root: str | Path = "."):
    def model_call(agent_contract, request, runtime):
        agent = Agent(model=model, name=agent_contract["name"], role=agent_contract["role"], instructions=["Follow the Agent Contract.", "Return JSON only.", "Never change process state directly."])
        response = agent.run(json.dumps(request.payload))
        content = getattr(response, "content", response)
        return json.loads(content) if isinstance(content, str) else content

    return GovernedExecutor(root, model_call)
''',
        "agno/README.md": "# Agno adapter\n\nInstall Python 3.11+ and `pip install -r requirements.lock`. Create an Agno model, pass it to `create_app(model)`, then call `.execute(request)`. Register side-effecting tools only through `GovernedExecutor.call_tool`.\n",
    })
    return files


def framework_files(target: str) -> dict[str, str]:
    builders = {"langgraph": _langgraph_files, "crewai": _crewai_files, "agno": _agno_files}
    return builders[target]()
