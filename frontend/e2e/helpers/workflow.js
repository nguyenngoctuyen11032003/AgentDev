/* global process */
// Fake workflow for the E2E suite: literal and human nodes plus one agent that fails without using model tokens.
export const WORKFLOW_ID = 'zz_e2e_fake'
export const WORKFLOW_FILE = `${WORKFLOW_ID}.yaml`
export const API = process.env.E2E_API || 'http://localhost:6400'

export const buildYaml = ({ connection, provider }) => `version: 0.4.0
vars: {}
graph:
  id: ${WORKFLOW_ID}
  description: E2E fake workflow (no model calls). Parallel branch, a soft-failing step and one approval gate.
  log_level: INFO
  is_majority_voting: false
  start:
  - Plan
  end:
  - Final
  nodes:
  - id: Plan
    type: literal
    description: Plan step (literal)
    config:
      role: assistant
      content: |-
        Plan ready.
        \`\`\`python
        raise RuntimeError("e2e planned failure")
        \`\`\`
  - id: Branch Ok
    type: literal
    description: Parallel branch that succeeds
    config:
      role: assistant
      content: Branch Ok done
  - id: Branch Soft
    type: agent
    description: Parallel branch that fails (rejected model name, no tokens) but the run goes on
    continue_on_error: true
    config:
      connection: ${connection}
      provider: ${provider}
      name: zz-e2e-no-such-model
      role: You never run.
  - id: Merge
    type: literal
    description: Merge step (literal)
    config:
      role: assistant
      content: Merge done, waiting for approval
  - id: Approval
    type: human
    description: Approval gate
    config:
      description: E2E approval gate. Reply OK to continue.
  - id: Final
    type: literal
    description: Final step (literal)
    config:
      role: assistant
      content: E2E FINISHED
  edges:
  - from: Plan
    to: Branch Ok
  - from: Plan
    to: Branch Soft
  - from: Branch Ok
    to: Merge
  - from: Branch Soft
    to: Merge
  - from: Merge
    to: Approval
  - from: Approval
    to: Final
`

// The failing step is an agent asking a signed-in CLI account for a model that does not exist: the CLI
// rejects it before any tokens are used, and the engine raises, so continue_on_error really applies.
export async function pickConnection(request) {
  const res = await request.get(`${API}/api/connections`)
  const list = res.ok() ? (await res.json()).connections || [] : []
  const cli = list.find((c) => c.authType === 'cli' && !c.needsSignIn && ['anthropic', 'openai'].includes(c.vendor))
  return cli ? { connection: cli.id, provider: cli.vendor } : null
}

export async function createWorkflow(request) {
  const picked = (await pickConnection(request)) || { connection: 'none', provider: 'anthropic' }
  await request.delete(`${API}/api/workflows/${WORKFLOW_FILE}/delete`).catch(() => {})
  const res = await request.post(`${API}/api/workflows/upload/content`, {
    data: { filename: WORKFLOW_FILE, content: buildYaml(picked) },
  })
  if (!res.ok()) throw new Error(`create workflow failed: ${res.status()} ${await res.text()}`)
  return picked
}

export async function deleteWorkflow(request) {
  await request.delete(`${API}/api/workflows/${WORKFLOW_FILE}/delete`).catch(() => {})
}
