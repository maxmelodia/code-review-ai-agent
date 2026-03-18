<!--
Auto-generated helper for AI coding agents. This file was created by an assistant
based on repository contents as of March 17, 2026. If you update the repo, please
update these instructions so they stay accurate and actionable.
-->
# Copilot / AI agent instructions — code-review-ai-agent

Purpose
- Give brief, concrete guidance so an AI agent can be productive immediately in this repository.

Repo snapshot (discovered)
- Only file present at repository root: `README.md` (path: `/README.md`).
- Branch: `develop` (current working branch). Owner: `maxmelodia`.

High-level guidance (what to do first)
- Read `/README.md` to understand any stated project goals. Currently the README is a single heading; there is no code, build or test configuration detected.
- Before creating large scaffolding or picking a language/tooling, ask the human owner for the intended language/runtime. If the user is not available, propose one small scaffold and ask for approval.

What I (the agent) may safely do without approval
- Add small, non-destructive files (e.g., `.github/copilot-instructions.md`, small README improvements, a single CHANGELOG or CONTRIBUTING stub) in a feature branch off `develop` and open a PR. Mention the change in the PR title.

What to avoid or confirm first
- Do not rework the repository structure (add heavy scaffolding for a full app, or delete files) without explicit confirmation.
- Don't merge changes directly into `develop` — create a branch and a PR and request review.

Developer workflow notes (no build/test scripts found)
- No package manifests or CI config were detected by the initial scan. Typical files to look for in future: `package.json`, `pyproject.toml`, `requirements.txt`, `setup.py`, `Makefile`, `.github/workflows/*.yml`.
- If you add build or test files, include an easy verification command in the README (for example: `npm test`, `pytest`, or `make test`) so subsequent agents can run quick checks.

Conventions and patterns to follow here
- Keep commits small and focused. Use feature branches named `feat/<short-description>` or `fix/<short-description>` targeting `develop`.
- When adding new language-specific scaffolding, add a short README section that documents the exact commands to build, test and run.

Integration points & dependencies
- No external integrations were discovered. If you add integrations (APIs, cloud infra, etc.), document credentials/placement and any local emulator commands in the README.

Where to look for signals in future commits
- Top-level files (manifests and CI configs), `.github/` workflows, `src/` and `tests/` directories will indicate project language and conventions.

Examples from this repo
- Current example: `/README.md` contains only `# code-review-ai-agent` — treat this as a placeholder and surface the missing details to the human owner.

If anything here is unclear or incomplete, ask the repository owner what language/runtime and intended purpose for this project should be; I will then update these instructions and add minimal, reversible scaffolding on request.

-- End of instructions --
