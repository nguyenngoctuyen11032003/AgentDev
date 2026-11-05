/**
 * Department templates offered on the workbench start panel (same set as DepartmentTemplatePicker).
 * `always: true` keeps the card visible before the workflow list has loaded.
 */
export const WORKFLOW_TEMPLATES = [
  { file: 'software_company.yaml', labelKey: 'workflow_list.dept_software', descKey: 'workflow_list.dept_software_desc', always: true },
  { file: 'marketing_agency.yaml', labelKey: 'workflow_list.dept_marketing', descKey: 'workflow_list.dept_marketing_desc' },
  { file: 'content_studio.yaml', labelKey: 'workflow_list.dept_content', descKey: 'workflow_list.dept_content_desc' }
]

const stripExt = (name) => String(name || '').replace(/\.ya?ml$/i, '')

/**
 * Workflow name (no extension) the "Open a template" button opens: the first department template that
 * exists, else the first existing workflow, else '' (nothing to open).
 */
export function pickDefaultTemplate(existingFiles) {
  const files = (Array.isArray(existingFiles) ? existingFiles : []).map((name) => String(name))
  const existing = new Set(files.map((name) => stripExt(name).toLowerCase()))
  const template = WORKFLOW_TEMPLATES.find((tpl) => existing.has(stripExt(tpl.file).toLowerCase()))
  if (template) return stripExt(template.file)
  return files.length ? stripExt(files[0]) : ''
}
