from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .base import N8nTarget


GENERATOR_VERSION = "python-code/1.1"
SUPPORTED_GENERATOR_VERSIONS = {"python-code/1.0", GENERATOR_VERSION}
FORBIDDEN_NAMES = {
    "__import__", "breakpoint", "compile", "delattr", "eval", "exec", "getattr", "globals", "input", "locals", "open", "setattr", "vars",
    "os", "pathlib", "requests", "shutil", "socket", "subprocess", "sys", "urllib", "httpx",
}
SAFE_STANDARD_MODULES = {"datetime", "decimal", "math", "re", "statistics"}
SERVICE_DEPENDENCY_MODULES = {
    "core": SAFE_STANDARD_MODULES,
    "dates": SAFE_STANDARD_MODULES | {"dateutil"},
    "validation": SAFE_STANDARD_MODULES | {"jsonschema"},
}
FORBIDDEN_ATTRIBUTES = {
    "connect", "exec", "execute", "open", "popen", "remove", "rename", "replace", "rmdir",
    "run", "socket", "spawn", "system", "unlink", "urlopen", "write_text", "write_bytes",
}
REQUIRED_PROHIBITIONS = {"network", "filesystem", "credentials", "dynamic_code"}
SUPPORTED_COMPARISON_OPERATORS = {"<", "<=", "==", "!=", ">=", ">"}
TYPESCRIPT_FALLBACK_REASONS = {"python_runtime_unavailable", "service_network_forbidden", "native_installation_required"}
SANDBOX_RUNNER = r'''
import json
import resource
import sys

def set_soft_limit(kind, requested):
    _, hard = resource.getrlimit(kind)
    soft = requested if hard == resource.RLIM_INFINITY else min(requested, hard)
    try:
        resource.setrlimit(kind, (soft, hard))
    except ValueError:
        pass

set_soft_limit(resource.RLIMIT_AS, 512 * 1024 * 1024)
set_soft_limit(resource.RLIMIT_CPU, 1)
set_soft_limit(resource.RLIMIT_FSIZE, 1024 * 1024)
payload = json.loads(sys.stdin.read())
safe_builtins = {
    "bool": bool, "dict": dict, "enumerate": enumerate, "float": float,
    "int": int, "isinstance": isinstance, "len": len, "list": list,
    "max": max, "min": min, "range": range, "round": round,
    "set": set, "sorted": sorted, "str": str, "sum": sum, "tuple": tuple,
    "TypeError": TypeError, "ValueError": ValueError, "KeyError": KeyError,
}
namespace = {"__builtins__": safe_builtins}
allowed_imports = set(payload.get("allowedImports", []))
original_import = __import__
def safe_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or name.split(".", 1)[0] not in allowed_imports:
        raise ImportError("module is outside the selected dependency profile")
    return original_import(name, globals, locals, fromlist, level)
safe_builtins["__import__"] = safe_import
exec(compile(payload["source"], "<reviewed-python>", "exec"), namespace, namespace)
try:
    result = namespace["transform"](payload["input"])
    print(json.dumps({"status": "returned", "result": result}, ensure_ascii=False, sort_keys=True))
except (TypeError, ValueError, KeyError) as error:
    print(json.dumps({"status": "raised", "errorType": type(error).__name__, "message": str(error)}, ensure_ascii=False, sort_keys=True))
'''


@dataclass
class PythonCodePolicyError(ValueError):
    code: str
    detail: str

    def __str__(self) -> str:
        return f"{self.code}: {self.detail}"


def source_hash(source: str) -> str:
    return "sha256:" + hashlib.sha256(source.encode("utf-8")).hexdigest()


def operation_spec_hash(spec: dict[str, Any]) -> str:
    canonical = json.dumps(spec, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return source_hash(canonical)


def generate_numeric_threshold_source(field: str, output_field: str, operator: str, threshold: int | float) -> str:
    if not field.strip() or not output_field.strip():
        raise PythonCodePolicyError("python_generation_invalid", "input and output fields are required")
    if operator not in SUPPORTED_COMPARISON_OPERATORS:
        raise PythonCodePolicyError("python_generation_invalid", f"unsupported comparison operator: {operator}")
    field_literal = json.dumps(field.strip(), ensure_ascii=False)
    output_literal = json.dumps(output_field.strip(), ensure_ascii=False)
    threshold_literal = json.dumps(threshold, ensure_ascii=False)
    return f'''def transform(items):
    if not isinstance(items, list):
        raise TypeError("items must be a list")
    result = []
    for item in items:
        data = item.get("json")
        if not isinstance(data, dict) or {field_literal} not in data:
            raise ValueError({field_literal} + " is required")
        value = data[{field_literal}]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise TypeError({field_literal} + " must be a number")
        result.append({{"json": {{**data, {output_literal}: value {operator} {threshold_literal}}}}})
    return result
'''


def _sandbox_call(source: str, input_value: Any, allowed_imports: set[str], timeout_seconds: float = 1.0) -> tuple[dict[str, Any], int]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [sys.executable, "-I", "-c", SANDBOX_RUNNER],
            input=json.dumps({"source": source, "input": input_value, "allowedImports": sorted(allowed_imports)}, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
            env={"PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8"},
        )
    except subprocess.TimeoutExpired as error:
        raise PythonCodePolicyError("python_execution_timeout", "isolated execution exceeded one second") from error
    duration_ms = max(1, round((time.monotonic() - started) * 1000))
    if completed.returncode != 0:
        detail = completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else "isolated process failed"
        raise PythonCodePolicyError("python_execution_failed", detail[:300])
    try:
        return json.loads(completed.stdout), duration_ms
    except json.JSONDecodeError as error:
        raise PythonCodePolicyError("python_execution_failed", "isolated process returned invalid output") from error


def verify_python_fixtures(logic: dict[str, Any]) -> dict[str, Any]:
    source = logic["source"]
    profile = logic.get("dependencyProfile", "core")
    if profile not in SERVICE_DEPENDENCY_MODULES:
        raise PythonCodePolicyError("python_dependency_profile_unknown", profile)
    allowed_imports = SERVICE_DEPENDENCY_MODULES[profile] if logic.get("strategy") == "python_service" else set()
    normal, normal_ms = _sandbox_call(source, logic["inputExample"], allowed_imports)
    repeated, repeated_ms = _sandbox_call(source, logic["inputExample"], allowed_imports)
    if normal.get("status") != "returned" or normal.get("result") != logic["outputExample"]:
        raise PythonCodePolicyError("python_fixture_result_mismatch", "normal example does not produce the expected output")
    if repeated != normal:
        raise PythonCodePolicyError("python_execution_nondeterministic", "the same input produced different results")
    malformed, malformed_ms = _sandbox_call(source, logic["errorExample"], allowed_imports)
    if malformed.get("status") != "raised" or malformed.get("errorType") != logic["expectedError"]:
        raise PythonCodePolicyError("python_fixture_error_mismatch", f"malformed example must raise {logic['expectedError']}")
    return {
        "status": "passed",
        "contentHash": source_hash(source),
        "runner": "isolated-python/1.0",
        "dependencyProfile": profile,
        "checks": ["expected_output", "deterministic_repeat", "expected_error", "timeout"],
        "durationMs": normal_ms + repeated_ms + malformed_ms,
    }


def _policy_violations(source: str, *, allowed_imports: set[str] | None = None) -> list[str]:
    try:
        tree = ast.parse(source, mode="exec")
    except SyntaxError as error:
        raise PythonCodePolicyError("python_syntax_invalid", f"line {error.lineno}: {error.msg}") from error
    violations: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots = {alias.name.split(".", 1)[0] for alias in node.names}
            if allowed_imports is None or not roots <= allowed_imports:
                violations.add("imports are prohibited or outside the selected dependency profile")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".", 1)[0]
            if node.level or allowed_imports is None or root not in allowed_imports:
                violations.add("imports are prohibited or outside the selected dependency profile")
        elif isinstance(node, ast.Name) and node.id in FORBIDDEN_NAMES:
            violations.add(f"name `{node.id}` is prohibited")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("__"):
                violations.add("dunder attribute access is prohibited")
            if node.attr in FORBIDDEN_ATTRIBUTES:
                violations.add(f"attribute `{node.attr}` is prohibited")
    functions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    transform = [node for node in functions if node.name == "transform"]
    if len(functions) != 1 or len(transform) != 1:
        violations.add("source must contain only one function named transform")
    elif (
        len(transform[0].args.args) != 1
        or transform[0].args.posonlyargs
        or transform[0].args.kwonlyargs
        or transform[0].args.vararg
        or transform[0].args.kwarg
        or transform[0].args.defaults
        or transform[0].args.kw_defaults
        or transform[0].decorator_list
        or isinstance(transform[0], ast.AsyncFunctionDef)
    ):
        violations.add("source must define exactly one synchronous transform(items) function")
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.Expr, ast.Import, ast.ImportFrom)):
            violations.add("top-level executable control flow is prohibited")
        if isinstance(node, ast.Expr) and not isinstance(node.value, ast.Constant):
            violations.add("top-level calls and expressions are prohibited")
    return sorted(violations)


def validate_python_code_artifact(
    process_ir: dict[str, Any],
    step: dict[str, Any],
    target: N8nTarget,
    *,
    require_execution: bool = True,
) -> dict[str, Any]:
    logic = step.get("customLogic") or {}
    strategy = logic.get("strategy")
    expected_profile = {
        "python_code": "n8n_native_python", "python_service": "external_python_service",
        "typescript_node": "native_typescript_node",
    }.get(strategy)
    if not expected_profile:
        raise PythonCodePolicyError("python_strategy_required", "unsupported custom logic strategy")
    if logic.get("runtimeProfile") != expected_profile:
        raise PythonCodePolicyError("python_runtime_unsupported", f"{strategy} requires {expected_profile}")
    if strategy == "python_code" and target.python_runtime != "native_task_runner":
        raise PythonCodePolicyError("python_runtime_unsupported", f"n8n {target.minor} requires the native Python task runner profile")
    if logic.get("approvalStatus") != "approved":
        raise PythonCodePolicyError("python_code_not_approved", "a person must approve this exact artifact before export")
    if logic.get("generatorVersion") not in SUPPORTED_GENERATOR_VERSIONS:
        raise PythonCodePolicyError("python_generator_version_mismatch", f"supported versions: {', '.join(sorted(SUPPORTED_GENERATOR_VERSIONS))}")

    source = logic.get("source", "")
    if not isinstance(source, str) or not source.strip() or not isinstance(logic.get("reasonStandardNodesInsufficient"), str) or not logic["reasonStandardNodesInsufficient"].strip():
        raise PythonCodePolicyError("python_artifact_incomplete", "source and standard-node justification are required")
    if not isinstance(logic.get("errorCases"), list) or not logic["errorCases"] or not all(isinstance(item, str) and item.strip() for item in logic["errorCases"]):
        raise PythonCodePolicyError("python_artifact_incomplete", "at least one explicit error case is required")
    if logic.get("expectedError") not in {"TypeError", "ValueError", "KeyError"}:
        raise PythonCodePolicyError("python_artifact_incomplete", "expectedError must be TypeError, ValueError, or KeyError")
    expected_hash = source_hash(source)
    if logic.get("contentHash") != expected_hash:
        raise PythonCodePolicyError("python_content_hash_mismatch", "source changed after review")
    dependency_profile = logic.get("dependencyProfile", "core")
    if strategy == "python_service" and dependency_profile not in SERVICE_DEPENDENCY_MODULES:
        raise PythonCodePolicyError("python_dependency_profile_unknown", dependency_profile)
    allowed_imports = SERVICE_DEPENDENCY_MODULES[dependency_profile] if strategy == "python_service" else None
    violations = _policy_violations(source, allowed_imports=allowed_imports)
    if violations:
        raise PythonCodePolicyError("python_policy_violation", "; ".join(violations))
    spec = logic.get("operationSpec")
    spec_hash = None
    if strategy == "typescript_node":
        if logic.get("fallbackReason") not in TYPESCRIPT_FALLBACK_REASONS:
            raise PythonCodePolicyError("typescript_fallback_reason_required", "select a confirmed reason why both Python runtimes are unsuitable")
        if (
            not isinstance(spec, dict) or spec.get("kind") != "numeric_threshold"
            or spec.get("operator") not in SUPPORTED_COMPARISON_OPERATORS
            or not isinstance(spec.get("inputField"), str) or not spec["inputField"].strip()
            or not isinstance(spec.get("outputField"), str) or not spec["outputField"].strip()
            or not isinstance(spec.get("threshold"), (int, float)) or isinstance(spec.get("threshold"), bool)
        ):
            raise PythonCodePolicyError("typescript_operation_spec_required", "a complete numeric_threshold operation spec is required")
        spec_hash = operation_spec_hash(spec)
    execution = logic.get("executionEvidence")
    if require_execution and logic.get("generatorVersion") == GENERATOR_VERSION and (
        not isinstance(execution, dict)
        or execution.get("status") != "passed"
        or execution.get("contentHash") != expected_hash
        or execution.get("runner") != "isolated-python/1.0"
        or ("dependencyProfile" in logic and execution.get("dependencyProfile") != dependency_profile)
        or (strategy == "typescript_node" and execution.get("operationSpecHash") != spec_hash)
    ):
        raise PythonCodePolicyError("python_execution_required", "isolated execution evidence for this exact source is required")
    if not isinstance(logic.get("inputExample"), list) or not isinstance(logic.get("outputExample"), list) or not isinstance(logic.get("errorExample"), list):
        raise PythonCodePolicyError("python_fixture_shape_invalid", "n8n all-items fixtures must be arrays")
    for name in ("inputExample", "outputExample"):
        if not all(isinstance(item, dict) and isinstance(item.get("json"), dict) for item in logic[name]):
            raise PythonCodePolicyError("python_fixture_shape_invalid", f"{name} items must contain a json object")

    declared_prohibitions = {str(item).strip().lower() for item in logic.get("prohibitions", [])}
    missing_prohibitions = sorted(REQUIRED_PROHIBITIONS - declared_prohibitions)
    if missing_prohibitions:
        raise PythonCodePolicyError("python_prohibitions_incomplete", ", ".join(missing_prohibitions))

    rules = {rule["id"]: rule for rule in process_ir.get("businessRules", [])}
    linked = logic.get("businessRuleIds", [])
    if not linked:
        raise PythonCodePolicyError("python_business_rules_missing", "at least one confirmed rule is required")
    for rule_id in linked:
        rule = rules.get(rule_id)
        if not rule or step["id"] not in rule.get("appliesToStepIds", []):
            raise PythonCodePolicyError("python_business_rule_mismatch", f"{rule_id} is not linked to step {step['id']}")
        if not rule.get("source"):
            raise PythonCodePolicyError("python_business_rule_source_missing", rule_id)
    return {
        "stepId": step["id"],
        "targetN8nMinor": target.minor,
        "runtimeProfile": target.python_runtime,
        "dependencyProfile": dependency_profile if strategy == "python_service" else None,
        "fallbackReason": logic.get("fallbackReason") if strategy == "typescript_node" else None,
        "operationSpecHash": spec_hash,
        "generatorVersion": logic["generatorVersion"],
        "contentHash": expected_hash,
        "businessRuleIds": linked,
        "approvalStatus": "approved",
        "executionEvidence": execution,
        "policy": {"status": "passed", "prohibitions": sorted(REQUIRED_PROHIBITIONS)},
    }


def compile_python_code_node(process_ir: dict[str, Any], step: dict[str, Any], target: N8nTarget) -> dict[str, Any]:
    validate_python_code_artifact(process_ir, step, target)
    return {
        "mode": "runOnceForAllItems",
        "language": "pythonNative",
        "pythonCode": step["customLogic"]["source"].rstrip() + "\n\nreturn transform(_items)\n",
    }


def compile_python_service_node(process_ir: dict[str, Any], step: dict[str, Any], target: N8nTarget) -> dict[str, Any]:
    validate_python_code_artifact(process_ir, step, target)
    return {
        "method": "POST",
        "url": "={{ $env.APA_PYTHON_SERVICE_URL + '/execute' }}",
        "authentication": "genericCredentialType",
        "genericAuthType": "httpHeaderAuth",
        "sendBody": True,
        "contentType": "raw",
        "rawContentType": "application/json",
        "body": "={{ JSON.stringify({ items: $input.all() }) }}",
        "options": {"timeout": 30000, "response": {"response": {"responseFormat": "json"}}},
    }


def python_code_files(process_ir: dict[str, Any], target: N8nTarget) -> dict[str, str]:
    files: dict[str, str] = {}
    for step in process_ir.get("steps", []):
        logic = step.get("customLogic")
        if not logic or logic.get("strategy") != "python_code":
            continue
        manifest = validate_python_code_artifact(process_ir, step, target)
        root = f"custom-code/{step['id']}"
        files[f"{root}/main.py"] = logic["source"]
        files[f"{root}/contract.json"] = json.dumps({
            **manifest,
            "reasonStandardNodesInsufficient": logic["reasonStandardNodesInsufficient"],
            "inputExample": logic["inputExample"],
            "outputExample": logic["outputExample"],
            "errorExample": logic["errorExample"],
            "expectedError": logic["expectedError"],
            "errorCases": logic["errorCases"],
        }, ensure_ascii=False, indent=2) + "\n"
        files[f"{root}/fixtures/normal.json"] = json.dumps(logic["inputExample"], ensure_ascii=False, indent=2) + "\n"
        files[f"{root}/fixtures/empty.json"] = "{}\n"
        files[f"{root}/fixtures/malformed.json"] = json.dumps(logic["errorExample"], ensure_ascii=False, indent=2) + "\n"
        files[f"{root}/tests/test_main.py"] = f'''import json
import unittest
from pathlib import Path

from main import transform


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_ERROR = {logic["expectedError"]}


class GeneratedLogicTest(unittest.TestCase):
    def test_confirmed_example(self):
        input_value = json.loads((ROOT / "fixtures" / "normal.json").read_text())
        expected = json.loads((ROOT / "fixtures" / "expected.json").read_text())
        self.assertEqual(transform(input_value), expected)

    def test_empty_input_is_deterministic(self):
        first = transform([])
        self.assertEqual(first, transform([]))
        self.assertIsInstance(first, list)

    def test_malformed_input_fails_explicitly(self):
        malformed = json.loads((ROOT / "fixtures" / "malformed.json").read_text())
        with self.assertRaises(EXPECTED_ERROR):
            transform(malformed)


if __name__ == "__main__":
    unittest.main()
'''
        files[f"{root}/fixtures/expected.json"] = json.dumps(logic["outputExample"], ensure_ascii=False, indent=2) + "\n"
        files[f"{root}/README.md"] = (
            f"# Reviewed Python for {step['title']}\n\n"
            "The workflow embeds the exact `main.py` content in an n8n Code node. "
            "Its hash and approval are recorded in `contract.json`. Do not edit the workflow code directly: "
            "create and approve a new Process IR revision, then export again. Native Python requires an enabled n8n task runner. "
            "Run `python -m unittest discover -s tests` in this directory before import.\n"
        )
    return files
