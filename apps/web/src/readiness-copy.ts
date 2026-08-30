import type { Locale } from './types'

const ru: Record<string, string> = {
  process_steps_missing: 'Добавьте основные рабочие шаги процесса.', passport_not_assessed: 'Заполните паспорт процесса.',
  actors_not_assessed: 'Укажите участников процесса.', systems_not_assessed: 'Укажите используемые программы.', data_not_assessed: 'Укажите рабочие данные.',
  states_not_assessed: 'Опишите состояния основного объекта.', rules_not_assessed: 'Опишите правила принятия решений.', branches_not_assessed: 'Опишите варианты развития процесса.',
  exceptions_not_assessed: 'Опишите действия при ошибках.', governance_not_assessed: 'Разделите работу человека, системы и ИИ.', automation_steps_missing: 'Укажите, какие действия нужно автоматизировать.',
  validation_errors: 'В схеме есть структурные ошибки.', process_description_missing: 'Добавьте описание процесса.', process_goal_missing: 'Укажите цель процесса.',
  process_owner_missing: 'Назначьте владельца процесса.', process_start_boundary_missing: 'Укажите, что запускает процесс.', process_end_boundary_missing: 'Укажите, когда процесс считается завершённым.',
  process_scope_missing: 'Укажите, что входит и не входит в процесс.', success_metrics_missing: 'Добавьте показатель успешности.', human_tasks_without_actor: 'Для некоторых ручных шагов не назначен исполнитель.',
  actor_responsibilities_missing: 'Обязанности некоторых участников не определены.', unknown_integrations: 'Способ подключения некоторых программ ещё не известен.', unsupported_integrations: 'Некоторые программы пока нельзя подключить.',
  step_fields_missing: 'Для шагов не хватает обязательной информации.', data_types_unknown: 'Типы некоторых данных ещё не определены.', object_states_missing: 'Не описан жизненный цикл основного объекта.',
  initial_state_missing: 'Не указано начальное состояние.', terminal_state_missing: 'Не указано конечное состояние.', state_transitions_missing: 'Не описаны переходы между состояниями.',
  decision_conditions_missing: 'Не для всех вариантов решения указаны условия.', business_rules_missing: 'Решения не оформлены отдельными правилами.', decision_rules_not_linked: 'Некоторые ветвления не связаны с правилами.',
  rule_sources_missing: 'Для некоторых правил не указан источник.', exception_paths_missing: 'Не для всех автоматических шагов описаны ошибки.', execution_policies_missing: 'Не указано, кто выполняет некоторые шаги.',
  ai_restrictions_missing: 'Для действий ИИ не указаны запреты.', ai_approval_gate_missing: 'Рискованное действие ИИ не требует подтверждения человека.', blocking_questions_open: 'Остались вопросы, без которых нельзя подготовить черновик.',
  automation_parameters_missing: 'Не хватает параметров автоматизации.', automation_hints_missing: 'Не для всех шагов выбран способ автоматизации.',
}

const en: Record<string, string> = {
  process_steps_missing: 'Add the main working steps.', passport_not_assessed: 'Complete the process passport.', actors_not_assessed: 'Identify process participants.', systems_not_assessed: 'Identify the software used.', data_not_assessed: 'Describe the working data.',
  states_not_assessed: 'Describe the main object states.', rules_not_assessed: 'Describe decision rules.', branches_not_assessed: 'Describe process alternatives.', exceptions_not_assessed: 'Describe what happens on failure.', governance_not_assessed: 'Separate human, system, and AI work.', automation_steps_missing: 'Identify the actions to automate.',
  validation_errors: 'The diagram contains structural errors.', process_description_missing: 'Add a process description.', process_goal_missing: 'Define the process goal.', process_owner_missing: 'Assign a process owner.', process_start_boundary_missing: 'Define what starts the process.', process_end_boundary_missing: 'Define when the process is complete.', process_scope_missing: 'Define what is in and out of scope.', success_metrics_missing: 'Add a success metric.',
  human_tasks_without_actor: 'Some manual steps have no owner.', actor_responsibilities_missing: 'Some participant responsibilities are undefined.', unknown_integrations: 'Some software connection methods are unknown.', unsupported_integrations: 'Some software cannot currently be connected.', step_fields_missing: 'Some steps lack required information.', data_types_unknown: 'Some data types are unknown.',
  object_states_missing: 'The main object lifecycle is not described.', initial_state_missing: 'The initial state is missing.', terminal_state_missing: 'The final state is missing.', state_transitions_missing: 'State transitions are missing.', decision_conditions_missing: 'Some decision outcomes have no condition.', business_rules_missing: 'Decisions are not captured as separate rules.', decision_rules_not_linked: 'Some branches are not linked to rules.', rule_sources_missing: 'Some rules have no source.', exception_paths_missing: 'Some automated steps have no failure handling.',
  execution_policies_missing: 'Some steps do not identify who performs them.', ai_restrictions_missing: 'AI actions have no explicit restrictions.', ai_approval_gate_missing: 'A risky AI action has no human approval.', blocking_questions_open: 'Some questions must be answered before the draft is ready.', automation_parameters_missing: 'Automation parameters are missing.', automation_hints_missing: 'Some steps have no automation approach.',
}

const es: Record<string, string> = {
  process_steps_missing: 'Añada los pasos principales del proceso.', passport_not_assessed: 'Complete el pasaporte del proceso.', actors_not_assessed: 'Indique los participantes.', systems_not_assessed: 'Indique los programas utilizados.', data_not_assessed: 'Describa los datos de trabajo.',
  states_not_assessed: 'Describa los estados del objeto principal.', rules_not_assessed: 'Describa las reglas de decisión.', branches_not_assessed: 'Describa las alternativas del proceso.', exceptions_not_assessed: 'Describa qué ocurre ante un error.', governance_not_assessed: 'Separe el trabajo de personas, sistemas e IA.', automation_steps_missing: 'Indique qué acciones deben automatizarse.',
  validation_errors: 'El diagrama contiene errores estructurales.', process_description_missing: 'Añada una descripción.', process_goal_missing: 'Defina el objetivo.', process_owner_missing: 'Asigne un propietario del proceso.', process_start_boundary_missing: 'Indique qué inicia el proceso.', process_end_boundary_missing: 'Indique cuándo termina.', process_scope_missing: 'Defina qué está incluido y excluido.', success_metrics_missing: 'Añada un indicador de éxito.',
  human_tasks_without_actor: 'Algunos pasos manuales no tienen responsable.', actor_responsibilities_missing: 'Faltan responsabilidades de algunos participantes.', unknown_integrations: 'No se conoce cómo conectar algunos programas.', unsupported_integrations: 'Algunos programas no se pueden conectar.', step_fields_missing: 'Falta información obligatoria en algunos pasos.', data_types_unknown: 'No se conoce el tipo de algunos datos.',
  object_states_missing: 'No se ha descrito el ciclo de vida del objeto.', initial_state_missing: 'Falta el estado inicial.', terminal_state_missing: 'Falta el estado final.', state_transitions_missing: 'Faltan transiciones entre estados.', decision_conditions_missing: 'Algunas alternativas no tienen condición.', business_rules_missing: 'Las decisiones no están registradas como reglas.', decision_rules_not_linked: 'Algunas ramas no están vinculadas a reglas.', rule_sources_missing: 'Falta la fuente de algunas reglas.', exception_paths_missing: 'Falta el tratamiento de errores en algunos pasos automáticos.',
  execution_policies_missing: 'No se indica quién ejecuta algunos pasos.', ai_restrictions_missing: 'Las acciones de IA no tienen restricciones explícitas.', ai_approval_gate_missing: 'Una acción de riesgo de IA no requiere aprobación humana.', blocking_questions_open: 'Quedan preguntas necesarias para preparar el borrador.', automation_parameters_missing: 'Faltan parámetros de automatización.', automation_hints_missing: 'Falta el método de automatización de algunos pasos.',
}

const catalogs: Record<Locale, Record<string, string>> = { ru, en, es }

export function readinessReason(code: string, locale: Locale): string {
  return catalogs[locale][code] ?? code.replaceAll('_', ' ')
}
