from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .paths import WORKSPACE_ROOT
from .process_ir import upgrade_process_ir
from .rubric import CURRENT_RUBRIC_VERSION, entry_id, localized_entry_names

from .localization import normalize_locale


Localized = dict[str, Any]


def _l(ru: Any, en: Any, es: Any) -> Localized:
    return {"ru": ru, "en": en, "es": es}


@dataclass(frozen=True)
class TemplateSpec:
    id: str
    category: str
    domain: str
    name: Localized
    description: Localized
    actor: Localized
    system: Localized
    system_type: str
    flow: Localized
    keywords: tuple[str, ...]


@dataclass(frozen=True)
class CatalogTemplateSpec:
    id: str
    category: str
    domain: str
    name: Localized
    description: Localized
    preview_steps: Localized
    keywords: tuple[str, ...]
    priority: str
    ai_required: bool
    human_in_loop: bool
    automation_pattern: str
    source_template_id: int | None
    source_url: str
    library_number: int | None = None
    agent_export: dict[str, Any] | None = None
    adapter_roles: tuple[str, ...] = ()
    quality_controls: tuple[str, ...] = ()


TemplateDefinition = TemplateSpec | CatalogTemplateSpec


CORE_CATEGORIES = {"sales", "service", "marketing", "sales_crm", "support_cx", "marketing_content", "ecommerce_inventory"}
MANAGEMENT_CATEGORIES = {"analytics_compliance", "autonomous_agents"}


def template_rubric_entry_ids(spec: TemplateDefinition) -> list[str]:
    is_catalog = isinstance(spec, CatalogTemplateSpec)
    domain = spec.category
    business_role = "management" if domain in MANAGEMENT_CATEGORIES else "core" if domain in CORE_CATEGORIES else "supporting"
    customer_impact = "customer_facing" if domain in CORE_CATEGORIES else "internal"
    organizational_span = "cross_functional" if domain in {"cross_functional", "autonomous_agents"} else "local"
    if is_catalog and spec.agent_export and spec.agent_export.get("enabled"):
        automation_mode = "ai_agent"
    elif is_catalog and spec.ai_required:
        automation_mode = "ai_function"
    else:
        automation_mode = "workflow"
    priority = spec.priority.casefold() if is_catalog else "medium"
    risk = "critical" if priority in {"critical", "p0"} else "high" if priority in {"high", "p1"} else "medium" if priority in {"medium", "p2"} else "low"
    human_control = "approval" if is_catalog and spec.human_in_loop else "review"
    return [
        entry_id("process_level", "process"),
        entry_id("business_role", business_role),
        entry_id("customer_impact", customer_impact),
        entry_id("organizational_span", organizational_span),
        entry_id("automation_mode", automation_mode),
        entry_id("domain", domain),
        entry_id("risk", risk),
        entry_id("data_sensitivity", "internal"),
        entry_id("human_control", human_control),
    ]


def apply_template_classification(process_ir: dict[str, Any], spec: TemplateDefinition) -> dict[str, Any]:
    process_ir["classification"] = {
        "rubricVersion": CURRENT_RUBRIC_VERSION,
        "status": "proposed",
        "entryIds": template_rubric_entry_ids(spec),
        "classifiedAt": None,
        "classifiedByUserId": None,
    }
    return process_ir


TEMPLATE_SPECS = (
    TemplateSpec(
        "lead-qualification", "sales", "sales_crm",
        _l("Квалификация входящего лида", "Inbound lead qualification", "Calificacion de leads entrantes"),
        _l("Собирает обращение, проверяет критерии и передает подходящий лид в продажи.", "Captures an inquiry, checks qualification criteria, and routes a suitable lead to sales.", "Captura una consulta, comprueba los criterios y envia el lead adecuado a ventas."),
        _l("Менеджер по продажам", "Sales manager", "Responsable de ventas"),
        _l("CRM", "CRM", "CRM"), "crm",
        _l(("Получено обращение", "Создать лид в CRM", "Проверить потребность и контакты", "Лид подходит?", "Назначить менеджера", "Добавить в прогрев"), ("Inquiry received", "Create CRM lead", "Check need and contact details", "Is the lead qualified?", "Assign sales owner", "Add to nurture"), ("Consulta recibida", "Crear lead en CRM", "Comprobar necesidad y contacto", "El lead esta cualificado?", "Asignar responsable", "Anadir a nutricion")),
        ("лид", "lead", "заявка с сайта", "квалификац", "crm", "bant", "prospect", "cliente potencial"),
    ),
    TemplateSpec(
        "sales-pipeline", "sales", "sales_crm",
        _l("Ведение сделки", "Sales opportunity pipeline", "Pipeline de oportunidades"),
        _l("Проводит сделку от первого контакта через предложение и согласование до выигрыша или отказа.", "Moves an opportunity from first contact through proposal and negotiation to won or lost.", "Lleva una oportunidad desde el primer contacto hasta el cierre ganado o perdido."),
        _l("Менеджер по продажам", "Sales manager", "Responsable de ventas"),
        _l("CRM", "CRM", "CRM"), "crm",
        _l(("Лид квалифицирован", "Открыть сделку", "Подготовить предложение", "Клиент согласен?", "Закрыть сделку успешно", "Зафиксировать отказ"), ("Lead qualified", "Open opportunity", "Prepare proposal", "Has the customer agreed?", "Close as won", "Record lost deal"), ("Lead cualificado", "Abrir oportunidad", "Preparar propuesta", "El cliente acepta?", "Cerrar como ganada", "Registrar perdida")),
        ("сделк", "воронк", "коммерческ", "sales pipeline", "opportunity", "proposal", "deal", "oportunidad"),
    ),
    TemplateSpec(
        "customer-onboarding", "sales", "customer_success",
        _l("Онбординг нового клиента", "New customer onboarding", "Incorporacion de nuevos clientes"),
        _l("Передает клиента после продажи, собирает данные, настраивает услугу и подтверждает запуск.", "Hands off a new customer, gathers data, configures the service, and confirms launch.", "Transfiere al nuevo cliente, recopila datos, configura el servicio y confirma el inicio."),
        _l("Менеджер по работе с клиентами", "Customer success manager", "Responsable de clientes"),
        _l("CRM и база знаний", "CRM and knowledge base", "CRM y base de conocimiento"), "customer_success",
        _l(("Сделка выиграна", "Создать план запуска", "Собрать данные клиента", "Все готово к запуску?", "Запустить обслуживание", "Запросить недостающие данные"), ("Deal won", "Create launch plan", "Collect customer data", "Ready to launch?", "Start service", "Request missing data"), ("Venta ganada", "Crear plan de inicio", "Recopilar datos del cliente", "Listo para iniciar?", "Iniciar servicio", "Solicitar datos faltantes")),
        ("онбординг клиент", "новый клиент", "внедрение клиент", "customer onboarding", "client onboarding", "alta de cliente"),
    ),
    TemplateSpec(
        "quote-approval", "sales", "sales_operations",
        _l("Согласование коммерческого предложения", "Quote and proposal approval", "Aprobacion de propuesta comercial"),
        _l("Готовит расчет, проверяет скидку и условия, согласует исключения и отправляет предложение клиенту.", "Prepares pricing, checks discounts and terms, approves exceptions, and sends the quote.", "Prepara precios, comprueba descuentos, aprueba excepciones y envia la propuesta."),
        _l("Руководитель продаж", "Sales lead", "Director de ventas"),
        _l("CRM", "CRM", "CRM"), "crm",
        _l(("Запрошено предложение", "Рассчитать стоимость", "Проверить скидку и условия", "Условия допустимы?", "Отправить предложение", "Передать на согласование"), ("Quote requested", "Calculate price", "Review discount and terms", "Are terms within policy?", "Send proposal", "Escalate for approval"), ("Propuesta solicitada", "Calcular precio", "Revisar descuento y condiciones", "Condiciones permitidas?", "Enviar propuesta", "Escalar aprobacion")),
        ("коммерческ предлож", "расчет стоимости", "скидк", "quote approval", "pricing", "proposal approval", "cotizacion"),
    ),
    TemplateSpec(
        "contract-approval", "operations", "legal_operations",
        _l("Согласование договора", "Contract review and approval", "Revision y aprobacion de contratos"),
        _l("Проверяет договор по маршруту ответственных, обрабатывает замечания и направляет на подписание.", "Routes a contract for review, resolves comments, and sends the approved version for signature.", "Enruta un contrato para revision, resuelve comentarios y envia la version aprobada a firma."),
        _l("Ответственный за договор", "Contract owner", "Responsable del contrato"),
        _l("Система электронного документооборота", "Document management system", "Sistema documental"), "document_management",
        _l(("Получен проект договора", "Зарегистрировать договор", "Провести проверку условий", "Договор согласован?", "Отправить на подписание", "Вернуть с замечаниями"), ("Contract draft received", "Register contract", "Review contract terms", "Is the contract approved?", "Send for signature", "Return with comments"), ("Borrador recibido", "Registrar contrato", "Revisar condiciones", "Contrato aprobado?", "Enviar a firma", "Devolver con comentarios")),
        ("договор", "контракт", "согласовани", "подписан", "contract review", "contract approval", "contrato"),
    ),
    TemplateSpec(
        "invoice-approval", "finance", "finance",
        _l("Согласование счета поставщика", "Supplier invoice approval", "Aprobacion de factura de proveedor"),
        _l("Сверяет счет с заказом и поставкой, получает согласование и передает документ к оплате.", "Matches an invoice to the order and receipt, obtains approval, and releases it for payment.", "Compara la factura con el pedido y la recepcion, obtiene aprobacion y la libera para pago."),
        _l("Бухгалтер", "Accountant", "Contable"),
        _l("Учетная система", "Accounting system", "Sistema contable"), "accounting",
        _l(("Получен счет", "Зарегистрировать счет", "Сверить сумму и поставку", "Счет корректен?", "Передать к оплате", "Вернуть на исправление"), ("Invoice received", "Register invoice", "Match amount and receipt", "Is the invoice correct?", "Release for payment", "Return for correction"), ("Factura recibida", "Registrar factura", "Comparar importe y recepcion", "Factura correcta?", "Liberar para pago", "Devolver para corregir")),
        ("счет поставщик", "счёт поставщик", "оплат", "invoice approval", "accounts payable", "supplier invoice", "factura proveedor"),
    ),
    TemplateSpec(
        "accounts-receivable", "finance", "finance",
        _l("Контроль дебиторской задолженности", "Accounts receivable collection", "Cobro de cuentas por cobrar"),
        _l("Отслеживает срок оплаты, отправляет напоминания и эскалирует просроченную задолженность.", "Tracks due dates, sends reminders, and escalates overdue receivables.", "Controla vencimientos, envia recordatorios y escala deudas atrasadas."),
        _l("Бухгалтер", "Accountant", "Contable"),
        _l("Учетная система", "Accounting system", "Sistema contable"), "accounting",
        _l(("Наступил срок проверки", "Получить открытые счета", "Связаться с клиентом", "Оплата получена?", "Закрыть задолженность", "Эскалировать просрочку"), ("Review date reached", "Load open invoices", "Contact customer", "Has payment arrived?", "Close receivable", "Escalate overdue debt"), ("Fecha de revision", "Cargar facturas abiertas", "Contactar al cliente", "Pago recibido?", "Cerrar cuenta", "Escalar deuda vencida")),
        ("дебитор", "задолжен", "просроч", "accounts receivable", "collections", "overdue invoice", "cuentas por cobrar"),
    ),
    TemplateSpec(
        "expense-reimbursement", "finance", "finance",
        _l("Возмещение расходов сотруднику", "Employee expense reimbursement", "Reembolso de gastos"),
        _l("Проверяет авансовый отчет и подтверждения, согласует расходы и создает выплату.", "Reviews an expense report and receipts, approves the claim, and creates reimbursement.", "Revisa gastos y comprobantes, aprueba la solicitud y crea el reembolso."),
        _l("Бухгалтер", "Accountant", "Contable"),
        _l("Сервис управления расходами", "Expense management system", "Sistema de gastos"), "expense_management",
        _l(("Подан отчет о расходах", "Зарегистрировать отчет", "Проверить чеки и лимиты", "Расходы подтверждены?", "Создать выплату", "Вернуть сотруднику"), ("Expense report submitted", "Register expense report", "Check receipts and limits", "Are expenses approved?", "Create reimbursement", "Return to employee"), ("Informe presentado", "Registrar informe", "Comprobar recibos y limites", "Gastos aprobados?", "Crear reembolso", "Devolver al empleado")),
        ("авансовый отчет", "возмещение расход", "чек", "expense reimbursement", "expense report", "receipt", "reembolso"),
    ),
    TemplateSpec(
        "purchase-request", "procurement", "procurement",
        _l("Заявка на закупку", "Purchase request approval", "Aprobacion de solicitud de compra"),
        _l("Собирает потребность, проверяет бюджет, согласует закупку и формирует заказ поставщику.", "Captures demand, checks budget, approves the purchase, and creates a supplier order.", "Recoge la necesidad, comprueba presupuesto, aprueba la compra y crea el pedido."),
        _l("Специалист по закупкам", "Buyer", "Comprador"),
        _l("Система закупок", "Procurement system", "Sistema de compras"), "procurement",
        _l(("Подана заявка", "Зарегистрировать потребность", "Проверить бюджет и поставщика", "Закупка одобрена?", "Создать заказ", "Вернуть инициатору"), ("Request submitted", "Register demand", "Check budget and supplier", "Is purchase approved?", "Create purchase order", "Return to requester"), ("Solicitud presentada", "Registrar necesidad", "Comprobar presupuesto y proveedor", "Compra aprobada?", "Crear pedido", "Devolver al solicitante")),
        ("закупк", "заявка на покуп", "заказ поставщик", "purchase request", "purchase order", "procurement", "solicitud de compra"),
    ),
    TemplateSpec(
        "supplier-onboarding", "procurement", "procurement",
        _l("Подключение нового поставщика", "Supplier onboarding", "Alta de proveedor"),
        _l("Собирает реквизиты, проверяет поставщика и создает его карточку в учетной системе.", "Collects supplier details, performs checks, and creates the vendor record.", "Recopila datos, verifica al proveedor y crea su ficha en el sistema."),
        _l("Специалист по закупкам", "Buyer", "Comprador"),
        _l("Система закупок", "Procurement system", "Sistema de compras"), "procurement",
        _l(("Запрошено подключение", "Собрать реквизиты", "Проверить поставщика", "Проверка пройдена?", "Создать карточку поставщика", "Запросить исправления"), ("Onboarding requested", "Collect supplier details", "Verify supplier", "Did checks pass?", "Create supplier record", "Request corrections"), ("Alta solicitada", "Recopilar datos", "Verificar proveedor", "Verificacion superada?", "Crear ficha de proveedor", "Solicitar correcciones")),
        ("новый поставщик", "проверка поставщик", "реквизит поставщик", "supplier onboarding", "vendor onboarding", "alta proveedor"),
    ),
    TemplateSpec(
        "inventory-replenishment", "procurement", "inventory",
        _l("Пополнение запасов", "Inventory replenishment", "Reposicion de inventario"),
        _l("Контролирует остатки, рассчитывает потребность и создает заказ при достижении точки пополнения.", "Monitors stock, calculates demand, and creates an order when the reorder point is reached.", "Controla existencias, calcula la necesidad y crea un pedido al llegar al punto de reposicion."),
        _l("Специалист по снабжению", "Inventory planner", "Planificador de inventario"),
        _l("Система складского учета", "Inventory system", "Sistema de inventario"), "inventory",
        _l(("Обновились остатки", "Рассчитать доступный запас", "Проверить прогноз спроса", "Нужно пополнение?", "Создать заказ поставщику", "Продолжить наблюдение"), ("Stock updated", "Calculate available stock", "Review demand forecast", "Is replenishment needed?", "Create supplier order", "Continue monitoring"), ("Stock actualizado", "Calcular existencias", "Revisar demanda", "Hace falta reponer?", "Crear pedido", "Continuar seguimiento")),
        ("остатк", "пополнени", "склад", "запас", "inventory replenishment", "reorder point", "stock", "reposicion"),
    ),
    TemplateSpec(
        "order-fulfillment", "operations", "order_management",
        _l("Исполнение заказа клиента", "Customer order fulfillment", "Preparacion de pedido de cliente"),
        _l("Проверяет оплату и наличие, комплектует заказ, организует доставку и уведомляет клиента.", "Checks payment and stock, picks the order, arranges delivery, and notifies the customer.", "Comprueba pago y stock, prepara el pedido, organiza entrega y avisa al cliente."),
        _l("Менеджер операций", "Operations manager", "Responsable de operaciones"),
        _l("Система управления заказами", "Order management system", "Sistema de pedidos"), "order_management",
        _l(("Получен заказ", "Проверить оплату и наличие", "Скомплектовать заказ", "Заказ готов?", "Передать в доставку", "Сообщить о задержке"), ("Order received", "Check payment and stock", "Pick and pack order", "Is the order ready?", "Hand over for delivery", "Notify about delay"), ("Pedido recibido", "Comprobar pago y stock", "Preparar pedido", "Pedido listo?", "Entregar a transporte", "Avisar del retraso")),
        ("заказ клиент", "комплектац", "доставк", "order fulfillment", "shipping", "pick and pack", "preparacion pedido"),
    ),
    TemplateSpec(
        "returns-refunds", "operations", "order_management",
        _l("Возврат товара и денег", "Returns and refunds", "Devoluciones y reembolsos"),
        _l("Принимает запрос, проверяет условия возврата, оформляет прием товара и возврат оплаты.", "Receives a request, checks return eligibility, receives the item, and issues a refund.", "Recibe la solicitud, comprueba condiciones, recibe el producto y emite el reembolso."),
        _l("Менеджер операций", "Operations manager", "Responsable de operaciones"),
        _l("Система управления заказами", "Order management system", "Sistema de pedidos"), "order_management",
        _l(("Запрошен возврат", "Найти заказ", "Проверить срок и состояние", "Возврат допустим?", "Оформить возврат денег", "Отказать с объяснением"), ("Return requested", "Find original order", "Check window and condition", "Is return eligible?", "Issue refund", "Decline with explanation"), ("Devolucion solicitada", "Buscar pedido", "Comprobar plazo y estado", "Devolucion permitida?", "Emitir reembolso", "Rechazar con explicacion")),
        ("возврат товар", "возврат денег", "рефанд", "returns", "refund", "return merchandise", "devolucion", "reembolso"),
    ),
    TemplateSpec(
        "support-ticket", "service", "customer_support",
        _l("Обработка обращения клиента", "Customer support ticket", "Ticket de soporte al cliente"),
        _l("Регистрирует обращение, определяет приоритет, назначает исполнителя и контролирует решение.", "Registers a request, sets priority, assigns an owner, and tracks resolution.", "Registra la solicitud, fija prioridad, asigna responsable y controla la resolucion."),
        _l("Специалист поддержки", "Support specialist", "Especialista de soporte"),
        _l("Сервис-деск", "Service desk", "Mesa de ayuda"), "ticketing",
        _l(("Получено обращение", "Создать тикет", "Диагностировать проблему", "Можно решить сразу?", "Отправить решение клиенту", "Эскалировать специалисту"), ("Request received", "Create ticket", "Diagnose issue", "Can it be resolved now?", "Send resolution", "Escalate to specialist"), ("Solicitud recibida", "Crear ticket", "Diagnosticar problema", "Se puede resolver ahora?", "Enviar solucion", "Escalar a especialista")),
        ("обращение клиент", "тикет", "поддержк", "service desk", "support ticket", "customer support", "ticket soporte"),
    ),
    TemplateSpec(
        "incident-escalation", "service", "incident_management",
        _l("Управление инцидентом", "Incident escalation", "Escalado de incidentes"),
        _l("Фиксирует сбой, оценивает влияние, привлекает ответственных и контролирует восстановление.", "Records an incident, assesses impact, engages responders, and tracks recovery.", "Registra un incidente, evalua impacto, moviliza responsables y controla recuperacion."),
        _l("Координатор инцидента", "Incident coordinator", "Coordinador de incidentes"),
        _l("Система мониторинга", "Monitoring system", "Sistema de monitorizacion"), "monitoring",
        _l(("Обнаружен сбой", "Создать инцидент", "Оценить влияние и приоритет", "Инцидент критический?", "Созвать группу реагирования", "Назначить обычную очередь"), ("Failure detected", "Create incident", "Assess impact and priority", "Is the incident critical?", "Page response team", "Assign standard queue"), ("Fallo detectado", "Crear incidente", "Evaluar impacto y prioridad", "Incidente critico?", "Convocar equipo", "Asignar cola normal")),
        ("инцидент", "сбой", "авари", "эскалац", "incident escalation", "outage", "critical incident", "incidente"),
    ),
    TemplateSpec(
        "employee-onboarding", "hr", "human_resources",
        _l("Онбординг сотрудника", "Employee onboarding", "Incorporacion de empleados"),
        _l("Собирает данные нового сотрудника, готовит доступы и рабочее место, контролирует первый день.", "Collects new hire data, prepares access and equipment, and coordinates the first day.", "Recopila datos, prepara accesos y equipo, y coordina el primer dia."),
        _l("HR-специалист", "HR specialist", "Especialista de RRHH"),
        _l("HR-система", "HR system", "Sistema de RRHH"), "hris",
        _l(("Кандидат принял оффер", "Создать карточку сотрудника", "Подготовить доступы и оборудование", "Все готово к выходу?", "Подтвердить первый день", "Эскалировать подготовку"), ("Offer accepted", "Create employee record", "Prepare access and equipment", "Ready for start date?", "Confirm first day", "Escalate preparation"), ("Oferta aceptada", "Crear ficha de empleado", "Preparar accesos y equipo", "Todo listo?", "Confirmar primer dia", "Escalar preparacion")),
        ("онбординг сотрудник", "новый сотрудник", "выход сотрудник", "employee onboarding", "new hire", "alta empleado"),
    ),
    TemplateSpec(
        "leave-request", "hr", "human_resources",
        _l("Заявка на отпуск", "Leave request approval", "Aprobacion de vacaciones"),
        _l("Проверяет остаток дней и пересечения, согласует отсутствие и обновляет календарь.", "Checks leave balance and conflicts, obtains approval, and updates the calendar.", "Comprueba saldo y conflictos, obtiene aprobacion y actualiza el calendario."),
        _l("HR-специалист", "HR specialist", "Especialista de RRHH"),
        _l("HR-система", "HR system", "Sistema de RRHH"), "hris",
        _l(("Подана заявка на отпуск", "Проверить остаток дней", "Оценить пересечения в команде", "Отпуск согласован?", "Обновить календарь", "Вернуть для выбора дат"), ("Leave requested", "Check leave balance", "Review team conflicts", "Is leave approved?", "Update calendar", "Return for new dates"), ("Vacaciones solicitadas", "Comprobar saldo", "Revisar conflictos", "Vacaciones aprobadas?", "Actualizar calendario", "Solicitar otras fechas")),
        ("отпуск", "отгул", "отсутстви", "leave request", "vacation approval", "time off", "vacaciones"),
    ),
    TemplateSpec(
        "recruitment", "hr", "human_resources",
        _l("Подбор сотрудника", "Recruitment and hiring", "Seleccion y contratacion"),
        _l("Открывает вакансию, проводит отбор и интервью, согласует кандидата и отправляет оффер.", "Opens a vacancy, screens and interviews candidates, approves a finalist, and sends an offer.", "Abre una vacante, filtra y entrevista candidatos, aprueba finalista y envia oferta."),
        _l("HR-специалист", "HR specialist", "Especialista de RRHH"),
        _l("Система подбора", "Applicant tracking system", "Sistema de seleccion"), "ats",
        _l(("Согласована вакансия", "Опубликовать вакансию", "Провести отбор и интервью", "Кандидат подходит?", "Отправить оффер", "Сообщить об отказе"), ("Vacancy approved", "Publish vacancy", "Screen and interview", "Is the candidate suitable?", "Send offer", "Send rejection"), ("Vacante aprobada", "Publicar vacante", "Filtrar y entrevistar", "Candidato adecuado?", "Enviar oferta", "Enviar rechazo")),
        ("ваканси", "кандидат", "найм", "подбор сотрудник", "recruitment", "hiring", "candidate", "contratacion"),
    ),
    TemplateSpec(
        "service-appointment", "operations", "field_service",
        _l("Выездная заявка или запись на услугу", "Service appointment and work order", "Cita de servicio y orden de trabajo"),
        _l("Принимает заявку, подбирает время и исполнителя, контролирует выполнение и закрывает заказ-наряд.", "Receives a request, schedules an owner, tracks delivery, and closes the work order.", "Recibe solicitud, programa responsable, controla ejecucion y cierra la orden."),
        _l("Диспетчер", "Dispatcher", "Despachador"),
        _l("Система планирования", "Scheduling system", "Sistema de planificacion"), "scheduling",
        _l(("Получена заявка", "Создать заказ-наряд", "Назначить время и исполнителя", "Ресурсы доступны?", "Подтвердить запись", "Предложить другое время"), ("Request received", "Create work order", "Schedule time and owner", "Are resources available?", "Confirm appointment", "Offer another time"), ("Solicitud recibida", "Crear orden de trabajo", "Asignar hora y responsable", "Recursos disponibles?", "Confirmar cita", "Ofrecer otra hora")),
        ("запись на услуг", "выезд", "заказ-наряд", "мастер", "service appointment", "work order", "field service", "cita servicio"),
    ),
    TemplateSpec(
        "content-approval", "marketing", "marketing",
        _l("Согласование контента", "Marketing content approval", "Aprobacion de contenido"),
        _l("Проводит материал через редактуру, проверку бренда и финальное согласование перед публикацией.", "Routes content through editing, brand review, and final approval before publishing.", "Pasa contenido por edicion, revision de marca y aprobacion final antes de publicar."),
        _l("Маркетолог", "Marketing specialist", "Especialista de marketing"),
        _l("Система управления контентом", "Content management system", "Sistema de contenidos"), "cms",
        _l(("Создан черновик", "Зарегистрировать материал", "Проверить текст и оформление", "Материал согласован?", "Запланировать публикацию", "Вернуть автору"), ("Draft created", "Register content item", "Review copy and design", "Is content approved?", "Schedule publication", "Return to author"), ("Borrador creado", "Registrar contenido", "Revisar texto y diseno", "Contenido aprobado?", "Programar publicacion", "Devolver al autor")),
        ("контент", "публикац", "редактур", "согласование материал", "content approval", "editorial workflow", "publish", "contenido"),
    ),
)


CATEGORY_NAMES = {
    "sales": _l("Продажи", "Sales", "Ventas"),
    "service": _l("Клиентский сервис", "Customer service", "Atencion al cliente"),
    "finance": _l("Финансы", "Finance", "Finanzas"),
    "procurement": _l("Закупки и склад", "Procurement and inventory", "Compras e inventario"),
    "hr": _l("Сотрудники", "People", "Personas"),
    "operations": _l("Операции", "Operations", "Operaciones"),
    "marketing": _l("Маркетинг", "Marketing", "Marketing"),
    "analytics_compliance": _l("Аналитика, риски и комплаенс", "Analytics, risk and compliance", "Analítica, riesgo y cumplimiento"),
    "autonomous_agents": _l("Автономные агенты", "Autonomous agents", "Agentes autónomos"),
    "cross_functional": _l("Сквозные процессы", "Cross-functional", "Procesos transversales"),
    "ecommerce_inventory": _l("E-commerce и запасы", "E-commerce and inventory", "Comercio electrónico e inventario"),
    "finance_procurement": _l("Финансы и закупки", "Finance and procurement", "Finanzas y compras"),
    "hr_people": _l("Сотрудники и HR", "HR and people", "Personas y RR. HH."),
    "it_devops_security": _l("IT, DevOps и безопасность", "IT, DevOps and security", "TI, DevOps y seguridad"),
    "marketing_content": _l("Маркетинг и контент", "Marketing and content", "Marketing y contenido"),
    "operations_documents": _l("Операции и документы", "Operations and documents", "Operaciones y documentos"),
    "sales_crm": _l("Продажи и CRM", "Sales and CRM", "Ventas y CRM"),
    "support_cx": _l("Поддержка и клиентский опыт", "Support and customer experience", "Soporte y experiencia del cliente"),
}


CATALOG_PATH = WORKSPACE_ROOT / "data" / "process_library" / "n8n" / "v1" / "n8n_process_library_50_v1.json"
BATCH_071_300_PATH = WORKSPACE_ROOT / "data" / "process_library" / "batch_071_300" / "v1" / "process_library_230_batch_v1.json"
BATCH_071_300_LOCALIZATIONS_PATH = WORKSPACE_ROOT / "data" / "process_library" / "batch_071_300" / "v1" / "LOCALIZATIONS_v1.json"
BATCH_EXACT_DUPLICATE_IDS = {
    "sales_crm.inbound_lead_qualification",
    "hr_people.interview_scheduling",
    "ecommerce_inventory.abandoned_cart_recovery",
    "operations_documents.contract_risk_review",
}
BATCH_STEP_NAMES = {
    "act": _l("Выполнить действие", "Act", "Actuar"),
    "analyze": _l("Проанализировать", "Analyze", "Analizar"),
    "approve": _l("Согласовать", "Approve", "Aprobar"),
    "approve/escalate": _l("Согласовать или эскалировать", "Approve or escalate", "Aprobar o escalar"),
    "assess": _l("Оценить", "Assess", "Evaluar"),
    "audit": _l("Провести аудит", "Audit", "Auditar"),
    "brief": _l("Подготовить бриф", "Prepare brief", "Preparar brief"),
    "classify": _l("Классифицировать", "Classify", "Clasificar"),
    "close": _l("Закрыть", "Close", "Cerrar"),
    "collect": _l("Собрать данные", "Collect", "Recopilar"),
    "confirm": _l("Подтвердить", "Confirm", "Confirmar"),
    "coordinate": _l("Скоординировать", "Coordinate", "Coordinar"),
    "decide": _l("Принять решение", "Decide", "Decidir"),
    "delegate/tool-use": _l("Делегировать или вызвать инструмент", "Delegate or use tool", "Delegar o usar herramienta"),
    "deliver": _l("Передать результат", "Deliver", "Entregar"),
    "detect/request": _l("Обнаружить или принять запрос", "Detect or receive request", "Detectar o recibir solicitud"),
    "enrich": _l("Обогатить данные", "Enrich", "Enriquecer"),
    "escalate": _l("Эскалировать", "Escalate", "Escalar"),
    "evaluate": _l("Оценить результат", "Evaluate", "Evaluar resultado"),
    "event": _l("Обработать событие", "Handle event", "Gestionar evento"),
    "evidence": _l("Собрать подтверждения", "Collect evidence", "Recopilar evidencias"),
    "execute": _l("Выполнить", "Execute", "Ejecutar"),
    "extract": _l("Извлечь данные", "Extract", "Extraer"),
    "fulfill": _l("Исполнить", "Fulfill", "Cumplir"),
    "generate": _l("Сформировать", "Generate", "Generar"),
    "goal": _l("Определить цель", "Define goal", "Definir objetivo"),
    "learn": _l("Учесть результат", "Learn", "Aprender"),
    "measure": _l("Измерить", "Measure", "Medir"),
    "notify": _l("Уведомить", "Notify", "Notificar"),
    "observe": _l("Проверить результат", "Observe", "Observar"),
    "persist": _l("Сохранить", "Persist", "Guardar"),
    "plan": _l("Составить план", "Plan", "Planificar"),
    "post": _l("Провести запись", "Post", "Registrar"),
    "prioritize": _l("Расставить приоритеты", "Prioritize", "Priorizar"),
    "provision": _l("Предоставить ресурс", "Provision", "Aprovisionar"),
    "publish": _l("Опубликовать", "Publish", "Publicar"),
    "receive": _l("Получить", "Receive", "Recibir"),
    "reconcile": _l("Сверить", "Reconcile", "Conciliar"),
    "record": _l("Зафиксировать", "Record", "Registrar"),
    "remediate": _l("Устранить проблему", "Remediate", "Corregir"),
    "report": _l("Подготовить отчёт", "Report", "Informar"),
    "request": _l("Принять запрос", "Request", "Solicitar"),
    "research": _l("Провести исследование", "Research", "Investigar"),
    "reserve": _l("Зарезервировать", "Reserve", "Reservar"),
    "resolve": _l("Разрешить", "Resolve", "Resolver"),
    "retain": _l("Сохранить по политике", "Retain", "Conservar"),
    "review": _l("Проверить", "Review", "Revisar"),
    "sign": _l("Подписать", "Sign", "Firmar"),
    "store": _l("Сохранить данные", "Store", "Almacenar"),
    "validate": _l("Проверить данные", "Validate", "Validar"),
    "verify": _l("Подтвердить результат", "Verify", "Verificar"),
}
CATALOG_CATEGORY_MAP = {
    "sales": "sales",
    "finance": "finance",
    "procurement": "procurement",
    "support": "service",
    "cx": "service",
    "hr": "hr",
    "marketing": "marketing",
    "commerce": "operations",
    "inventory": "procurement",
    "operations": "operations",
    "documents": "operations",
}


def _catalog_keywords(item: dict[str, Any], english_name: str) -> tuple[str, ...]:
    title_ru = item["title_ru"]
    semantic_words = item["id"].split(".", 1)[-1].replace("_", " ")
    values = [title_ru.casefold(), english_name.casefold(), semantic_words.casefold()]
    values.extend(word.casefold() for word in title_ru.replace("/", " ").split() if len(word) >= 5)
    values.extend(word.casefold() for word in semantic_words.split() if len(word) >= 5)
    return tuple(dict.fromkeys(values))


def _load_catalog_template_specs() -> tuple[CatalogTemplateSpec, ...]:
    payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    specs: list[CatalogTemplateSpec] = []
    preview_steps = _l(
        ("Уточнить входные данные", "Согласовать правила и действия", "Подтвердить результат процесса"),
        ("Confirm inputs", "Agree rules and actions", "Confirm the process outcome"),
        ("Confirmar entradas", "Acordar reglas y acciones", "Confirmar el resultado del proceso"),
    )
    for item in payload["processes"]:
        source = item["source"]
        prefix = item["id"].split(".", 1)[0]
        category = CATALOG_CATEGORY_MAP[prefix]
        english_name = item["id"].split(".", 1)[-1].replace("_", " ").title()
        name = _l(item["title_ru"], english_name, english_name)
        description = _l(
            f"Черновик типового процесса «{item['title_ru']}». Его границы, роли и правила необходимо подтвердить в интервью.",
            f"Interview draft for the {english_name.lower()} process. Confirm its scope, roles, and rules before automation.",
            f"Borrador de entrevista para el proceso {english_name.lower()}. Confirme su alcance, roles y reglas antes de automatizarlo.",
        )
        specs.append(
            CatalogTemplateSpec(
                id=f"catalog-{item['id'].replace('.', '-').replace('_', '-')}",
                category=category,
                domain=item["id"].split(".", 1)[0],
                name=name,
                description=description,
                preview_steps=preview_steps,
                keywords=_catalog_keywords(item, english_name),
                priority=item["priority"],
                ai_required=item["ai_required"],
                human_in_loop=item["human_in_loop"],
                automation_pattern=item["automation_pattern"],
                source_template_id=source["template_id"],
                source_url=source["url"],
            )
        )
    return tuple(specs)


def _load_batch_071_300_template_specs() -> tuple[CatalogTemplateSpec, ...]:
    payload = json.loads(BATCH_071_300_PATH.read_text(encoding="utf-8"))
    localized_titles = json.loads(BATCH_071_300_LOCALIZATIONS_PATH.read_text(encoding="utf-8"))["titles"]
    specs: list[CatalogTemplateSpec] = []
    for item in payload["processes"]:
        if item["id"] in BATCH_EXACT_DUPLICATE_IDS:
            continue
        english_name = item["title_en"]
        localized_title = localized_titles[item["id"]]
        russian_name = localized_title["ru"]
        spanish_name = localized_title["es"]
        preview_steps = {
            locale: tuple(BATCH_STEP_NAMES[step][locale] for step in item["semantic_steps"])
            for locale in ("ru", "en", "es")
        }
        name = _l(russian_name, english_name, spanish_name)
        description = _l(
            f"Черновик процесса «{russian_name}». Подтвердите цель, роли, правила и интеграции в интервью.",
            f"Interview draft for “{english_name}”. Confirm its goal, roles, rules, and integrations before automation.",
            f"Borrador de entrevista para «{spanish_name}». Confirme objetivo, roles, reglas e integraciones antes de automatizar.",
        )
        keywords = tuple(dict.fromkeys([
            english_name.casefold(),
            item["id"].split(".", 1)[-1].replace("_", " ").casefold(),
            *(word.casefold() for word in english_name.split() if len(word) >= 5),
            *(role.casefold().replace("_", " ") for role in item["adapter_roles"]),
        ]))
        specs.append(
            CatalogTemplateSpec(
                id=f"catalog-{item['id'].replace('.', '-').replace('_', '-')}",
                category=item["category"],
                domain=item["category"],
                name=name,
                description=description,
                preview_steps=preview_steps,
                keywords=keywords,
                priority=item["priority"],
                ai_required=item["uses_ai"],
                human_in_loop=item["human_in_the_loop"],
                automation_pattern=item["automation_pattern"],
                source_template_id=None,
                source_url=item["provenance"]["source_url"],
                library_number=item["library_number"],
                agent_export=item["agent_export"],
                adapter_roles=tuple(item["adapter_roles"]),
                quality_controls=tuple(item["quality_controls"]),
            )
        )
    return tuple(specs)


LEGACY_CATALOG_TEMPLATE_SPECS = _load_catalog_template_specs()
BATCH_071_300_TEMPLATE_SPECS = _load_batch_071_300_template_specs()
CATALOG_TEMPLATE_SPECS = LEGACY_CATALOG_TEMPLATE_SPECS + BATCH_071_300_TEMPLATE_SPECS
ALL_TEMPLATE_SPECS: tuple[TemplateDefinition, ...] = TEMPLATE_SPECS + CATALOG_TEMPLATE_SPECS


def _copy(value: Localized, locale: str) -> Any:
    return value[normalize_locale(locale)]


def _step(
    step_id: str,
    step_type: str,
    title: str,
    *,
    actor_id: str | None = None,
    system_id: str | None = None,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
) -> dict[str, Any]:
    automated = step_type in {"system_task", "decision"}
    return {
        "id": step_id,
        "type": step_type,
        "title": title,
        "description": "",
        "actorId": actor_id,
        "systemId": system_id,
        "inputs": inputs or [],
        "outputs": outputs or [],
        "operation": {"kind": "condition" if step_type == "decision" else step_type, "name": step_id.removeprefix("step_"), "parameters": {}},
        "missingFields": [],
        "automationHint": {"target": "n8n", "nodeType": "n8n-nodes-base.if" if step_type == "decision" else "n8n-nodes-base.httpRequest"} if automated else None,
    }


def _build_catalog_process_template(spec: CatalogTemplateSpec, locale: str) -> dict[str, Any]:
    normalized_locale = normalize_locale(locale)
    process_id = f"template_{spec.id.replace('-', '_')}"
    start_title, end_title, question = _copy(
        _l(
            ("Процесс инициирован", "Результат процесса подтверждён", "Опишите, что запускает процесс, кто в нём участвует и какой результат считается успешным."),
            ("Process initiated", "Process outcome confirmed", "Describe what starts the process, who participates, and what outcome is considered successful."),
            ("Proceso iniciado", "Resultado del proceso confirmado", "Describa qué inicia el proceso, quién participa y qué resultado se considera satisfactorio."),
        ),
        normalized_locale,
    )
    blocked = {"score": 0, "status": "blocked", "notes": ["catalog_interview_draft"]}
    open_questions = [
        {
            "id": "question_confirm_process",
            "priority": "high",
            "target": {"entity": "process", "id": process_id},
            "question": question,
            "blocksAutomationReady": True,
        }
    ]
    if spec.agent_export and spec.agent_export.get("enabled"):
        agent = spec.agent_export
        suggested_topology = agent["topology"]
        suggested_roles = ", ".join(agent["roles"])
        suggested_tools = ", ".join(spec.adapter_roles)
        suggested_memory = ", ".join(agent["memory"])
        suggested_approvals = ", ".join(agent["approval_points"])
        suggested_stops = ", ".join(agent["stop_conditions"])
        suggested_evaluation = agent["evaluation"]
        agent_questions = _copy(
            _l(
                (
                    f"Каталог предлагает topology `{suggested_topology}` и роли `{suggested_roles}`. Подтвердите роли, границы и схему взаимодействия.",
                    f"Предлагаемые адаптеры и инструменты: `{suggested_tools}`. Какие из них разрешены и какие действия явно запрещены?",
                    f"Предлагаемые типы памяти: `{suggested_memory}`. Какие данные можно хранить и каков срок хранения?",
                    f"Предлагаемые точки подтверждения: `{suggested_approvals}`. Какие внешние или значимые действия требуют решения человека?",
                    f"Предлагаемые условия остановки: `{suggested_stops}`; оценка: `{suggested_evaluation}`. Подтвердите остановку, эскалацию и критерии качества.",
                ),
                (
                    f"The catalog suggests topology `{suggested_topology}` and roles `{suggested_roles}`. Confirm the roles, boundaries, and interaction model.",
                    f"Suggested adapters and tools: `{suggested_tools}`. Which are allowed, and which actions are explicitly prohibited?",
                    f"Suggested memory types: `{suggested_memory}`. What data may be retained, and for how long?",
                    f"Suggested approval points: `{suggested_approvals}`. Which external or high-impact actions require a human decision?",
                    f"Suggested stop conditions: `{suggested_stops}`; evaluation: `{suggested_evaluation}`. Confirm stopping, escalation, and quality criteria.",
                ),
                (
                    f"El catálogo propone la topología `{suggested_topology}` y los roles `{suggested_roles}`. Confirme roles, límites y modelo de interacción.",
                    f"Adaptadores y herramientas sugeridos: `{suggested_tools}`. ¿Cuáles se permiten y qué acciones están prohibidas?",
                    f"Tipos de memoria sugeridos: `{suggested_memory}`. ¿Qué datos pueden conservarse y durante cuánto tiempo?",
                    f"Puntos de aprobación sugeridos: `{suggested_approvals}`. ¿Qué acciones externas o de alto impacto requieren decisión humana?",
                    f"Condiciones de parada sugeridas: `{suggested_stops}`; evaluación: `{suggested_evaluation}`. Confirme parada, escalado y criterios de calidad.",
                ),
            ),
            normalized_locale,
        )
        open_questions.extend(
            {
                "id": f"question_agent_{index}",
                "priority": "high",
                "target": {"entity": "process", "id": process_id},
                "question": agent_question,
                "blocksAutomationReady": True,
            }
            for index, agent_question in enumerate(agent_questions, 1)
        )
    process_ir = upgrade_process_ir(
        {
            "schemaVersion": "0.1",
            "process": {
                "id": process_id,
                "name": _copy(spec.name, normalized_locale),
                "description": _copy(spec.description, normalized_locale),
                "domain": spec.domain,
                "maturity": "draft",
            },
            "actors": [],
            "systems": [],
            "dataObjects": [],
            "steps": [
                _step("step_start", "start", start_title),
                _step("step_end", "end", end_title),
            ],
            "edges": [{"id": "edge_start_end", "from": "step_start", "to": "step_end", "condition": None}],
            "exceptions": [],
            "openQuestions": open_questions,
            "readiness": {
                "overall": 0,
                "categories": {
                    name: deepcopy(blocked)
                    for name in ("structure", "actors", "systems", "data", "branches", "exceptions", "automation")
                },
            },
        }
    )
    process_ir["passport"]["inScope"] = list(_copy(spec.preview_steps, normalized_locale))
    return process_ir


def build_process_template(spec: TemplateDefinition, locale: str) -> dict[str, Any]:
    if isinstance(spec, CatalogTemplateSpec):
        return apply_template_classification(_build_catalog_process_template(spec, locale), spec)
    normalized_locale = normalize_locale(locale)
    trigger, register, review, decision, success, alternative = _copy(spec.flow, normalized_locale)
    process_id = f"template_{spec.id.replace('-', '_')}"
    data_id = "data_case"
    actor_id = "actor_owner"
    system_id = "system_primary"
    yes_label, no_label = _copy(_l(("Да", "Нет"), ("Yes", "No"), ("Si", "No")), normalized_locale)
    success_condition = {"left": "route", "operator": "==", "right": yes_label}
    alternative_condition = {"left": "route", "operator": "==", "right": no_label}
    category = {"score": 85, "status": "ok", "notes": ["template_baseline"]}
    steps = [
        _step("step_start", "start", trigger, system_id=system_id, outputs=[data_id]),
        _step("step_register", "system_task", register, system_id=system_id, inputs=[data_id], outputs=[data_id]),
        _step("step_review", "human_task", review, actor_id=actor_id, system_id=system_id, inputs=[data_id], outputs=[data_id]),
        _step("step_decision", "decision", decision, actor_id=actor_id, inputs=[data_id]),
        _step("step_success", "system_task", success, system_id=system_id, inputs=[data_id], outputs=[data_id]),
        _step("step_alternative", "system_task", alternative, system_id=system_id, inputs=[data_id], outputs=[data_id]),
        _step("step_end_success", "end", success, inputs=[data_id]),
        _step("step_end_alternative", "end", alternative, inputs=[data_id]),
    ]
    process_ir = {
        "schemaVersion": "0.1",
        "process": {
            "id": process_id,
            "name": _copy(spec.name, normalized_locale),
            "description": _copy(spec.description, normalized_locale),
            "domain": spec.domain,
            "maturity": "diagram_ready",
        },
        "actors": [{"id": actor_id, "name": _copy(spec.actor, normalized_locale), "type": "human", "responsibilities": [review]}],
        "systems": [{"id": system_id, "name": _copy(spec.system, normalized_locale), "type": spec.system_type, "integrationStatus": "api_available", "notes": "Template default; confirm the actual system during the interview."}],
        "dataObjects": [{"id": data_id, "name": _copy(spec.name, normalized_locale), "fields": [
            {"name": "id", "type": "string", "required": True, "source": "primary_system"},
            {"name": "status", "type": "string", "required": True, "source": "process"},
            {"name": "created_at", "type": "datetime", "required": True, "source": "primary_system"},
        ]}],
        "steps": steps,
        "edges": [
            {"id": "edge_start_register", "from": "step_start", "to": "step_register", "condition": None},
            {"id": "edge_register_review", "from": "step_register", "to": "step_review", "condition": None},
            {"id": "edge_review_decision", "from": "step_review", "to": "step_decision", "condition": None},
            {"id": "edge_decision_success", "from": "step_decision", "to": "step_success", "condition": success_condition},
            {"id": "edge_decision_alternative", "from": "step_decision", "to": "step_alternative", "condition": alternative_condition},
            {"id": "edge_success_end", "from": "step_success", "to": "step_end_success", "condition": None},
            {"id": "edge_alternative_end", "from": "step_alternative", "to": "step_end_alternative", "condition": None},
        ],
        "exceptions": [
            {"id": "exception_register", "sourceStepId": "step_register", "trigger": "Primary system is unavailable", "handling": "Queue the request and notify the process owner."},
            {"id": "exception_success", "sourceStepId": "step_success", "trigger": "Completion action fails", "handling": "Keep the case open and create a retry task."},
            {"id": "exception_alternative", "sourceStepId": "step_alternative", "trigger": "Alternative action fails", "handling": "Notify the process owner for manual handling."},
        ],
        "openQuestions": [],
        "readiness": {"overall": 85, "categories": {name: deepcopy(category) for name in ("structure", "actors", "systems", "data", "branches", "exceptions", "automation")}},
    }
    process_ir = upgrade_process_ir(process_ir)
    process_ir["passport"].update(
        {
            "goal": _copy(spec.description, normalized_locale),
            "ownerActorId": actor_id,
            "startsWhen": trigger,
            "endsWhen": f"{success}; {alternative}",
            "inScope": [register, review, decision, success, alternative],
            "outOfScope": [
                _copy(
                    _l(
                        "Хранение учетных данных и рабочий запуск интеграций",
                        "Credential storage and production activation of integrations",
                        "Almacenamiento de credenciales y activacion productiva de integraciones",
                    ),
                    normalized_locale,
                )
            ],
            "successMetrics": [
                {
                    "id": "metric_completion_rate",
                    "name": _copy(
                        _l(
                            "Доля обращений, завершенных по процессу",
                            "Cases completed through the process",
                            "Casos completados mediante el proceso",
                        ),
                        normalized_locale,
                    ),
                    "target": ">= 90",
                    "unit": "%",
                }
            ],
        }
    )
    process_ir["states"] = [
        {"id": "state_received", "dataObjectId": data_id, "name": trigger, "description": "", "initial": True, "terminal": False},
        {"id": "state_in_progress", "dataObjectId": data_id, "name": review, "description": "", "initial": False, "terminal": False},
        {"id": "state_completed", "dataObjectId": data_id, "name": success, "description": "", "initial": False, "terminal": True},
        {"id": "state_alternative", "dataObjectId": data_id, "name": alternative, "description": "", "initial": False, "terminal": True},
    ]
    process_ir["stateTransitions"] = [
        {"id": "transition_start", "dataObjectId": data_id, "fromStateId": "state_received", "toStateId": "state_in_progress", "trigger": register, "ruleIds": []},
        {"id": "transition_success", "dataObjectId": data_id, "fromStateId": "state_in_progress", "toStateId": "state_completed", "trigger": success, "ruleIds": ["rule_decision_success"]},
        {"id": "transition_alternative", "dataObjectId": data_id, "fromStateId": "state_in_progress", "toStateId": "state_alternative", "trigger": alternative, "ruleIds": ["rule_decision_alternative"]},
    ]
    return apply_template_classification(process_ir, spec)


def serialize_template(spec: TemplateDefinition, locale: str, *, include_process_ir: bool = True) -> dict[str, Any]:
    process_ir = build_process_template(spec, locale)
    is_catalog_draft = isinstance(spec, CatalogTemplateSpec)
    result = {
        "id": spec.id,
        "category": spec.category,
        "category_name": _copy(CATEGORY_NAMES[spec.category], locale),
        "name": process_ir["process"]["name"],
        "description": process_ir["process"]["description"],
        "step_count": len(process_ir["steps"]),
        "actor_count": len(process_ir["actors"]),
        "system_count": len(process_ir["systems"]),
        "preview_steps": list(_copy(spec.preview_steps, locale)) if is_catalog_draft else [step["title"] for step in process_ir["steps"] if step["type"] not in {"start", "end"}],
        "status": "interview_draft" if is_catalog_draft else "ready",
        "priority": spec.priority if is_catalog_draft else None,
        "ai_required": spec.ai_required if is_catalog_draft else None,
        "human_in_loop": spec.human_in_loop if is_catalog_draft else None,
        "automation_pattern": spec.automation_pattern if is_catalog_draft else None,
        "source_template_id": spec.source_template_id if is_catalog_draft else None,
        "source_url": spec.source_url if is_catalog_draft else None,
        "library_number": spec.library_number if is_catalog_draft else None,
        "agent_enabled": bool(spec.agent_export and spec.agent_export.get("enabled")) if is_catalog_draft else False,
        "agent_topology": spec.agent_export.get("topology") if is_catalog_draft and spec.agent_export else None,
        "search_terms": list(spec.keywords),
        "rubric_entry_ids": template_rubric_entry_ids(spec),
    }
    if include_process_ir:
        result["process_ir"] = process_ir
    return result


def list_process_templates(locale: str, rubric_entry_ids: set[str] | None = None) -> list[dict[str, Any]]:
    selected = rubric_entry_ids or set()
    return [
        serialize_template(spec, locale, include_process_ir=False)
        for spec in ALL_TEMPLATE_SPECS
        if selected.issubset(set(template_rubric_entry_ids(spec)))
    ]


def get_process_template(template_id: str, locale: str) -> dict[str, Any] | None:
    spec = find_process_template(template_id)
    return serialize_template(spec, locale) if spec else None


def find_process_template(template_id: str) -> TemplateDefinition | None:
    return next((spec for spec in ALL_TEMPLATE_SPECS if spec.id == template_id), None)


def _rubric_term_matches(term: str, normalized_text: str) -> bool:
    normalized_term = term.casefold()
    if normalized_term in normalized_text:
        return True
    meaningful_words = [word for word in normalized_term.replace("-", " ").split() if len(word) >= 5]
    return bool(meaningful_words) and all(word[:5] in normalized_text for word in meaningful_words)


def suggest_process_template(
    text: str,
    locale: str,
    excluded_ids: set[str] | None = None,
    rubric_entry_ids: set[str] | None = None,
) -> dict[str, Any] | None:
    normalized = " ".join(text.casefold().split())
    excluded = excluded_ids or set()
    selected = rubric_entry_ids or set()
    ranked: list[tuple[int, int, int, TemplateDefinition, list[str]]] = []
    for index, spec in enumerate(ALL_TEMPLATE_SPECS):
        if spec.id in excluded:
            continue
        template_entry_ids = set(template_rubric_entry_ids(spec))
        if selected and not selected.issubset(template_entry_ids):
            continue
        rubric_terms = localized_entry_names(
            [identifier for identifier in template_entry_ids if ":domain:" in identifier or ":automation_mode:" in identifier],
            locale,
        )
        keyword_matches = [keyword for keyword in spec.keywords if keyword.casefold() in normalized]
        rubric_matches = [term for term in rubric_terms if _rubric_term_matches(term, normalized)]
        matches = list(dict.fromkeys((*keyword_matches, *rubric_matches)))
        score = len(matches) + len(selected) * 2
        if score:
            ranked.append((score, int(isinstance(spec, TemplateSpec)), -index, spec, matches))
    if not ranked:
        return None
    count, _, _, spec, matches = max(ranked, key=lambda item: (item[0], item[1], item[2]))
    strong_match = any(len(item) >= 10 or " " in item for item in matches)
    if not selected and count < 2 and not strong_match:
        return None
    copy = {
        "ru": "Похоже на типовой процесс. Совпали признаки: ",
        "en": "This resembles a common process. Matched signals: ",
        "es": "Se parece a un proceso habitual. Coincidencias: ",
    }
    return {
        "template": serialize_template(spec, locale),
        "confidence": min(0.96, 0.52 + count * 0.11),
        "reason": copy[normalize_locale(locale)] + ", ".join((matches or localized_entry_names(list(selected), locale))[:4]),
        "matched_signals": (matches or localized_entry_names(list(selected), locale))[:4],
    }
