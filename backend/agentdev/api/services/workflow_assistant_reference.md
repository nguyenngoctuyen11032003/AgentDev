# AgentDev workflow YAML reference

A workflow is one YAML file in `workspace/workflows/`. Write YAML 1.1 that `yaml.safe_load` accepts.

## File frame

```text
version: 0.4.0          # always 0.4.0
vars: {}                # optional; root-level only
graph:
  id: content_pipeline  # snake_case, usually the file name without .yaml
  description: >-       # one or two sentences: what the workflow does and how the user uses it
    ...
  log_level: INFO
  is_majority_voting: false
  start: [Node A]       # node ids that run first; they receive the user's message
  end: [Node Z]         # node ids whose output is the final answer
  nodes: [...]
  edges: [...]          # [] for a pure team (lead delegates at run time)
```

- `end` is required unless exactly one node has no outgoing edge. Always write both `start` and `end`.
- Node ids: unique, short, Title Case, spaces allowed (`QA Tester`, `Revision Guard`). The same exact id is
  used in `start`, `end`, `edges[].from/to` and `team.members`. Keep ids in English unless the user asks.

## Nodes

Every node: `id` (required), `type` (required: `agent`, `human`, `literal`, `passthrough`, `loop_counter`,
`subgraph`), `description` (one line; a team lead routes work on it), `config` (required, depends on type).

### agent (an AI worker)
Required: `provider`, `name`. Strongly recommended: `role`.
- `provider`: vendor id from the model list given to you (`anthropic` or `openai`).
- `name`: a model of that vendor from the list (e.g. `claude-opus-5-5` for leads/hard reasoning,
  `claude-sonnet-5-5` for most workers). Never write `connection`, `api_key` or `base_url`: the account is
  bound automatically at run time.
- `role`: the system prompt (block scalar `|-`). Say who the agent is, its scope, its output format, and
  any verdict keyword that edge conditions depend on.
- `params` (optional): `effort: low|medium|high`, `max_tokens: 16000`, `tool_loop_limit: 80`.
- `skills` (optional): `enabled: true` + `allow: [{name: <skill>}]`. Only names from the skill catalog.
- `tooling` (optional): list of `{type: function, config: {tools: [{name: <tool>}]}}`. Only names from the
  tool catalog. Read-only set: `describe_available_files`, `list_directory`, `read_file_segment`,
  `search_in_files`. Writing adds `create_folder`, `save_file`, `apply_text_edits`.
- `native_mode` (optional, coding agents): `{enabled: true, allow_commands: true}` runs the agent as a full
  Claude Code / Codex agent in the project folder.
- `team` (optional, makes this agent a lead), see below.

### human (a person answers in the UI)
`config: {description: "What the person must review or type"}`. The run pauses until they reply; their
text becomes the node output, so edge conditions can test it (e.g. `any: [OK]`).

### literal (fixed text)
`config: {content: "text", role: user}`. `content` is required and non-empty; `role` is `user` or
`assistant`. Ignores its inputs.

### passthrough (forward input unchanged)
`config: {}` (forwards only the last message); `{only_last_message: false}` forwards all inputs. Use as an entry point that holds the user's brief, or as a
join/exit point.

### loop_counter (stops a loop)
`config: {max_iterations: 3, message: "Revision limit reached"}` (`max_iterations` >= 1, required;
`reset_on_emit` default true). It outputs nothing until it has been triggered `max_iterations` times, then
emits `message`. Wiring rule: the node that decides "loop again" feeds both the loop body and the counter;
the counter has an edge back into the loop body (so it counts as inside the loop) and an edge to the node
outside the loop that should run when the limit is hit. See example 2.

### subgraph (a whole workflow as one node)
- Existing workflow: `config: {type: file, config: {path: other_workflow.yaml}}` (path relative to
  `workspace/workflows/`; only files from the existing-files list).
- Inline: `config: {type: config, config: {id: ..., description: ..., start: [...], end: [...], nodes: [...],
  edges: [...]}}` (same fields as `graph`, no `vars`).
A proposal is always exactly one file: never invent a new file for a subgraph.

## Edges

```text
- from: Reviewer           # required, node id
  to: Writer               # required, node id
  condition: ...           # optional, default 'true' (always)
  trigger: true            # default true; false = deliver data but do not start the target
  carry_data: true         # default true; false = start the target without passing the output
  keep_message: false      # default false; true = target keeps this message on every later run
```

- A node runs when at least one incoming edge with `trigger: true` has fired (start nodes run first). It
  receives the outputs of every incoming edge whose condition matched and that carries data.
- `keep_message: true` on the edge from the brief into a loop body keeps the original request visible on
  every iteration (by default an agent sees only the inputs of its current run).
- Keyword condition (the usual branch), tested on the source node's output text:
  `condition: {type: keyword, config: {any: [APPROVED]}}`; the "else" branch uses `none: [APPROVED]`.
  Also `regex: ["^PASS"]` and `case_sensitive` (default true). Write the `any`/`none` pair so exactly one
  branch fires, and tell the source agent in its `role` to start its reply with the keyword.
- Function condition: `condition: code_pass` (also `code_fail`, `need_reflection_loop`, `should_stop_loop`).
- Every cycle needs a way out: a keyword branch to a node outside the loop and/or a `loop_counter`.

## Teams (a lead delegates at run time)

`team: {enabled: true, members: [<agent ids>], plan_approval: true, max_delegations: 20,
max_review_rounds: 3, max_parallel: 2}`. `plan_approval`: the lead proposes a plan and waits for the user's
OK before building. `max_delegations`: cap per request. `max_review_rounds`: times failed work may go back.
`max_parallel`: members working at once (1 = one after another).

- The lead is usually the only `start` and `end` node, and `edges: []`. Members are agent nodes with no
  edges; the lead calls them by id. A member may itself be a lead of its own members (e.g. a project
  manager under a CTO). Every id in `members` must be an agent node in the same file.
- Put the routing rules (who gets which kind of task, in what order) in the lead's `role`.

## Shape: team, pipeline, or mixed
- Team: one lead + members, `edges: []`. Flexible; the lead decides order. Good for open-ended work.
- Pipeline: fixed order with edges, optional review loops and human checkpoints. Good for repeatable work.
- Mixed: a pipeline whose step is a lead with a team, or a `subgraph` node.

## YAML style
- Reuse identical blocks with anchors: first `tooling: &code_tools` then `tooling: *code_tools`.
- When editing an existing workflow, copy every part the user did not ask to change verbatim, including
  comments, anchors and aliases.

## Example 1: team (trimmed from software_company.yaml)

```yaml
version: 0.4.0
vars: {}
graph:
  id: small_web_team
  description: >-
    Small web team. You chat only with the Tech Lead, who plans the work, gets your approval and
    delegates to the frontend developer and the QA tester.
  log_level: INFO
  is_majority_voting: false
  start: [Tech Lead]
  end: [Tech Lead]
  nodes:
    - id: Tech Lead
      type: agent
      description: Team lead, the only one who talks to the client
      config:
        provider: anthropic
        name: claude-opus-5-5
        role: |-
          You are the tech lead of a small web team. The user is your client and talks only to you.
          Questions: answer yourself. New work: propose a short plan, wait for approval, then brief the
          Frontend Developer, then have the QA Tester check the result.
          Check reports against the request and answer the client concisely, in their language.
        skills:
          enabled: true
          allow:
            - name: spec-driven-development
        team:
          enabled: true
          members: [Frontend Developer, QA Tester]
          plan_approval: true
          max_delegations: 15
          max_review_rounds: 3
          max_parallel: 1
        params:
          effort: high
    - id: Frontend Developer
      type: agent
      description: Builds screens and components
      config:
        provider: anthropic
        name: claude-sonnet-5-5
        role: |-
          You are a frontend developer. Build the assigned screens: responsive, accessible, with loading,
          empty and error states. Report the files you changed.
        skills:
          enabled: true
          allow:
            - name: frontend-ui-engineering
        tooling: &code_tools
          - type: function
            config:
              tools:
                - name: describe_available_files
                - name: list_directory
                - name: read_file_segment
                - name: search_in_files
                - name: create_folder
                - name: save_file
                - name: apply_text_edits
    - id: QA Tester
      type: agent
      description: Tests the work against the acceptance criteria
      config:
        provider: anthropic
        name: claude-sonnet-5-5
        role: |-
          You are the QA tester. Check the delivered work against the request. Report PASS or FAIL per
          criterion with short evidence.
        tooling: *code_tools
  edges: []
```

## Example 2: pipeline with review loop, limit and human approval

```yaml
version: 0.4.0
vars: {}
graph:
  id: article_pipeline
  description: >-
    Writes an article from your brief. An AI reviewer sends it back for fixes (at most 3 rounds),
    then you approve it and it is formatted for publishing.
  log_level: INFO
  is_majority_voting: false
  start: [Brief]
  end: [Publisher]
  nodes:
    - id: Brief
      type: passthrough
      description: Holds the user's brief
      config: {}
    - id: Writer
      type: agent
      description: Writes and revises the article
      config:
        provider: anthropic
        name: claude-sonnet-5-5
        role: |-
          You write the article described in the brief. When you receive review notes, rewrite the whole
          article applying every note. Output only the article.
    - id: Reviewer
      type: agent
      description: Reviews the draft and approves it or asks for fixes
      config:
        provider: anthropic
        name: claude-opus-5-5
        role: |-
          You review the draft against the brief. Start your reply with exactly one verdict word:
          APPROVED, followed by the full final article; or REVISE, followed by numbered, concrete fixes.
    - id: Revision Guard
      type: loop_counter
      description: Stops the loop after 3 revision rounds
      config:
        max_iterations: 3
        message: Revision limit reached without approval. Please decide on the last draft.
    - id: Editor Approval
      type: human
      description: The user approves the article before publishing
      config:
        description: Read the article. Reply OK to publish, or write the changes to make.
    - id: Publisher
      type: agent
      description: Formats the approved article for publishing
      config:
        provider: anthropic
        name: claude-sonnet-5-5
        role: |-
          Format the approved article as clean Markdown with a title, a short summary and headings.
          Apply any change the editor asked for.
  edges:
    - from: Brief
      to: Writer
      keep_message: true
    - from: Writer
      to: Reviewer
    - from: Reviewer
      to: Writer
      condition: {type: keyword, config: {none: [APPROVED]}}
    - from: Reviewer
      to: Revision Guard
      condition: {type: keyword, config: {none: [APPROVED]}}
    - from: Revision Guard
      to: Writer
    - from: Revision Guard
      to: Editor Approval
    - from: Reviewer
      to: Editor Approval
      condition: {type: keyword, config: {any: [APPROVED]}}
    - from: Editor Approval
      to: Publisher
```

## Rules for every proposal
1. Every agent has `provider` and `name` taken from the model list you were given; prefer the vendor the
   user is chatting with unless they ask otherwise.
2. Skills and tools: only names from the catalogs. Unknown tool names make the workflow fail its check.
3. `subgraph` points only to a file in the existing-files list, or is an inline graph.
4. Every id in `start`, `end`, edges and `team.members` matches a node id exactly.
5. Every node can run: it is a start node, the target of a triggering edge, or a team member.
6. Every loop has an exit; give the verdict keyword to the agent whose output the condition tests.
7. A new file name is a snake_case slug ending in `.yaml` that is not in the existing-files list.
