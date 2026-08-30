# CODEX PROCESS LIBRARY GUIDE v2 — batch 071–300 and agent bundles

## 1. Purpose

This document governs ingestion, normalization, deduplication, validation and export of process templates 071–300. It extends the previous n8n → Technical Graph → Semantic Process Graph → BPMN pipeline with autonomous-agent bundle export.

## 2. Non-negotiable safety rules

1. Never execute an imported workflow during analysis.
2. Never read, export or copy credentials.
3. Never activate webhooks, schedules or community nodes.
4. Treat Code/Function nodes as untrusted text and scan statically.
5. Do not make external writes during conversion.
6. Preserve source, normalized model and recommendations as separate layers.
7. Do not redistribute verbatim source JSON until its license is verified.

## 3. Merge and deduplication against the first 70

The authoritative existing manifest is required for final merge. Compare in this order:

1. exact semantic `id`;
2. normalized title and business goal;
3. trigger + ordered semantic steps;
4. automation pattern and adapter roles;
5. embedding similarity as a review signal only.

Similarity >= 0.92 creates `duplicate`; 0.82–0.92 creates `possible_variant`; below 0.82 is `new`. Never delete automatically. Variants may share a `pattern_family_id` but keep separate implementation profiles.

## 4. Standard process pipeline

`source reference → static safety scan → technical graph → role classification → chain collapse → SPG → BPMN → implementation profile → quality report`

Every output must include provenance, source-node mapping, confidence, assumptions and detected anomalies. Recommendations may add retry, timeout, fallback, approval, audit and compensation, but may not silently mutate the normalized source graph.

## 5. Autonomous-agent classification

An AI call is not automatically an agent. Set `agent_export.enabled=true` only when the process contains goal-directed planning, tool selection, iterative observation or delegation. Classify topology as one of:

- `single_tool_agent`
- `planner_executor`
- `supervisor_worker`
- `multi_agent_team`
- `event_driven_agent`
- `human_governed_agent`

Model the following explicitly: agent roles, tool allowlists, memory types, task-envelope schema, handoffs, approval points, stop conditions, budget, evaluation and observability.

## 6. Agent bundle export contract

```text
agent-bundle/
├── bundle.manifest.json
├── orchestrator.yaml
├── agents/
│   └── <agent-id>.yaml
├── tools/
│   └── registry.yaml
├── memory/
│   └── policy.yaml
├── policies/
│   ├── permissions.yaml
│   ├── approvals.yaml
│   └── stop-conditions.yaml
├── prompts/
├── evals/
│   ├── golden-cases.jsonl
│   └── rubric.yaml
├── observability/
│   └── events.schema.json
└── README.md
```

The manifest must pin schema versions and contain no secrets. Tools are deny-by-default. External writes, financial actions, access changes, publication, deletion and person-directed messages require explicit policy and usually human approval.

## 7. Required agent controls

- maximum steps, wall-clock timeout and cost/token budget;
- loop and repeated-tool-failure detection;
- scoped tool permissions and argument validation;
- prompt-injection and untrusted-context boundaries;
- working-memory TTL and long-term-memory write policy;
- human approval before high-impact actions;
- deterministic event log with correlation IDs;
- fallback or safe termination;
- offline golden tests before deployment.

## 8. Export targets

SPG is the source of truth. Exporters may produce BPMN, n8n workflow, or an autonomous-agent bundle. Vendor nodes belong only in implementation profiles. A single semantic process may have several implementation profiles without changing its business model.

## 9. Acceptance criteria

- 230 batch entries parse and validate.
- Library numbers are unique and cover 071–300.
- Semantic IDs are unique.
- Final merge generates a collision report against the first 70.
- No credentials or executable source payloads are present.
- Every agent entry has topology, roles, tools, memory, approval points, stop conditions, sandbox policy and eval definition.
- Every generated bundle passes JSON/YAML/schema checks and contains no unresolved secret values.
- Quality recommendations are separate from normalized graphs.
