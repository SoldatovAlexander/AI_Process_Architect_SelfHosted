import { useMemo } from 'react'
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react'
import { Bot, Circle, Clock3, Diamond, Flag, UserRound, Webhook } from 'lucide-react'
import type { ProcessIR, ProcessStep } from '../types'
import { layoutProcessSteps } from '../process-layout'

const icons = {
  start: Circle,
  end: Flag,
  human_task: UserRound,
  system_task: Bot,
  decision: Diamond,
  timer: Clock3,
  external_event: Webhook,
}

type ProcessNodeData = { step: ProcessStep; selected: boolean }

const branchHandles = {
  1: ['branch-bottom'],
  2: ['branch-left', 'branch-right'],
  3: ['branch-left', 'branch-bottom', 'branch-right'],
} as const

function ProcessNode({ data }: NodeProps<Node<ProcessNodeData>>) {
  if (data.step.type === 'decision') {
    return (
      <div className={`process-node process-node--decision ${data.selected ? 'is-selected' : ''}`} data-help-topic="gateway">
        <Handle type="target" position={Position.Top} />
        <span className="decision-node__gateway" aria-hidden="true"><b>×</b></span>
        <strong className="decision-node__title">{data.step.title}</strong>
        <Handle id="branch-left" className="decision-handle decision-handle--left" type="source" position={Position.Left} />
        <Handle id="branch-bottom" className="decision-handle decision-handle--bottom" type="source" position={Position.Bottom} />
        <Handle id="branch-right" className="decision-handle decision-handle--right" type="source" position={Position.Right} />
      </div>
    )
  }
  const Icon = icons[data.step.type]
  return (
    <div className={`process-node process-node--${data.step.type} ${data.selected ? 'is-selected' : ''}`} data-help-topic="node">
      <Handle type="target" position={Position.Top} />
      <span className="process-node__icon"><Icon size={17} /></span>
      <span><small>{data.step.type.replace('_', ' ')}</small><strong>{data.step.title}</strong></span>
      {data.step.missingFields.length > 0 && <i>{data.step.missingFields.length}</i>}
      <Handle type="source" position={Position.Bottom} />
      <Handle id="return-target" className="auxiliary-handle auxiliary-handle--left-target" type="target" position={Position.Left} />
      <Handle id="return-source" className="auxiliary-handle auxiliary-handle--left-source" type="source" position={Position.Left} />
      <Handle id="bypass-target" className="auxiliary-handle auxiliary-handle--right-target" type="target" position={Position.Right} />
      <Handle id="bypass-source" className="auxiliary-handle auxiliary-handle--right-source" type="source" position={Position.Right} />
    </div>
  )
}

const nodeTypes = { process: ProcessNode }

function layout(process: ProcessIR, selectedId: string | null): Node<ProcessNodeData>[] {
  return layoutProcessSteps(process).map(({ step, position }) => ({
      id: step.id,
      type: 'process',
      position,
      data: { step, selected: step.id === selectedId },
  }))
}

function formatCondition(condition: NonNullable<ProcessIR['edges'][number]['condition']>) {
  const subject = condition.left.replaceAll('_', ' ').trim()
  let label: string
  if (condition.left === 'route') label = String(condition.right)
  else if (condition.operator === '==' && condition.right === true) label = subject
  else if (condition.operator === '==' && condition.right === false) label = `не ${subject}`
  else label = `${subject} ${condition.operator} ${String(condition.right)}`
  return label.length > 38 ? `${label.slice(0, 37)}…` : label
}

export function ProcessCanvas({ process, selectedId, onSelect }: { process: ProcessIR; selectedId: string | null; onSelect: (id: string) => void }) {
  const nodes = useMemo(() => layout(process, selectedId), [process, selectedId])
  const edges = useMemo<Edge[]>(() => {
    const steps = new Map(process.steps.map((step) => [step.id, step]))
    const positionedNodes = new Map(nodes.map((node) => [node.id, node]))
    const outgoing = new Map<string, typeof process.edges>()
    process.edges.forEach((edge) => outgoing.set(edge.from, [...(outgoing.get(edge.from) ?? []), edge]))
    return process.edges.map((edge) => {
      const siblings = outgoing.get(edge.from) ?? [edge]
      const handles = branchHandles[Math.min(siblings.length, 3) as keyof typeof branchHandles]
      const siblingIndex = siblings.findIndex((item) => item.id === edge.id)
      const sourceNode = positionedNodes.get(edge.from)
      const targetNode = positionedNodes.get(edge.to)
      const verticalDistance = sourceNode && targetNode ? targetNode.position.y - sourceNode.position.y : 0
      const isReturn = verticalDistance <= 0
      const isLongBypass = verticalDistance > 360
      const decisionHandle = steps.get(edge.from)?.type === 'decision' && siblings.length <= 3 ? handles[siblingIndex] : undefined
      const targetSupportsAuxiliaryHandle = steps.get(edge.to)?.type !== 'decision'
      return {
        id: edge.id,
        source: edge.from,
        target: edge.to,
        sourceHandle: decisionHandle ?? (isReturn ? 'return-source' : isLongBypass ? 'bypass-source' : undefined),
        targetHandle: targetSupportsAuxiliaryHandle ? (isReturn ? 'return-target' : isLongBypass ? 'bypass-target' : undefined) : undefined,
        type: 'smoothstep',
        pathOptions: { borderRadius: 8, offset: (isReturn || isLongBypass ? 42 : 24) + siblingIndex * 4 },
        label: edge.condition ? formatCondition(edge.condition) : undefined,
        markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 16 },
        style: { stroke: '#778791', strokeWidth: 1.35 },
        labelStyle: { fontSize: 10, fontWeight: 650, fill: '#43515b' },
        labelBgStyle: { fill: '#ffffff', fillOpacity: 0.96 },
        labelBgPadding: [6, 4] as [number, number],
        labelBgBorderRadius: 4,
      }
    })
  }, [nodes, process])

  return (
    <div className="canvas-surface">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable
        onNodeClick={(_, node) => onSelect(node.id)}
        fitView
        fitViewOptions={{ padding: 0.16, maxZoom: 1 }}
        minZoom={0.25}
        maxZoom={1.6}
        proOptions={{ hideAttribution: true }}
      >
        <Background color="#d9e0e3" gap={22} size={1} />
        <Controls showInteractive={false} position="bottom-left" />
      </ReactFlow>
    </div>
  )
}
