# VS Code + Claude Code — Memory, Context, Skills & Model Playbook

Models in use: **Opus** (plan/architect), **Sonnet** (build/iterate), **Haiku** (bulk/mechanical).

---

## 1. Principles

1. The model has no memory between sessions. **State lives in files**, not in chat.
2. Always-on context is expensive. **Keep it short; load detail on demand.**
3. Deterministic needs (format, tests, protected files) belong in **hooks and permissions**, not prose instructions.
4. Verification beats trust: give the model tests/linters it can run.

---

## 2. Project layout

```
repo/
├── CLAUDE.md                  # short: identity, rules, commands, map
├── .mcp.json                  # shared MCP servers (DB, repo, docs, tickets)
├── .claude/
│   ├── settings.json          # permissions, hooks, default model
│   ├── skills/<name>/SKILL.md # model-triggered capabilities
│   ├── agents/<name>.md       # subagents (own context, tools, model)
│   └── commands/<name>.md     # slash-command workflows
├── docs/                      # reference docs, loaded on demand
└── memory/
    ├── decisions.md           # ADR-style log
    ├── state.md               # current status / open positions / WIP
    └── open-questions.md
```

User-level (all projects): `~/.claude/CLAUDE.md`, `~/.claude/skills/`, `~/.claude/agents/`.

---

## 3. Memory

| Layer | Mechanism | Contents |
|---|---|---|
| Stable rules | `CLAUDE.md` (user → project → subfolder) | Identity, conventions, commands, non-negotiables, file map |
| Evolving state | `memory/*.md` | Decisions, status, open threads |
| Session hygiene | `/clear`, `/compact <focus>`, `/resume` | Keep window clean, resume work |

**Write-discipline rule (put in CLAUDE.md):**
> After any decision or significant change, append a dated entry to `memory/decisions.md` (decision, rationale, status). At session end, update `memory/state.md` and `memory/open-questions.md`.

Without an explicit rule, memory files go stale.

---

## 4. CLAUDE.md template (keep under ~150 lines)

```markdown
# <Project> — Instructions
## Identity & stance
<one paragraph: role, tone, non-negotiables>

## Commands
- Build: ...
- Test: ...
- Lint/typecheck: ...

## Conventions
- <only rules that are always true>

## Map (load on demand)
- Architecture: docs/architecture.md
- Data model: docs/data-model.md
- Skills: .claude/skills/ (auto-triggered)
- Memory: memory/ (read at start, update at end)

## Memory protocol
<write-discipline rule above>

## Model routing
See section 8.
```

Use `@docs/file.md` imports inside CLAUDE.md for things that must load, and plain pointers for things that should load only when relevant.

---

## 5. Context practices

- Reference files explicitly: `@path/file`, `@folder/`.
- **Plan before code** for anything non-trivial (Plan mode / Shift+Tab): state understanding, assumptions, affected files → approve → execute.
- **Subagents for exploration**: broad searches return a summary, not a context flood.
- **MCP over pasting**: DB, repo, tickets, docs via `.mcp.json`.
- One task per session; `/clear` between unrelated tasks, re-anchor from files.
- List test/lint commands in CLAUDE.md so the model can self-verify.

---

## 6. Skills

`.claude/skills/<name>/SKILL.md`:

```markdown
---
name: adr-writer
description: Use when the user asks to record, draft or review an Architecture Decision Record, or says "ADR", "decision log", "why did we choose X".
---
# ADR Writer
## Steps
1. Read memory/decisions.md for prior context.
2. Draft: Context, Decision, Options considered, Consequences, Status.
3. Append to memory/decisions.md.
## Resources
- templates/adr.md
```

- **The description is the trigger.** Write "use when X, Y, Z" with concrete phrases; vague descriptions never fire.
- Put scripts/templates beside SKILL.md; reference them from the body.
- Skills **must be under `.claude/skills/`** (or a plugin) to be auto-discovered. Folders like `skills/work/` outside `.claude/` will not auto-load — symlink or move.

---

## 7. Subagents, commands, hooks, permissions

**Subagent** `.claude/agents/reviewer.md`:
```markdown
---
name: reviewer
description: Reviews diffs for correctness, security, and convention drift. Use after implementation.
tools: Read, Grep, Glob, Bash
model: sonnet
---
You are a strict code reviewer. Report findings by severity with file:line references. Do not edit files.
```

**Slash command** `.claude/commands/review-pr.md` — a prompt template invoked as `/review-pr`.

**Hooks** (`.claude/settings.json`): enforce what must always happen — format on edit, run tests after changes, block edits to protected paths.

**Permissions** (`settings.json`): allow/deny lists per project (e.g., deny `.env`, deny destructive shell commands).

---

## 8. Model routing: Opus / Sonnet / Haiku

| Model | Use for | Avoid for |
|---|---|---|
| **Opus** | Architecture, planning, ambiguous or cross-cutting problems, hard debugging, design review, ADRs | Routine edits, bulk work (slow/costly) |
| **Sonnet** | Default for implementation, refactors, tests, docs, iteration | Deep ambiguity needing long reasoning chains |
| **Haiku** | Bulk/mechanical: renames, formatting, boilerplate, summarizing files, log triage, simple subagent lookups | Design decisions, subtle bugs |

**How to apply it**
- Switch in-session with `/model`; set a default in `settings.json` or at launch.
- Use the **plan-with-Opus, execute-with-Sonnet** mode (`opusplan`) if available in your version: Opus in plan mode, Sonnet in execution.
- Pin per-subagent via the `model:` frontmatter field — e.g., explorer/summarizer agents on `haiku`, reviewer on `sonnet`, architect on `opus`.
- Escalate when stuck: if Sonnet fails twice on the same problem, restate the problem with findings so far and switch to Opus.
- Because state lives in files, switching models mid-project loses nothing.

**Suggested default routing**
1. Opus: plan + ADR for the change.
2. Sonnet: implement + tests.
3. Haiku subagents: scan repo, summarize, mechanical edits.
4. Sonnet/Opus: review before merge (Opus for high-risk changes).

---

## 9. Setup checklist

- [ ] CLAUDE.md written, <150 lines, includes commands + memory protocol + map
- [ ] `memory/` files created; write-discipline rule added
- [ ] Skills moved/symlinked under `.claude/skills/`, descriptions have trigger phrases
- [ ] Subagents defined with `tools:` and `model:` set
- [ ] `.mcp.json` committed; each server verified (`/mcp`)
- [ ] `settings.json`: permissions + hooks (format/test/protect)
- [ ] Test/lint commands run clean from the terminal
- [ ] Team habit: plan first, one task per session, `/clear` between tasks

## 10. Failure modes

1. Bloated CLAUDE.md → rules ignored. Trim.
2. Skills outside discovery path → never trigger.
3. Long mixed-topic sessions → degraded output. Clear and re-anchor.
4. Memory with no write protocol → stale/contradictory state.
5. No verification loop → "looks right" is the only check.
6. Using Opus for everything → slow and costly; using Haiku for design → shallow output.

> Feature names and flags evolve; confirm against current Claude Code docs.
