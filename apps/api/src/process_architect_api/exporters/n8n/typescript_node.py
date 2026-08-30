from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any

from .python_code import validate_python_code_artifact

if TYPE_CHECKING:
    from .base import N8nTarget


def package_slug(step_id: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", step_id.lower()).strip("-")[:48]
    return slug or "custom-step"


def typescript_node_type(step_id: str) -> str:
    return f"n8n-nodes-apa-{package_slug(step_id)}.numericThreshold"


def compile_typescript_node(process_ir: dict[str, Any], step: dict[str, Any], target: N8nTarget) -> dict[str, Any]:
    validate_python_code_artifact(process_ir, step, target)
    spec = step["customLogic"]["operationSpec"]
    return {
        "operationSpecVersion": "numeric_threshold/1.0",
        "inputField": spec["inputField"],
        "outputField": spec["outputField"],
        "operator": spec["operator"],
        "threshold": spec["threshold"],
    }


def typescript_node_files(process_ir: dict[str, Any], target: N8nTarget) -> dict[str, str]:
    files: dict[str, str] = {}
    for step in process_ir.get("steps", []):
        logic = step.get("customLogic") or {}
        if logic.get("strategy") != "typescript_node":
            continue
        manifest = validate_python_code_artifact(process_ir, step, target)
        slug = package_slug(step["id"])
        package_name = f"n8n-nodes-apa-{slug}"
        root = f"typescript-nodes/{step['id']}"
        package = {
            "name": package_name, "version": "1.0.0", "description": f"Private reviewed node for {step['title']}",
            "license": "UNLICENSED", "private": True, "main": "dist/nodes/NumericThreshold/NumericThreshold.node.js",
            "files": ["dist"],
            "scripts": {"build": "tsc -p tsconfig.json", "test": "node --test test/*.test.mjs", "pack:private": "npm run build && npm pack"},
            "engines": {"node": ">=20"},
            "peerDependencies": {"n8n-workflow": ">=2.30.0 <2.33.0"},
            "devDependencies": {"@types/node": "24.13.3", "n8n-workflow": target.minor + ".0", "typescript": "7.0.2"},
            "n8n": {"n8nNodesApiVersion": 1, "strict": True, "nodes": ["dist/nodes/NumericThreshold/NumericThreshold.node.js"]},
        }
        files[f"{root}/package.json"] = json.dumps(package, ensure_ascii=False, indent=2) + "\n"
        files[f"{root}/tsconfig.json"] = json.dumps({
            "compilerOptions": {"strict": True, "target": "ES2022", "module": "Node16", "moduleResolution": "Node16", "outDir": "dist", "rootDir": ".", "esModuleInterop": True, "skipLibCheck": True},
            "include": ["nodes/**/*.ts"],
        }, indent=2) + "\n"
        files[f"{root}/nodes/NumericThreshold/NumericThreshold.node.ts"] = '''import type { IExecuteFunctions } from 'n8n-workflow';
import type { INodeExecutionData, INodeType, INodeTypeDescription } from 'n8n-workflow';
import { NodeOperationError } from 'n8n-workflow';

type Operator = '<' | '<=' | '==' | '!=' | '>=' | '>';

export function compare(value: number, operator: Operator, threshold: number): boolean {
  switch (operator) {
    case '<': return value < threshold;
    case '<=': return value <= threshold;
    case '==': return value === threshold;
    case '!=': return value !== threshold;
    case '>=': return value >= threshold;
    case '>': return value > threshold;
  }
}

export class NumericThreshold implements INodeType {
  description: INodeTypeDescription = {
    displayName: 'APA Numeric Threshold', name: 'numericThreshold', icon: 'fa:code-branch', group: ['transform'],
    version: 1, description: 'Reviewed deterministic numeric threshold', defaults: { name: 'APA Numeric Threshold' },
    inputs: ['main'], outputs: ['main'],
    properties: [
      { displayName: 'Operation Spec Version', name: 'operationSpecVersion', type: 'hidden', default: 'numeric_threshold/1.0' },
      { displayName: 'Input Field', name: 'inputField', type: 'string', default: '', required: true },
      { displayName: 'Output Field', name: 'outputField', type: 'string', default: '', required: true },
      { displayName: 'Operator', name: 'operator', type: 'options', default: '<=', options: ['<','<=','==','!=','>=','>'].map((name) => ({ name, value: name })) },
      { displayName: 'Threshold', name: 'threshold', type: 'number', default: 0 },
    ],
  };

  async execute(this: IExecuteFunctions): Promise<INodeExecutionData[][]> {
    const items = this.getInputData();
    const inputField = this.getNodeParameter('inputField', 0) as string;
    const outputField = this.getNodeParameter('outputField', 0) as string;
    const operator = this.getNodeParameter('operator', 0) as Operator;
    const threshold = this.getNodeParameter('threshold', 0) as number;
    return [items.map((item, index) => {
      const value = item.json[inputField];
      if (typeof value !== 'number' || !Number.isFinite(value)) throw new NodeOperationError(this.getNode(), `${inputField} must be a finite number`, { itemIndex: index });
      return { json: { ...item.json, [outputField]: compare(value, operator, threshold) }, pairedItem: { item: index } };
    })];
  }
}
'''
        spec = logic["operationSpec"]
        files[f"{root}/test/logic.test.mjs"] = f'''import assert from 'node:assert/strict';
import test from 'node:test';

function compare(value, operator, threshold) {{
  return {{ '<': value < threshold, '<=': value <= threshold, '==': value === threshold, '!=': value !== threshold, '>=': value >= threshold, '>': value > threshold }}[operator];
}}

test('confirmed operation fixture', () => {{
  const input = {json.dumps(logic["inputExample"], ensure_ascii=False)};
  const expected = {json.dumps(logic["outputExample"], ensure_ascii=False)};
  const output = input.map((item) => ({{ json: {{ ...item.json, {json.dumps(spec["outputField"])}: compare(item.json[{json.dumps(spec["inputField"])}], {json.dumps(spec["operator"])}, {json.dumps(spec["threshold"])}) }} }}));
  assert.deepEqual(output, expected);
}});
'''
        files[f"{root}/contract.json"] = json.dumps({**manifest, "packageName": package_name, "nodeType": typescript_node_type(step["id"]), "operationSpec": spec}, ensure_ascii=False, indent=2) + "\n"
        files[f"{root}/README.md"] = f'''# Private TypeScript node for {step["title"]}

Fallback reason: **{logic["fallbackReason"]}**. This package exists because both native Python and the external Python service were rejected for the confirmed environment. It supports n8n 2.30, 2.31, and 2.32 only.

## Build and test

1. Use Node.js 20 or newer in an isolated build environment.
2. Run `npm install --ignore-scripts`, `npm run build`, `npm test`, and `npm audit --omit=dev --audit-level=high`.
3. Run `npm run pack:private`, scan the resulting tarball, and keep it in a private artifact registry.

## Install

Install the generated `.tgz` in the n8n custom-node directory according to your self-hosted deployment, restart every n8n main/worker process, and verify that **APA Numeric Threshold** appears. Import the workflow only after the node is installed. Never install an unreviewed tarball on production.

## Upgrade and rollback

Keep the previous tarball. Stop n8n, replace the package with the reviewed new version, restart, run the fixture workflow, then activate. To roll back, stop n8n, reinstall the previous tarball, restart, and restore the preceding Process IR/workflow revision.

## Remove

Deactivate workflows using this node, remove or replace those nodes, uninstall the package from every main/worker installation, restart n8n, and run `n8n audit`. Community/custom nodes execute with the privileges of the n8n process; treat installation as privileged code deployment.
'''
    return files
