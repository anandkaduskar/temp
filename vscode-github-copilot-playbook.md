# VS Code + GitHub Copilot — Memory, Context, Skills & Model Playbook

Models in use: **Claude Opus** (plan/architect), **Claude Sonnet** (build/iterate), **Claude Haiku** (bulk/mechanical), selected via Copilot's model picker (availability depends on your plan and org policy).

---

## 1. Principles

1. The model has no memory between sessions. **State lives in files**, not in chat.
2. Always-on instructions are expensive. **Keep them short; scope the rest** with `applyTo` globs, skills and agents.
3. Copilot has no auto-managed memory — **file-based memory with an explicit write protocol is essential.**
4. Verification beats trust: tell the agent how to run tests/lint.
5. Check each feature against your surface (VS Code vs CLI vs GitHub.com coding agent) — support differs.

---

## 2. Project layout

```
repo/
├── AGENTS.md                         # tool-agnostic always-on rules (also read by Claude Code)
├── .github/
│   ├── copilot-instructions.md       # repo-wide, always-on (short: 5–15 core rules)
│   ├── instructions/*.instructions.md  # path-scoped rules (applyTo globs)
│   ├── prompts/*.prompt.md           # reusable /slash tasks (VS Code, CLI)
│   ├── agents/*.agent.md             # custom agents/personas (tools, model, handoffs)
│   ├── skills/<name>/SKILL.md        # model-invoked skills
│   └── hooks/                        # deterministic automation (where supported)
├── .claude/skills/<name>/SKILL.md    # also discovered by Copilot — share with Claude Code
├── .vscode/mcp.json                  # MCP servers for the workspace
├── docs/                             # reference docs, attached on demand
└── memory/
    ├── decisions.md
    ├── state.md
    └── open-questions.md
```

Pick **one** source of truth for always-on rules: either `AGENTS.md` or `.github/copilot-instructions.md`. Avoid duplicating content in both.

User-level prompts/instructions/agents live in your VS Code user prompts folder and roam with Settings Sync (skills are project-level or via extensions/plugins).

---

## 3. Customization primitives — when to use which

| Need | Primitive | Activation |
|---|---|---|
| Always-true rules | `copilot-instructions.md` / `AGENTS.md` | Automatic, every request |
| Language/folder-specific rules | `.instructions.md` with `applyTo` | Automatic on glob match |
| Repeatable task with inputs | `.prompt.md` | Manual `/name` |
| Specialized role with its own tools/model | `.agent.md` | Pick from agent picker / subagent |
| Capability with scripts/resources | `SKILL.md` folder | Model-invoked when relevant |
| External systems | MCP (`mcp.json`) | Tools available to agent |
| Must-always-happen automation | Hooks | Deterministic |

---

## 4. Memory

| Layer | Mechanism |
|---|---|
| Stable rules | `AGENTS.md` / `copilot-instructions.md` |
| Scoped rules | `*.instructions.md` + `applyTo` |
| Evolving state | `memory/*.md` (decisions, state, open questions) |
| Session hygiene | New chat per task; attach context explicitly |

**Write-discipline rule (put in instructions):**
> Before starting, read `memory/state.md` and `memory/decisions.md`. After any decision or significant change, append a dated entry to `memory/decisions.md` (decision, rationale, status). Before ending, update `memory/state.md` and `memory/open-questions.md`.

Verify in practice that agent mode actually edits these files — if not, make the update step an explicit part of your prompt files/agents.

---

## 5. Instruction templates

**`.github/copilot-instructions.md`** (aim for 5–15 rules):
```markdown
# <Project> — Rules
- Read memory/state.md and memory/decisions.md before non-trivial work.
- Plan first: state understanding, assumptions, affected files; wait for approval on multi-file changes.
- Build: `...`  Test: `...`  Lint: `...` — run tests after changes.
- Follow conventions in docs/conventions.md.
- After decisions, append to memory/decisions.md.
- Never edit: .env, migrations/ without asking.
```

**`.github/instructions/python.instructions.md`**:
```markdown
---
applyTo: "**/*.py"
---
- Type hints on all public functions; pytest for tests; no print() in library code.
```

**`.github/prompts/plan-change.prompt.md`**:
```markdown
---
description: Plan a change before implementing
agent: agent
model: <your Opus model name as shown in the picker>
---
Analyze the request, read memory/, list affected files, risks, test plan. Do not edit files. Output a numbered plan.
```

**`.github/agents/reviewer.agent.md`**:
```markdown
---
description: Strict reviewer for correctness, security, convention drift
tools: ['codebase', 'search', 'usages']
model: <your Sonnet model name>
---
Review the diff. Report by severity with file:line. Do not edit files.
```

(Exact frontmatter keys, tool names and model identifiers change between VS Code releases — check the Chat Customizations editor / docs.)

---

## 6. Context practices

- Attach context explicitly: `#file`, `#codebase`, `#selection`, drag files into chat.
- **Plan before code** — use a planning prompt/agent, then switch to implementation.
- One task per chat; start a new chat rather than stretching a long one (less control over compaction than Claude Code).
- Use MCP for DB/tickets/docs instead of pasting (e.g., PostgreSQL server in `.vscode/mcp.json`).
- Give the agent runnable verification (tests, linters, typecheck) and list the commands in instructions.

---

## 7. Skills

`.github/skills/<name>/SKILL.md` (or `.claude/skills/...`, `.agents/skills/...`):
```markdown
---
name: adr-writer
description: Use when the user asks to draft or review an Architecture Decision Record, or says "ADR", "decision log", "why did we choose X".
---
1. Read memory/decisions.md.
2. Draft: Context, Decision, Options, Consequences, Status.
3. Append to memory/decisions.md.
```
- The **description is the trigger** — use "use when…" with concrete phrases.
- Skills are an open standard: the same folder works in Copilot and Claude Code.
- Put skills under `.claude/skills/` if you want one copy shared by both tools.

---

## 8. Model routing: Opus / Sonnet / Haiku

| Model | Use for | Avoid for |
|---|---|---|
| **Opus** | Architecture, planning, ambiguous/cross-cutting work, hard debugging, design review | Routine edits, bulk work |
| **Sonnet** | Default for implementation, refactors, tests, docs | Deep ambiguity needing long reasoning |
| **Haiku** | Mechanical edits, boilerplate, summarization, quick Q&A, log triage | Design decisions, subtle bugs |

**How to apply it in Copilot**
- Switch models in the chat **model picker** per task.
- Pin models in **prompt files and custom agents** (`model:` frontmatter) — e.g., `plan-change` → Opus, `implement` → Sonnet, `summarize` / `boilerplate` → Haiku.
- Copilot bills premium requests with **per-model multipliers**; heavier models consume more. Check your plan's multipliers and use Haiku/Sonnet by default, Opus deliberately.
- Escalate when stuck: after two failed attempts on one problem, summarize findings in a new chat and switch to Opus.
- Because state is in files, switching models mid-task loses nothing.

**Suggested default routing**
1. Opus: `/plan-change` → plan + ADR entry.
2. Sonnet: implement + tests (agent mode).
3. Haiku: mechanical edits, summaries, doc touch-ups.
4. Sonnet (Opus for high-risk): `reviewer` agent before merge.

Note: the same Claude model can behave differently in Copilot than in Claude Code — different harness, tools and system prompts. Validate on your own tasks.

---

## 9. Setup checklist

- [ ] One always-on source of truth (`AGENTS.md` or `copilot-instructions.md`), concise
- [ ] `*.instructions.md` with `applyTo` for language/folder rules
- [ ] `memory/` files + write-discipline rule
- [ ] Prompt files: plan, implement, review, summarize (models pinned)
- [ ] Custom agents with tool restrictions and models pinned
- [ ] Skills in `.github/skills/` or `.claude/skills/` with trigger-phrased descriptions
- [ ] `.vscode/mcp.json` committed; each server verified
- [ ] Test/lint commands documented and passing
- [ ] Confirmed which features your surface supports (VS Code / CLI / GitHub.com)
- [ ] Model multipliers/quotas understood for your plan

## 10. Failure modes

1. Bloated always-on instructions → ignored rules. Scope with `applyTo`.
2. Duplicated rules across `AGENTS.md` and `copilot-instructions.md` → drift.
3. No memory write protocol → stale state.
4. Long single chat across tasks → degraded output; start fresh.
5. Assuming a feature works everywhere (e.g., prompt files on GitHub.com) → check support.
6. Opus for everything → quota burn; Haiku for design → shallow output.

> Copilot customization features change fast; confirm against the GitHub Docs customization cheat sheet and VS Code docs.
