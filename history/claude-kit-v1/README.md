# ConsentLens Claude setup

## Claude Code (recommended while coding)

1. Copy `CLAUDE.md` to your **repository root** (read/edit it first if the project already has one).
2. Copy `.claude/skills/` to `<repository-root>/.claude/skills/` and commit it so both teammates can share reusable instructions.
3. Put the full team implementation plan into the repository as `TEAM_PLAN.md`, if it is not already there. The supplied kit does **not** include that plan.
4. Start Claude Code in the repository directory. Ask it to inspect `CLAUDE.md`, `TEAM_PLAN.md`, and the codebase. Skills: `/build-slice`, `/privacy-audit`, `/muse-integration`, `/demo-ready`.
5. Begin with PROMPTS.md -> first-session prompt. Then choose the appropriate skill and name one precise task.

Keep normal permission approvals on; do not grant broad secret access or unchecked destructive shell operations merely to speed up coding.

## Claude.ai Project

Put the contents of `CLAUDE.md` in Project Instructions, upload `TEAM_PLAN.md`, and paste individual prompts from `PROMPTS.md`. File-system skills apply primarily to Claude Code, but skill instructions can be repurposed as prompts.

## Ownership and priorities

Abbos: `vision/` + frontend features. Teammate: backend + live recordings + Meta APIs + initial scaffold. Shared contract changes require coordination. First ship a real working live privacy pipeline; then improvements and demo readiness.

Official Anthropic docs: https://code.claude.com/docs/en/skills and https://support.claude.com/en/articles/14553240-give-claude-context-claude-md-and-better-prompts
