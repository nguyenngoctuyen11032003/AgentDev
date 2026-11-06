// Lab findings grouped by the layer that caused them (workflow / environment / platform / scenario).
// Only workflow findings ask the workflow assistant for a fix; the other layers get their own guidance.

/** Display order: what the user can fix in the workflow first, then outside causes. */
export const LAYER_ORDER = ['workflow', 'environment', 'platform', 'scenario']

/** Layer of a finding; findings of jobs stored before layers existed count as workflow findings. */
export const layerOf = (finding) => (LAYER_ORDER.includes(finding?.layer) ? finding.layer : 'workflow')

/**
 * Findings -> [{layer, findings}] in LAYER_ORDER, empty layers left out (unless listed in `keep`, e.g. a layer
 * that has guidance or a report to show), original order kept inside a layer.
 */
export function groupFindings(findings, keep = []) {
  const groups = new Map(LAYER_ORDER.map((layer) => [layer, []]))
  for (const finding of findings || []) groups.get(layerOf(finding)).push(finding)
  return LAYER_ORDER.filter((layer) => groups.get(layer).length || keep.includes(layer)).map((layer) => ({
    layer,
    findings: groups.get(layer)
  }))
}

/** The "fix with the assistant" brief is offered only when the server says the workflow needs a fix (old jobs: no flag). */
export const needsWorkflowFix = (job) => !!job && job.needs_workflow_fix !== false && !!job.fix_brief

/** Findings exist but none of them is caused by the workflow: tell the user the workflow can stay as it is. */
export const workflowUnchanged = (job) =>
  !!job?.findings?.length && !job.findings.some((finding) => layerOf(finding) === 'workflow')

/** Stable code of a platform-fix API error ("lab_bad_password" and "bad_password" both -> "bad_password"). */
export const platformFixErrorCode = (error) => String(error?.code || error?.error_code || '').replace(/^lab_/, '')
