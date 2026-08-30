import type { Readiness } from './types'

const DIAGRAM_WEIGHTS: Record<string, number> = {
  structure: 20,
  actors: 10,
  data: 15,
  branches: 15,
  exceptions: 10,
}

export function calculateDiagramReadiness(readiness: Readiness): number {
  const entries = Object.entries(DIAGRAM_WEIGHTS).filter(([key]) => readiness.categories[key])
  const totalWeight = entries.reduce((total, [, weight]) => total + weight, 0)
  if (!totalWeight) return 0
  return Math.round(entries.reduce((total, [key, weight]) => total + readiness.categories[key].score * weight, 0) / totalWeight)
}
