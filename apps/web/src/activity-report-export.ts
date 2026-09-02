import type { AdminActivityReport } from './types'

export interface ActivityReportExportLabels {
  summarySheet: string
  workspacesSheet: string
  metric: string
  value: string
  workspace: string
  workflowsCreated: string
  ready: string
  inProgress: string
  n8n: string
  agents: string
  agentRuns: string
  inputTokens: string
  outputTokens: string
  totalTokens: string
}

function save(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export async function downloadActivityReportXlsx(
  report: AdminActivityReport,
  labels: ActivityReportExportLabels,
  filenamePrefix: string,
) {
  const { default: ExcelJS } = await import('exceljs')
  const workbook = new ExcelJS.Workbook()
  workbook.creator = 'AI Process Architect'
  workbook.created = new Date()

  const columns = [
    ['workflowsCreated', labels.workflowsCreated],
    ['workflowsReady', labels.ready],
    ['workflowsInProgress', labels.inProgress],
    ['n8nPublications', labels.n8n],
    ['agentDeliveries', labels.agents],
    ['agentRuns', labels.agentRuns],
    ['inputTokens', labels.inputTokens],
    ['outputTokens', labels.outputTokens],
    ['totalTokens', labels.totalTokens],
  ] as const

  const summary = workbook.addWorksheet(labels.summarySheet)
  summary.columns = [{ header: labels.metric, key: 'metric', width: 34 }, { header: labels.value, key: 'value', width: 20 }]
  for (const [key, label] of columns) {
    summary.addRow({ metric: label, value: report.summary[key] })
  }

  const workspaces = workbook.addWorksheet(labels.workspacesSheet)
  workspaces.columns = [
    { header: labels.workspace, key: 'workspaceName', width: 30 },
    ...columns.map(([key, label]) => ({ header: label, key, width: 16 })),
  ]
  for (const item of report.workspaces) {
    workspaces.addRow(item)
  }

  for (const sheet of [summary, workspaces]) {
    const header = sheet.getRow(1)
    header.font = { bold: true }
    header.alignment = { vertical: 'middle' }
    sheet.views = [{ state: 'frozen', ySplit: 1 }]
  }
  summary.getColumn('value').numFmt = '#,##0.000000'

  const content = await workbook.xlsx.writeBuffer()
  save(new Blob([content], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }), `${filenamePrefix}-${report.periodStart.slice(0, 10)}.xlsx`)
}
