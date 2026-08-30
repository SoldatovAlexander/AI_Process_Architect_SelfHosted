import type { Locale, ProcessIR } from './types'

const labels = {
  ru: { process: 'Новый процесс', description: 'Процесс будет уточнён в интервью.', start: 'Начало процесса', end: 'Результат получен' },
  en: { process: 'New process', description: 'The process will be clarified during the interview.', start: 'Process starts', end: 'Result delivered' },
  es: { process: 'Nuevo proceso', description: 'El proceso se aclarará durante la entrevista.', start: 'Inicio del proceso', end: 'Resultado entregado' },
}

export function createProcessTemplate(name: string, locale: Locale): ProcessIR {
  const copy = labels[locale]
  const id = `process_${Date.now().toString(36)}`
  const category = { score: 0, status: 'blocked', notes: [] }
  return {
    schemaVersion: '0.2',
    process: { id, name: name || copy.process, description: copy.description, domain: 'unknown', maturity: 'draft' },
    passport: { goal: '', ownerActorId: null, startsWhen: copy.start, endsWhen: copy.end, inScope: [], outOfScope: [], successMetrics: [] },
    actors: [],
    systems: [],
    dataObjects: [],
    states: [],
    stateTransitions: [],
    businessRules: [],
    steps: [
      {
        id: 'step_start', type: 'start', title: copy.start, description: '', actorId: null, systemId: null,
        inputs: [], outputs: [], operation: { kind: 'trigger', name: 'unknown', parameters: {} }, missingFields: [], automationHint: null,
        execution: { performedBy: 'system', autonomy: 'manual', approvalRequired: false, restrictions: [] },
      },
      {
        id: 'step_end', type: 'end', title: copy.end, description: '', actorId: null, systemId: null,
        inputs: [], outputs: [], operation: { kind: 'end', name: 'complete', parameters: {} }, missingFields: [], automationHint: null,
        execution: { performedBy: 'system', autonomy: 'manual', approvalRequired: false, restrictions: [] },
      },
    ],
    edges: [{ id: 'edge_start_end', from: 'step_start', to: 'step_end', condition: null, ruleIds: [] }],
    exceptions: [],
    openQuestions: [],
    readiness: {
      overall: 0,
      categories: {
        structure: category, actors: category, systems: category, data: category,
        branches: category, exceptions: category, automation: category,
      },
    },
  }
}
