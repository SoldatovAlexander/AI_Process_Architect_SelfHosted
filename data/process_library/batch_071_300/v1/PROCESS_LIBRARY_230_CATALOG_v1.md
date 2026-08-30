# Process Library — batch 071–300

Новых кандидатов: **230**. Проектный итог до дедупликации: **300**.

## Классификация

| Класс | Количество |
|---|---:|
| Sales & CRM | 24 |
| Finance & Procurement | 24 |
| Support & CX | 21 |
| HR & People | 20 |
| Marketing & Content | 20 |
| E-commerce & Inventory | 20 |
| Operations & Documents | 20 |
| IT, DevOps & Security | 22 |
| Analytics, Risk & Compliance | 21 |
| Autonomous Agents | 28 |
| Cross-functional | 10 |

Приоритеты: P0 — 92, P1 — 103, P2 — 35.

## Каталог

| № | Semantic ID | Процесс | Класс | Приоритет | AI | HITL |
|---:|---|---|---|:---:|:---:|:---:|
| 71 | `sales_crm.lead_capture_from_website_and_messengers` | Lead capture from website and messengers | Sales & CRM | P0 | Нет | Нет |
| 72 | `sales_crm.lead_identity_resolution_and_deduplication` | Lead identity resolution and deduplication | Sales & CRM | P0 | Нет | Нет |
| 73 | `sales_crm.lead_enrichment_from_public_sources` | Lead enrichment from public sources | Sales & CRM | P0 | Нет | Нет |
| 74 | `sales_crm.inbound_lead_qualification` | Inbound lead qualification | Sales & CRM | P0 | Нет | Нет |
| 75 | `sales_crm.lead_scoring_and_prioritization` | Lead scoring and prioritization | Sales & CRM | P0 | Нет | Нет |
| 76 | `sales_crm.territory_based_lead_routing` | Territory-based lead routing | Sales & CRM | P0 | Нет | Нет |
| 77 | `sales_crm.product_based_lead_routing` | Product-based lead routing | Sales & CRM | P0 | Нет | Нет |
| 78 | `sales_crm.round_robin_lead_assignment` | Round-robin lead assignment | Sales & CRM | P0 | Нет | Нет |
| 79 | `sales_crm.vip_lead_escalation` | VIP lead escalation | Sales & CRM | P1 | Нет | Да |
| 80 | `sales_crm.missed_lead_recovery` | Missed lead recovery | Sales & CRM | P1 | Нет | Нет |
| 81 | `sales_crm.first_response_sla_monitoring` | First-response SLA monitoring | Sales & CRM | P1 | Нет | Нет |
| 82 | `sales_crm.personalized_first_response` | Personalized first response | Sales & CRM | P1 | Нет | Нет |
| 83 | `sales_crm.multi_step_outbound_sequence` | Multi-step outbound sequence | Sales & CRM | P1 | Нет | Нет |
| 84 | `sales_crm.follow_up_after_no_response` | Follow-up after no response | Sales & CRM | P1 | Нет | Нет |
| 85 | `sales_crm.meeting_booking_from_qualified_lead` | Meeting booking from qualified lead | Sales & CRM | P1 | Нет | Нет |
| 86 | `sales_crm.meeting_reminder_and_rescheduling` | Meeting reminder and rescheduling | Sales & CRM | P1 | Нет | Нет |
| 87 | `sales_crm.post_meeting_summary_and_crm_update` | Post-meeting summary and CRM update | Sales & CRM | P1 | Да | Нет |
| 88 | `sales_crm.opportunity_stage_progression` | Opportunity stage progression | Sales & CRM | P1 | Нет | Нет |
| 89 | `sales_crm.stalled_opportunity_detection` | Stalled opportunity detection | Sales & CRM | P2 | Нет | Нет |
| 90 | `sales_crm.quote_request_preparation` | Quote request preparation | Sales & CRM | P2 | Нет | Нет |
| 91 | `sales_crm.commercial_proposal_generation` | Commercial proposal generation | Sales & CRM | P2 | Нет | Нет |
| 92 | `sales_crm.commercial_proposal_approval` | Commercial proposal approval | Sales & CRM | P2 | Нет | Да |
| 93 | `sales_crm.proposal_delivery_and_tracking` | Proposal delivery and tracking | Sales & CRM | P2 | Нет | Нет |
| 94 | `sales_crm.contract_handoff_after_win` | Contract handoff after win | Sales & CRM | P2 | Нет | Нет |
| 95 | `finance_procurement.incoming_invoice_intake` | Incoming invoice intake | Finance & Procurement | P0 | Нет | Нет |
| 96 | `finance_procurement.invoice_ocr_and_field_extraction` | Invoice OCR and field extraction | Finance & Procurement | P0 | Да | Нет |
| 97 | `finance_procurement.invoice_duplicate_detection` | Invoice duplicate detection | Finance & Procurement | P0 | Нет | Нет |
| 98 | `finance_procurement.supplier_master_validation` | Supplier master validation | Finance & Procurement | P0 | Нет | Нет |
| 99 | `finance_procurement.three_way_invoice_matching` | Three-way invoice matching | Finance & Procurement | P0 | Нет | Нет |
| 100 | `finance_procurement.invoice_approval_routing` | Invoice approval routing | Finance & Procurement | P0 | Нет | Да |
| 101 | `finance_procurement.invoice_exception_resolution` | Invoice exception resolution | Finance & Procurement | P0 | Нет | Да |
| 102 | `finance_procurement.approved_invoice_posting` | Approved invoice posting | Finance & Procurement | P0 | Нет | Нет |
| 103 | `finance_procurement.payment_calendar_preparation` | Payment calendar preparation | Finance & Procurement | P1 | Нет | Нет |
| 104 | `finance_procurement.payment_approval` | Payment approval | Finance & Procurement | P1 | Нет | Да |
| 105 | `finance_procurement.payment_status_reconciliation` | Payment status reconciliation | Finance & Procurement | P1 | Нет | Нет |
| 106 | `finance_procurement.overdue_receivables_detection` | Overdue receivables detection | Finance & Procurement | P1 | Нет | Нет |
| 107 | `finance_procurement.customer_payment_reminder` | Customer payment reminder | Finance & Procurement | P1 | Нет | Нет |
| 108 | `finance_procurement.collections_escalation` | Collections escalation | Finance & Procurement | P1 | Нет | Да |
| 109 | `finance_procurement.bank_statement_reconciliation` | Bank statement reconciliation | Finance & Procurement | P1 | Нет | Нет |
| 110 | `finance_procurement.expense_report_intake` | Expense report intake | Finance & Procurement | P1 | Нет | Нет |
| 111 | `finance_procurement.expense_policy_validation` | Expense policy validation | Finance & Procurement | P1 | Нет | Нет |
| 112 | `finance_procurement.expense_approval_and_reimbursement` | Expense approval and reimbursement | Finance & Procurement | P1 | Нет | Да |
| 113 | `finance_procurement.budget_request_intake` | Budget request intake | Finance & Procurement | P2 | Нет | Нет |
| 114 | `finance_procurement.budget_variance_monitoring` | Budget variance monitoring | Finance & Procurement | P2 | Нет | Нет |
| 115 | `finance_procurement.cash_flow_forecast_refresh` | Cash-flow forecast refresh | Finance & Procurement | P2 | Нет | Нет |
| 116 | `finance_procurement.purchase_requisition_intake` | Purchase requisition intake | Finance & Procurement | P2 | Нет | Нет |
| 117 | `finance_procurement.purchase_requisition_approval` | Purchase requisition approval | Finance & Procurement | P2 | Нет | Да |
| 118 | `finance_procurement.supplier_discovery` | Supplier discovery | Finance & Procurement | P2 | Нет | Нет |
| 119 | `support_cx.omnichannel_ticket_intake` | Omnichannel ticket intake | Support & CX | P0 | Нет | Нет |
| 120 | `support_cx.customer_identity_and_context_enrichment` | Customer identity and context enrichment | Support & CX | P0 | Нет | Нет |
| 121 | `support_cx.ticket_deduplication` | Ticket deduplication | Support & CX | P0 | Нет | Нет |
| 122 | `support_cx.ticket_classification` | Ticket classification | Support & CX | P0 | Да | Нет |
| 123 | `support_cx.sentiment_and_urgency_detection` | Sentiment and urgency detection | Support & CX | P0 | Нет | Нет |
| 124 | `support_cx.automatic_knowledge_base_answer` | Automatic knowledge-base answer | Support & CX | P0 | Нет | Нет |
| 125 | `support_cx.rag_answer_confidence_check` | RAG answer confidence check | Support & CX | P0 | Нет | Нет |
| 126 | `support_cx.human_fallback_for_uncertain_answer` | Human fallback for uncertain answer | Support & CX | P0 | Нет | Нет |
| 127 | `support_cx.skill_based_ticket_routing` | Skill-based ticket routing | Support & CX | P1 | Нет | Нет |
| 128 | `support_cx.priority_customer_routing` | Priority customer routing | Support & CX | P1 | Нет | Нет |
| 129 | `support_cx.support_sla_monitoring` | Support SLA monitoring | Support & CX | P1 | Нет | Нет |
| 130 | `support_cx.sla_breach_escalation` | SLA breach escalation | Support & CX | P1 | Нет | Да |
| 131 | `support_cx.incident_swarm_activation` | Incident swarm activation | Support & CX | P1 | Нет | Нет |
| 132 | `support_cx.customer_status_notification` | Customer status notification | Support & CX | P1 | Нет | Нет |
| 133 | `support_cx.resolution_approval_for_sensitive_cases` | Resolution approval for sensitive cases | Support & CX | P1 | Нет | Да |
| 134 | `support_cx.ticket_closure_validation` | Ticket closure validation | Support & CX | P1 | Нет | Нет |
| 135 | `support_cx.customer_satisfaction_survey` | Customer satisfaction survey | Support & CX | P1 | Нет | Нет |
| 136 | `support_cx.negative_feedback_recovery` | Negative feedback recovery | Support & CX | P1 | Нет | Нет |
| 137 | `support_cx.complaint_registration` | Complaint registration | Support & CX | P2 | Нет | Нет |
| 138 | `support_cx.complaint_investigation_coordination` | Complaint investigation coordination | Support & CX | P2 | Нет | Нет |
| 139 | `support_cx.refund_request_triage` | Refund request triage | Support & CX | P2 | Нет | Нет |
| 140 | `hr_people.candidate_application_intake` | Candidate application intake | HR & People | P0 | Нет | Нет |
| 141 | `hr_people.resume_parsing_and_normalization` | Resume parsing and normalization | HR & People | P0 | Нет | Нет |
| 142 | `hr_people.candidate_duplicate_detection` | Candidate duplicate detection | HR & People | P0 | Нет | Нет |
| 143 | `hr_people.candidate_screening` | Candidate screening | HR & People | P0 | Нет | Нет |
| 144 | `hr_people.interview_scheduling` | Interview scheduling | HR & People | P0 | Нет | Нет |
| 145 | `hr_people.interview_reminder` | Interview reminder | HR & People | P0 | Нет | Нет |
| 146 | `hr_people.interview_transcription_and_summary` | Interview transcription and summary | HR & People | P0 | Да | Нет |
| 147 | `hr_people.candidate_scorecard_consolidation` | Candidate scorecard consolidation | HR & People | P0 | Да | Нет |
| 148 | `hr_people.offer_preparation` | Offer preparation | HR & People | P1 | Нет | Нет |
| 149 | `hr_people.offer_approval` | Offer approval | HR & People | P1 | Нет | Да |
| 150 | `hr_people.offer_delivery_and_acceptance` | Offer delivery and acceptance | HR & People | P1 | Нет | Нет |
| 151 | `hr_people.preboarding_document_collection` | Preboarding document collection | HR & People | P1 | Нет | Нет |
| 152 | `hr_people.employee_onboarding_plan` | Employee onboarding plan | HR & People | P1 | Нет | Нет |
| 153 | `hr_people.account_and_access_provisioning` | Account and access provisioning | HR & People | P1 | Нет | Нет |
| 154 | `hr_people.mandatory_training_assignment` | Mandatory training assignment | HR & People | P1 | Нет | Нет |
| 155 | `hr_people.probation_milestone_tracking` | Probation milestone tracking | HR & People | P1 | Нет | Нет |
| 156 | `hr_people.employee_pulse_survey` | Employee pulse survey | HR & People | P1 | Нет | Нет |
| 157 | `hr_people.leave_request_processing` | Leave request processing | HR & People | P1 | Нет | Нет |
| 158 | `hr_people.business_trip_request_processing` | Business trip request processing | HR & People | P2 | Нет | Нет |
| 159 | `hr_people.employee_document_request` | Employee document request | HR & People | P2 | Нет | Нет |
| 160 | `marketing_content.campaign_brief_intake` | Campaign brief intake | Marketing & Content | P0 | Нет | Нет |
| 161 | `marketing_content.audience_research` | Audience research | Marketing & Content | P0 | Да | Нет |
| 162 | `marketing_content.competitor_content_monitoring` | Competitor content monitoring | Marketing & Content | P0 | Нет | Нет |
| 163 | `marketing_content.keyword_cluster_research` | Keyword cluster research | Marketing & Content | P0 | Да | Нет |
| 164 | `marketing_content.editorial_calendar_planning` | Editorial calendar planning | Marketing & Content | P0 | Нет | Нет |
| 165 | `marketing_content.content_idea_backlog` | Content idea backlog | Marketing & Content | P0 | Нет | Нет |
| 166 | `marketing_content.long_form_article_drafting` | Long-form article drafting | Marketing & Content | P0 | Да | Нет |
| 167 | `marketing_content.seo_content_optimization` | SEO content optimization | Marketing & Content | P0 | Нет | Нет |
| 168 | `marketing_content.brand_compliance_review` | Brand compliance review | Marketing & Content | P1 | Нет | Да |
| 169 | `marketing_content.legal_review_of_campaign_content` | Legal review of campaign content | Marketing & Content | P1 | Нет | Да |
| 170 | `marketing_content.human_approval_before_publication` | Human approval before publication | Marketing & Content | P1 | Нет | Да |
| 171 | `marketing_content.multi_channel_content_adaptation` | Multi-channel content adaptation | Marketing & Content | P1 | Нет | Нет |
| 172 | `marketing_content.social_post_scheduling` | Social post scheduling | Marketing & Content | P1 | Нет | Нет |
| 173 | `marketing_content.image_creative_generation` | Image creative generation | Marketing & Content | P1 | Нет | Нет |
| 174 | `marketing_content.video_script_generation` | Video script generation | Marketing & Content | P1 | Нет | Нет |
| 175 | `marketing_content.email_newsletter_assembly` | Email newsletter assembly | Marketing & Content | P1 | Нет | Нет |
| 176 | `marketing_content.email_subject_line_testing` | Email subject-line testing | Marketing & Content | P1 | Нет | Нет |
| 177 | `marketing_content.campaign_launch_checklist` | Campaign launch checklist | Marketing & Content | P1 | Нет | Нет |
| 178 | `marketing_content.utm_governance` | UTM governance | Marketing & Content | P2 | Нет | Нет |
| 179 | `marketing_content.paid_ad_anomaly_monitoring` | Paid ad anomaly monitoring | Marketing & Content | P2 | Нет | Нет |
| 180 | `ecommerce_inventory.order_intake_and_validation` | Order intake and validation | E-commerce & Inventory | P0 | Нет | Нет |
| 181 | `ecommerce_inventory.payment_confirmation_handling` | Payment confirmation handling | E-commerce & Inventory | P0 | Нет | Нет |
| 182 | `ecommerce_inventory.fraud_risk_review_handoff` | Fraud-risk review handoff | E-commerce & Inventory | P0 | Да | Да |
| 183 | `ecommerce_inventory.inventory_availability_check` | Inventory availability check | E-commerce & Inventory | P0 | Нет | Нет |
| 184 | `ecommerce_inventory.order_allocation_across_warehouses` | Order allocation across warehouses | E-commerce & Inventory | P0 | Нет | Нет |
| 185 | `ecommerce_inventory.backorder_management` | Backorder management | E-commerce & Inventory | P0 | Нет | Нет |
| 186 | `ecommerce_inventory.picking_task_creation` | Picking task creation | E-commerce & Inventory | P0 | Нет | Нет |
| 187 | `ecommerce_inventory.packing_completion_update` | Packing completion update | E-commerce & Inventory | P0 | Нет | Нет |
| 188 | `ecommerce_inventory.shipment_label_creation` | Shipment label creation | E-commerce & Inventory | P1 | Нет | Нет |
| 189 | `ecommerce_inventory.shipment_tracking_notification` | Shipment tracking notification | E-commerce & Inventory | P1 | Нет | Нет |
| 190 | `ecommerce_inventory.delivery_exception_escalation` | Delivery exception escalation | E-commerce & Inventory | P1 | Нет | Да |
| 191 | `ecommerce_inventory.order_cancellation_processing` | Order cancellation processing | E-commerce & Inventory | P1 | Нет | Нет |
| 192 | `ecommerce_inventory.return_request_intake` | Return request intake | E-commerce & Inventory | P1 | Нет | Нет |
| 193 | `ecommerce_inventory.return_eligibility_validation` | Return eligibility validation | E-commerce & Inventory | P1 | Нет | Нет |
| 194 | `ecommerce_inventory.return_logistics_coordination` | Return logistics coordination | E-commerce & Inventory | P1 | Нет | Нет |
| 195 | `ecommerce_inventory.refund_after_return_validation` | Refund after return validation | E-commerce & Inventory | P1 | Нет | Нет |
| 196 | `ecommerce_inventory.abandoned_cart_recovery` | Abandoned cart recovery | E-commerce & Inventory | P1 | Нет | Нет |
| 197 | `ecommerce_inventory.low_stock_alert` | Low-stock alert | E-commerce & Inventory | P1 | Нет | Нет |
| 198 | `ecommerce_inventory.reorder_point_monitoring` | Reorder point monitoring | E-commerce & Inventory | P2 | Нет | Нет |
| 199 | `ecommerce_inventory.purchase_replenishment_proposal` | Purchase replenishment proposal | E-commerce & Inventory | P2 | Нет | Нет |
| 200 | `operations_documents.incoming_document_registration` | Incoming document registration | Operations & Documents | P0 | Нет | Нет |
| 201 | `operations_documents.document_classification` | Document classification | Operations & Documents | P0 | Да | Нет |
| 202 | `operations_documents.document_metadata_extraction` | Document metadata extraction | Operations & Documents | P0 | Да | Нет |
| 203 | `operations_documents.document_version_control` | Document version control | Operations & Documents | P0 | Нет | Нет |
| 204 | `operations_documents.document_review_routing` | Document review routing | Operations & Documents | P0 | Нет | Да |
| 205 | `operations_documents.multi_level_document_approval` | Multi-level document approval | Operations & Documents | P0 | Нет | Да |
| 206 | `operations_documents.electronic_signature_coordination` | Electronic signature coordination | Operations & Documents | P0 | Нет | Да |
| 207 | `operations_documents.document_publication` | Document publication | Operations & Documents | P0 | Нет | Нет |
| 208 | `operations_documents.document_retention_scheduling` | Document retention scheduling | Operations & Documents | P1 | Нет | Нет |
| 209 | `operations_documents.document_archival` | Document archival | Operations & Documents | P1 | Нет | Нет |
| 210 | `operations_documents.contract_request_intake` | Contract request intake | Operations & Documents | P1 | Нет | Нет |
| 211 | `operations_documents.contract_template_selection` | Contract template selection | Operations & Documents | P1 | Нет | Нет |
| 212 | `operations_documents.contract_clause_extraction` | Contract clause extraction | Operations & Documents | P1 | Да | Нет |
| 213 | `operations_documents.contract_risk_review` | Contract risk review | Operations & Documents | P1 | Да | Да |
| 214 | `operations_documents.contract_negotiation_task_tracking` | Contract negotiation task tracking | Operations & Documents | P1 | Нет | Нет |
| 215 | `operations_documents.contract_approval` | Contract approval | Operations & Documents | P1 | Нет | Да |
| 216 | `operations_documents.contract_signature_and_storage` | Contract signature and storage | Operations & Documents | P1 | Нет | Да |
| 217 | `operations_documents.contract_obligation_monitoring` | Contract obligation monitoring | Operations & Documents | P1 | Нет | Нет |
| 218 | `operations_documents.contract_renewal_notice` | Contract renewal notice | Operations & Documents | P2 | Нет | Нет |
| 219 | `operations_documents.meeting_agenda_preparation` | Meeting agenda preparation | Operations & Documents | P2 | Нет | Нет |
| 220 | `it_devops_security.it_service_request_intake` | IT service request intake | IT, DevOps & Security | P0 | Нет | Нет |
| 221 | `it_devops_security.access_request_approval` | Access request approval | IT, DevOps & Security | P0 | Нет | Да |
| 222 | `it_devops_security.privileged_access_approval` | Privileged access approval | IT, DevOps & Security | P0 | Нет | Да |
| 223 | `it_devops_security.user_account_provisioning` | User account provisioning | IT, DevOps & Security | P0 | Нет | Нет |
| 224 | `it_devops_security.user_access_recertification` | User access recertification | IT, DevOps & Security | P0 | Нет | Нет |
| 225 | `it_devops_security.password_reset_orchestration` | Password reset orchestration | IT, DevOps & Security | P0 | Нет | Нет |
| 226 | `it_devops_security.software_license_request` | Software license request | IT, DevOps & Security | P0 | Нет | Нет |
| 227 | `it_devops_security.device_provisioning` | Device provisioning | IT, DevOps & Security | P0 | Нет | Нет |
| 228 | `it_devops_security.device_return_tracking` | Device return tracking | IT, DevOps & Security | P1 | Нет | Нет |
| 229 | `it_devops_security.security_alert_enrichment` | Security alert enrichment | IT, DevOps & Security | P1 | Нет | Нет |
| 230 | `it_devops_security.phishing_report_triage` | Phishing report triage | IT, DevOps & Security | P1 | Нет | Нет |
| 231 | `it_devops_security.vulnerability_intake_and_prioritization` | Vulnerability intake and prioritization | IT, DevOps & Security | P1 | Нет | Нет |
| 232 | `it_devops_security.patch_deployment_approval` | Patch deployment approval | IT, DevOps & Security | P1 | Нет | Да |
| 233 | `it_devops_security.backup_job_monitoring` | Backup job monitoring | IT, DevOps & Security | P1 | Нет | Нет |
| 234 | `it_devops_security.backup_restore_test_coordination` | Backup restore test coordination | IT, DevOps & Security | P1 | Нет | Нет |
| 235 | `it_devops_security.service_health_monitoring` | Service health monitoring | IT, DevOps & Security | P1 | Нет | Нет |
| 236 | `it_devops_security.incident_detection_and_paging` | Incident detection and paging | IT, DevOps & Security | P1 | Нет | Нет |
| 237 | `it_devops_security.incident_severity_classification` | Incident severity classification | IT, DevOps & Security | P1 | Да | Нет |
| 238 | `it_devops_security.incident_response_coordination` | Incident response coordination | IT, DevOps & Security | P2 | Нет | Нет |
| 239 | `it_devops_security.post_incident_review` | Post-incident review | IT, DevOps & Security | P2 | Нет | Да |
| 240 | `it_devops_security.change_request_intake` | Change request intake | IT, DevOps & Security | P2 | Нет | Нет |
| 241 | `it_devops_security.change_risk_assessment` | Change risk assessment | IT, DevOps & Security | P2 | Да | Нет |
| 242 | `analytics_compliance.data_request_intake` | Data request intake | Analytics, Risk & Compliance | P0 | Нет | Нет |
| 243 | `analytics_compliance.data_quality_anomaly_detection` | Data quality anomaly detection | Analytics, Risk & Compliance | P0 | Да | Нет |
| 244 | `analytics_compliance.data_source_freshness_monitoring` | Data source freshness monitoring | Analytics, Risk & Compliance | P0 | Нет | Нет |
| 245 | `analytics_compliance.kpi_calculation_and_publication` | KPI calculation and publication | Analytics, Risk & Compliance | P0 | Нет | Нет |
| 246 | `analytics_compliance.executive_dashboard_refresh` | Executive dashboard refresh | Analytics, Risk & Compliance | P0 | Нет | Нет |
| 247 | `analytics_compliance.scheduled_management_reporting` | Scheduled management reporting | Analytics, Risk & Compliance | P0 | Нет | Нет |
| 248 | `analytics_compliance.ad_hoc_report_generation` | Ad-hoc report generation | Analytics, Risk & Compliance | P0 | Нет | Нет |
| 249 | `analytics_compliance.forecast_refresh_and_review` | Forecast refresh and review | Analytics, Risk & Compliance | P0 | Нет | Да |
| 250 | `analytics_compliance.customer_churn_risk_detection` | Customer churn risk detection | Analytics, Risk & Compliance | P1 | Да | Нет |
| 251 | `analytics_compliance.demand_anomaly_detection` | Demand anomaly detection | Analytics, Risk & Compliance | P1 | Нет | Нет |
| 252 | `analytics_compliance.regulatory_update_monitoring` | Regulatory update monitoring | Analytics, Risk & Compliance | P1 | Нет | Нет |
| 253 | `analytics_compliance.policy_impact_assessment` | Policy impact assessment | Analytics, Risk & Compliance | P1 | Нет | Нет |
| 254 | `analytics_compliance.compliance_evidence_collection` | Compliance evidence collection | Analytics, Risk & Compliance | P1 | Нет | Нет |
| 255 | `analytics_compliance.control_execution_monitoring` | Control execution monitoring | Analytics, Risk & Compliance | P1 | Нет | Нет |
| 256 | `analytics_compliance.audit_request_coordination` | Audit request coordination | Analytics, Risk & Compliance | P1 | Нет | Нет |
| 257 | `analytics_compliance.audit_finding_remediation` | Audit finding remediation | Analytics, Risk & Compliance | P1 | Нет | Нет |
| 258 | `analytics_compliance.risk_register_update` | Risk register update | Analytics, Risk & Compliance | P1 | Да | Нет |
| 259 | `analytics_compliance.third_party_due_diligence` | Third-party due diligence | Analytics, Risk & Compliance | P1 | Нет | Нет |
| 260 | `analytics_compliance.vendor_risk_reassessment` | Vendor risk reassessment | Analytics, Risk & Compliance | P2 | Да | Нет |
| 261 | `analytics_compliance.consent_capture_and_verification` | Consent capture and verification | Analytics, Risk & Compliance | P2 | Нет | Нет |
| 262 | `analytics_compliance.data_subject_request_intake` | Data subject request intake | Analytics, Risk & Compliance | P2 | Нет | Нет |
| 263 | `autonomous_agents.autonomous_company_research_agent` | Autonomous company research agent | Autonomous Agents | P0 | Да | Да |
| 264 | `autonomous_agents.deep_research_and_cited_report_agent` | Deep research and cited report agent | Autonomous Agents | P0 | Да | Да |
| 265 | `autonomous_agents.market_monitoring_agent` | Market monitoring agent | Autonomous Agents | P0 | Да | Да |
| 266 | `autonomous_agents.competitive_intelligence_agent` | Competitive intelligence agent | Autonomous Agents | P0 | Да | Да |
| 267 | `autonomous_agents.lead_research_and_enrichment_agent` | Lead research and enrichment agent | Autonomous Agents | P0 | Да | Да |
| 268 | `autonomous_agents.sales_outreach_preparation_agent` | Sales outreach preparation agent | Autonomous Agents | P0 | Да | Да |
| 269 | `autonomous_agents.customer_support_resolution_agent` | Customer support resolution agent | Autonomous Agents | P0 | Да | Да |
| 270 | `autonomous_agents.knowledge_base_curator_agent` | Knowledge-base curator agent | Autonomous Agents | P0 | Да | Да |
| 271 | `autonomous_agents.document_intake_and_extraction_agent` | Document intake and extraction agent | Autonomous Agents | P0 | Да | Да |
| 272 | `autonomous_agents.contract_review_agent` | Contract review agent | Autonomous Agents | P0 | Да | Да |
| 273 | `autonomous_agents.invoice_processing_agent` | Invoice processing agent | Autonomous Agents | P0 | Да | Да |
| 274 | `autonomous_agents.procurement_sourcing_agent` | Procurement sourcing agent | Autonomous Agents | P0 | Да | Да |
| 275 | `autonomous_agents.recruiting_coordinator_agent` | Recruiting coordinator agent | Autonomous Agents | P1 | Да | Да |
| 276 | `autonomous_agents.employee_onboarding_coordinator_agent` | Employee onboarding coordinator agent | Autonomous Agents | P1 | Да | Да |
| 277 | `autonomous_agents.content_research_and_drafting_agent` | Content research and drafting agent | Autonomous Agents | P1 | Да | Да |
| 278 | `autonomous_agents.social_media_campaign_agent` | Social media campaign agent | Autonomous Agents | P1 | Да | Да |
| 279 | `autonomous_agents.seo_research_agent` | SEO research agent | Autonomous Agents | P1 | Да | Да |
| 280 | `autonomous_agents.meeting_preparation_agent` | Meeting preparation agent | Autonomous Agents | P1 | Да | Да |
| 281 | `autonomous_agents.meeting_follow_up_agent` | Meeting follow-up agent | Autonomous Agents | P1 | Да | Да |
| 282 | `autonomous_agents.data_analyst_agent` | Data analyst agent | Autonomous Agents | P1 | Да | Да |
| 283 | `autonomous_agents.dashboard_narrator_agent` | Dashboard narrator agent | Autonomous Agents | P1 | Да | Да |
| 284 | `autonomous_agents.incident_triage_agent` | Incident triage agent | Autonomous Agents | P1 | Да | Да |
| 285 | `autonomous_agents.qa_test_design_agent` | QA test design agent | Autonomous Agents | P1 | Да | Да |
| 286 | `autonomous_agents.repository_code_review_agent` | Repository code review agent | Autonomous Agents | P2 | Да | Да |
| 287 | `autonomous_agents.multi_agent_proposal_factory` | Multi-agent proposal factory | Autonomous Agents | P2 | Да | Да |
| 288 | `autonomous_agents.multi_agent_research_team` | Multi-agent research team | Autonomous Agents | P2 | Да | Да |
| 289 | `autonomous_agents.supervisor_worker_service_desk` | Supervisor-worker service desk | Autonomous Agents | P2 | Да | Да |
| 290 | `autonomous_agents.personal_multi_channel_work_assistant` | Personal multi-channel work assistant | Autonomous Agents | P2 | Да | Да |
| 291 | `cross_functional.customer_master_data_change_approval` | Customer master-data change approval | Cross-functional | P0 | Нет | Да |
| 292 | `cross_functional.supplier_onboarding_and_verification` | Supplier onboarding and verification | Cross-functional | P0 | Нет | Нет |
| 293 | `cross_functional.new_product_launch_coordination` | New product launch coordination | Cross-functional | P0 | Нет | Нет |
| 294 | `cross_functional.branch_opening_readiness` | Branch opening readiness | Cross-functional | P0 | Нет | Нет |
| 295 | `cross_functional.project_status_collection_and_escalation` | Project status collection and escalation | Cross-functional | P0 | Нет | Да |
| 296 | `cross_functional.service_renewal_and_billing_coordination` | Service renewal and billing coordination | Cross-functional | P0 | Нет | Нет |
| 297 | `cross_functional.quality_nonconformance_handling` | Quality nonconformance handling | Cross-functional | P0 | Да | Нет |
| 298 | `cross_functional.corrective_action_tracking` | Corrective action tracking | Cross-functional | P0 | Нет | Нет |
| 299 | `cross_functional.business_continuity_exercise_coordination` | Business continuity exercise coordination | Cross-functional | P1 | Нет | Нет |
| 300 | `cross_functional.executive_decision_memo_preparation` | Executive decision memo preparation | Cross-functional | P1 | Нет | Да |

## Источники и ограничения

Каталог создан как семантическая библиотека на основе паттернов публичного каталога n8n. Исходные workflow JSON не включены. Для каждого элемента установлен `license_status=review_required`. Перед merge требуется проверка коллизий с авторитетным manifest первых 70 процессов.