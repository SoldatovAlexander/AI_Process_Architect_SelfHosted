import { describe, expect, it } from 'vitest'
import { catalogs } from './i18n/catalogs'
import { DECISION_NODE_SIZE, layoutProcessSteps, PROCESS_NODE_SIZE } from './process-layout'
import { createProcessTemplate } from './process-template'
import { calculateDiagramReadiness } from './readiness-metrics'
import type { Readiness } from './types'

describe('createProcessTemplate', () => {
  it.each(['ru', 'en', 'es'] as const)('creates a connected seed process for %s', (locale) => {
    const process = createProcessTemplate('Contract approval', locale)

    expect(process.schemaVersion).toBe('0.2')
    expect(process.process.name).toBe('Contract approval')
    expect(process.process.maturity).toBe('draft')
    expect(process.steps.map((step) => step.type)).toEqual(['start', 'end'])
    expect(process.edges).toEqual([
      { id: 'edge_start_end', from: 'step_start', to: 'step_end', condition: null, ruleIds: [] },
    ])
    expect(Object.keys((process.readiness as { categories: Record<string, unknown> }).categories).sort()).toEqual([
      'actors', 'automation', 'branches', 'data', 'exceptions', 'structure', 'systems',
    ])
  })
})

describe('locale catalogs', () => {
  it('keeps every supported locale on the same translation contract', () => {
    const expectedKeys = Object.keys(catalogs.ru).sort()

    expect(Object.keys(catalogs.en).sort()).toEqual(expectedKeys)
    expect(Object.keys(catalogs.es).sort()).toEqual(expectedKeys)
  })
})

describe('layoutProcessSteps', () => {
  it('terminates and positions every step when the process contains a return loop', () => {
    const process = createProcessTemplate('Support ticket', 'en')
    process.steps.splice(1, 0, {
      id: 'step_review',
      type: 'human_task',
      title: 'Review ticket',
      description: '',
      actorId: null,
      systemId: null,
      inputs: [],
      outputs: [],
      operation: { kind: 'manual', name: 'review', parameters: {} },
      missingFields: [],
      automationHint: null,
      execution: { performedBy: 'human', autonomy: 'manual', approvalRequired: false, restrictions: [] },
    })
    process.edges = [
      { id: 'edge_start_review', from: 'step_start', to: 'step_review', condition: null, ruleIds: [] },
      { id: 'edge_review_end', from: 'step_review', to: 'step_end', condition: null, ruleIds: [] },
      { id: 'edge_rework', from: 'step_review', to: 'step_start', condition: null, ruleIds: [] },
    ]

    const positioned = layoutProcessSteps(process)

    expect(positioned).toHaveLength(3)
    expect(positioned.map((item) => item.step.id)).toEqual(['step_start', 'step_review', 'step_end'])
    expect(positioned.every((item) => Number.isFinite(item.position.x) && Number.isFinite(item.position.y))).toBe(true)
    const boxes = positioned.map((item) => {
      const size = item.step.type === 'decision' ? DECISION_NODE_SIZE : PROCESS_NODE_SIZE
      return { x1: item.position.x, y1: item.position.y, x2: item.position.x + size.width, y2: item.position.y + size.height }
    })
    for (let index = 0; index < boxes.length; index += 1) {
      for (let other = index + 1; other < boxes.length; other += 1) {
        const first = boxes[index]
        const second = boxes[other]
        expect(first.x1 < second.x2 && first.x2 > second.x1 && first.y1 < second.y2 && first.y2 > second.y1).toBe(false)
      }
    }
  })
})

describe('calculateDiagramReadiness', () => {
  it('does not lower diagram readiness for incomplete integrations or automation hints', () => {
    const readiness = {
      revision_id: 'revision_1',
      readiness_scope: 'automation_draft',
      overall: 81,
      draft_ready: false,
      automation_ready: false,
      blocking_question_count: 0,
      next_blocking_question: null,
      categories: {
        structure: { score: 100, status: 'ok', reason_codes: [] },
        actors: { score: 100, status: 'ok', reason_codes: [] },
        systems: { score: 40, status: 'blocked', reason_codes: ['unknown_integrations'] },
        data: { score: 100, status: 'ok', reason_codes: [] },
        branches: { score: 100, status: 'ok', reason_codes: [] },
        exceptions: { score: 100, status: 'ok', reason_codes: [] },
        automation: { score: 70, status: 'warning', reason_codes: ['automation_hints_missing'] },
      },
    } satisfies Readiness

    expect(calculateDiagramReadiness(readiness)).toBe(100)
  })
})
