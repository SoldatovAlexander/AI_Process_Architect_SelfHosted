import dagre from '@dagrejs/dagre'
import type { ProcessIR, ProcessStep } from './types'

export interface PositionedStep {
  step: ProcessStep
  position: { x: number; y: number }
}

export const PROCESS_NODE_SIZE = { width: 190, height: 54 }
export const DECISION_NODE_SIZE = { width: 160, height: 108 }

export function layoutProcessSteps(process: ProcessIR): PositionedStep[] {
  const graph = new dagre.graphlib.Graph({ multigraph: true })
  graph.setGraph({
    rankdir: 'TB',
    ranker: 'network-simplex',
    acyclicer: 'greedy',
    nodesep: 54,
    edgesep: 24,
    ranksep: 84,
    marginx: 44,
    marginy: 36,
  })
  graph.setDefaultEdgeLabel(() => ({}))

  process.steps.forEach((step) => {
    const size = step.type === 'decision' ? DECISION_NODE_SIZE : PROCESS_NODE_SIZE
    graph.setNode(step.id, { width: size.width, height: size.height })
  })
  process.edges.forEach((edge) => {
    if (graph.hasNode(edge.from) && graph.hasNode(edge.to)) {
      graph.setEdge(edge.from, edge.to, {}, edge.id)
    }
  })

  dagre.layout(graph)

  return process.steps.map((step) => {
    const node = graph.node(step.id)
    const size = step.type === 'decision' ? DECISION_NODE_SIZE : PROCESS_NODE_SIZE
    return {
      step,
      position: {
        x: node.x - size.width / 2,
        y: node.y - size.height / 2,
      },
    }
  })
}
